"""Run orchestrator: drives the agent pipeline with human approval gates.

A ``Run`` moves through stages; each stage records a decision node (who proposed
what, what the human approved) which the frontend renders as the wire diagram.

    created -> profiled -> recommended -> configured -> executed -> interpreted

Every transition after an agent proposal requires an explicit approval call from
the API layer (driven by the human in the UI).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from engine.agents import run_eda_agent, run_interpret_agent, run_recommend_agent
from engine.catalog import get_model
from engine.llm.base import LLMProvider
from engine.profiler import profile_dataframe

STAGES = ["upload", "eda", "recommend", "configure", "execute", "interpret"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class DecisionNode:
    """One node in the wire diagram."""

    stage: str
    title: str
    status: str = "pending"  # pending | proposed | approved | done | error
    agent_output: dict[str, Any] = field(default_factory=dict)
    human_input: dict[str, Any] = field(default_factory=dict)
    detail: str = ""
    timestamp: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "title": self.title,
            "status": self.status,
            "agent_output": self.agent_output,
            "human_input": self.human_input,
            "detail": self.detail,
            "timestamp": self.timestamp,
        }


@dataclass
class Run:
    dataset_id: str
    df: pd.DataFrame
    filename: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    question: str = ""
    stage: str = "upload"
    profile: dict[str, Any] | None = None
    eda: dict[str, Any] | None = None
    recommendation: dict[str, Any] | None = None
    config: dict[str, Any] | None = None  # approved model + hyperparams + columns
    result: dict[str, Any] | None = None
    interpretation: dict[str, Any] | None = None
    error: str | None = None
    decisions: list[DecisionNode] = field(default_factory=list)

    def node(self, stage: str) -> DecisionNode | None:
        for d in self.decisions:
            if d.stage == stage:
                return d
        return None

    def to_dict(self, include_data: bool = True) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "dataset_id": self.dataset_id,
            "filename": self.filename,
            "question": self.question,
            "stage": self.stage,
            "error": self.error,
            "decisions": [n.to_dict() for n in self.decisions],
        }
        if include_data:
            d.update(
                profile=self.profile,
                eda=self.eda,
                recommendation=self.recommendation,
                config=self.config,
                result=self.result,
                interpretation=self.interpretation,
            )
        return d


class Orchestrator:
    """Stateless driver: every method advances one run one stage."""

    def __init__(self, provider: LLMProvider | None) -> None:
        self.provider = provider

    # -- Stage 1: profile + EDA ------------------------------------------------
    def start(self, run: Run, question: str) -> Run:
        run.question = question or ""
        run.decisions.append(
            DecisionNode(
                stage="upload", title="Dataset uploaded", status="done",
                detail=f"{run.filename}: {len(run.df):,} rows × {run.df.shape[1]} cols",
            )
        )
        node = DecisionNode(stage="eda", title="EDA & profiling")
        run.decisions.append(node)
        try:
            run.profile = profile_dataframe(run.df)
            run.eda = run_eda_agent(self.provider, run.profile)
            node.status = "proposed"
            node.agent_output = {"summary": run.eda.get("summary", "")}
            node.detail = f"Profiled {run.profile['n_cols']} columns; awaiting your review."
            run.stage = "eda"
        except Exception as exc:  # surface profiling errors to the UI
            node.status = "error"
            node.detail = str(exc)
            run.error = str(exc)
        return run

    # -- Gate: human approves EDA (optionally refining the question) ----------
    def approve_eda(self, run: Run, comment: str) -> Run:
        node = run.node("eda")
        if node:
            node.status = "approved"
            node.human_input = {"comment": comment}
        if comment:
            run.question = comment

        rec_node = DecisionNode(stage="recommend", title="Model recommendation")
        run.decisions.append(rec_node)
        try:
            run.recommendation = run_recommend_agent(self.provider, run.profile, run.question)
            rec_node.status = "proposed"
            top = run.recommendation["ranked_models"][0]["key"] if run.recommendation["ranked_models"] else "?"
            rec_node.agent_output = {
                "use_case": run.recommendation["use_case"],
                "top_model": top,
                "reasoning": run.recommendation["reasoning"],
            }
            rec_node.detail = f"Recommends {run.recommendation['use_case']} → {top}; awaiting approval."
            run.stage = "recommend"
        except Exception as exc:
            rec_node.status = "error"
            rec_node.detail = str(exc)
            run.error = str(exc)
        return run

    # -- Gate: human approves model + hyperparameters --------------------------
    def approve_config(
        self,
        run: Run,
        model_key: str,
        hyperparams: dict[str, Any],
        target: str | None,
        features: list[str] | None,
        time_column: str | None,
    ) -> Run:
        model = get_model(model_key)  # raises KeyError on bad key
        coerced = model.coerce_hyperparams(hyperparams)
        run.config = {
            "model_key": model_key,
            "model_name": model.name,
            "use_case": model.use_case,
            "hyperparams": coerced,
            "target": target,
            "features": features,
            "time_column": time_column,
        }
        rec_node = run.node("recommend")
        if rec_node and rec_node.status == "proposed":
            rec_node.status = "approved"
            rec_node.human_input = {"chosen_model": model_key}

        node = DecisionNode(
            stage="configure", title="Configuration approved", status="approved",
            human_input={"model": model_key, "hyperparams": coerced, "target": target},
            detail=f"{model.name} configured; ready to run.",
        )
        run.decisions.append(node)
        run.stage = "configure"
        return run

    # -- Stage: execute ---------------------------------------------------------
    def execute(self, run: Run) -> Run:
        if not run.config:
            raise ValueError("No approved configuration to execute.")
        node = DecisionNode(stage="execute", title=f"Run {run.config['model_name']}")
        run.decisions.append(node)
        try:
            model = get_model(run.config["model_key"])
            run.result = model.run(
                run.df,
                run.config["hyperparams"],
                target=run.config.get("target"),
                features=run.config.get("features"),
                time_column=run.config.get("time_column"),
            )
            node.status = "done"
            node.agent_output = {"metrics": run.result["metrics"]}
            node.detail = "Model trained and evaluated."
            run.stage = "execute"
            run.error = None
        except Exception as exc:
            node.status = "error"
            node.detail = str(exc)
            run.error = str(exc)
            return run

        # Interpretation runs automatically after a successful execution.
        interp_node = DecisionNode(stage="interpret", title="Results interpretation")
        run.decisions.append(interp_node)
        try:
            run.interpretation = run_interpret_agent(
                self.provider,
                run.config["model_name"],
                run.config["use_case"],
                run.config["hyperparams"],
                run.result["metrics"],
                run.result["artifacts"],
                run.question,
            )
            interp_node.status = "done"
            interp_node.agent_output = {
                "assessment": run.interpretation.get("assessment"),
                "summary": run.interpretation.get("summary", ""),
            }
            interp_node.detail = "Commentary generated."
            run.stage = "interpret"
        except Exception as exc:
            interp_node.status = "error"
            interp_node.detail = str(exc)
        return run
