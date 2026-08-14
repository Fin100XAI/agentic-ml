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

from engine.agents import run_brief_agent, run_eda_agent, run_interpret_agent, run_recommend_agent
from engine.catalog import get_model, models_for_use_case
from engine.insights import build_insights
from engine.llm.base import LLMProvider
from engine.profiler import profile_dataframe
from engine.suggest import suggest_hyperparams

STAGES = ["upload", "eda", "recommend", "configure", "execute", "interpret", "compare"]

# Metric used to rank models in a comparison; (key, higher_is_better).
PRIMARY_METRIC = {
    "classification": ("f1", True),
    "clustering": ("silhouette", True),
    "forecasting": ("mape_pct", False),
}


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
    created_at: str = field(default_factory=_now)
    profile: dict[str, Any] | None = None
    eda: dict[str, Any] | None = None
    recommendation: dict[str, Any] | None = None
    config: dict[str, Any] | None = None  # approved model + hyperparams + columns
    result: dict[str, Any] | None = None
    interpretation: dict[str, Any] | None = None
    insights: dict[str, Any] | None = None
    comparison: dict[str, Any] | None = None
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
            "created_at": self.created_at,
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
                insights=self.insights,
                comparison=self.comparison,
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
            # Data-aware hyperparameter suggestions for every model of the use case.
            run.recommendation["model_configs"] = suggest_hyperparams(
                run.df,
                run.recommendation["use_case"],
                target=run.recommendation.get("target"),
                time_column=run.recommendation.get("time_column"),
            )
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

        # Interpretation + insight extraction run automatically after execution.
        self._interpret(run)
        self._build_insights(run)
        return run

    def _build_insights(self, run: Run) -> None:
        """Turn the model run into decision-ready findings + an executive brief."""
        node = DecisionNode(stage="insights", title="Insight extraction")
        run.decisions.append(node)
        try:
            cluster_labels = run.result["artifacts"].pop("labels", None)  # strip from payload
            insights = build_insights(
                run.df,
                run.config["use_case"],
                run.config.get("target"),
                run.result["metrics"],
                run.result["artifacts"],
                cluster_labels,
                n_rows=run.profile["n_rows"] if run.profile else len(run.df),
                pct_missing=(run.profile or {}).get("missingness", {}).get("pct_missing") or 0,
            )
            insights["brief"] = run_brief_agent(self.provider, insights, run.question)
            run.insights = insights
            node.status = "done"
            node.detail = f"{len(insights.get('findings', []))} findings + executive brief."
            node.agent_output = {"evidence": insights.get("evidence", {}).get("level")}
        except Exception as exc:
            node.status = "error"
            node.detail = str(exc)

    def _interpret(self, run: Run) -> DecisionNode:
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
        return interp_node

    # -- Stage: compare all models of the use case ------------------------------
    def compare(self, run: Run, target: str | None, time_column: str | None) -> Run:
        if not run.recommendation:
            raise ValueError("Approve the EDA first so a use case is chosen.")
        use_case = run.recommendation["use_case"]
        suggestions = run.recommendation.get("model_configs", {})
        metric_key, higher_better = PRIMARY_METRIC[use_case]

        node = DecisionNode(stage="compare", title=f"Compare {use_case} models")
        run.decisions.append(node)

        rows: list[dict[str, Any]] = []
        for model in models_for_use_case(use_case):
            suggested = suggestions.get(model.key, {})
            hp = model.coerce_hyperparams(suggested.get("hyperparams", {}))
            entry: dict[str, Any] = {
                "model_key": model.key,
                "model_name": model.name,
                "hyperparams": hp,
                "rationale": suggested.get("rationale", ""),
            }
            try:
                out = model.run(run.df, hp, target=target, features=None, time_column=time_column)
                out["artifacts"].pop("labels", None)  # insight-only payload; keep response slim
                entry["metrics"] = out["metrics"]
                entry["artifacts"] = out["artifacts"]
                entry["error"] = None
            except Exception as exc:
                entry["metrics"] = {}
                entry["artifacts"] = {}
                entry["error"] = str(exc)
            rows.append(entry)

        # Rank by the primary metric; failed/missing metric goes last.
        def sort_key(r: dict[str, Any]) -> float:
            v = r["metrics"].get(metric_key)
            if not isinstance(v, (int, float)):
                return float("inf")
            return -v if higher_better else v

        rows.sort(key=sort_key)
        best = next((r for r in rows if r["error"] is None and isinstance(r["metrics"].get(metric_key), (int, float))), None)

        run.comparison = {
            "use_case": use_case,
            "target": target,
            "time_column": time_column,
            "primary_metric": metric_key,
            "higher_is_better": higher_better,
            "results": rows,
            "best_model": best["model_key"] if best else None,
            "interpretation": self._compare_summary(rows, use_case, metric_key, higher_better, best),
        }
        node.status = "done"
        node.detail = (
            f"Ran {len(rows)} models; best: {best['model_name']} ({metric_key}={best['metrics'].get(metric_key)})"
            if best
            else "Comparison ran, but no model produced a valid score."
        )
        node.agent_output = {"best_model": run.comparison["best_model"]}
        run.stage = "compare"
        run.error = None
        return run

    def _compare_summary(
        self,
        rows: list[dict[str, Any]],
        use_case: str,
        metric_key: str,
        higher_better: bool,
        best: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """LLM (or heuristic) summary of the model comparison."""
        heuristic: dict[str, Any] = {
            "summary": (
                f"All {use_case} models were trained on your data with agent-suggested settings and "
                f"ranked by {metric_key.replace('_', ' ')} ({'higher' if higher_better else 'lower'} is better)."
                + (f" {best['model_name']} came out on top." if best else "")
            ),
            "next_steps": [
                "Open the winner and fine-tune its settings for an extra edge.",
                "If two models score similarly, prefer the simpler one — it is easier to trust and explain.",
            ],
            "generated_by": "heuristic",
        }
        if self.provider is None:
            return heuristic
        try:
            import json

            slim = [
                {"model": r["model_name"], "metrics": r["metrics"], "error": r["error"]}
                for r in rows
            ]
            result = self.provider.complete_json(
                (
                    "You are the comparison-report agent in an ML workbench used by people "
                    "without ML expertise. Summarize the model comparison in plain language: "
                    "who won, by how much, whether the difference is meaningful, and what to do next. "
                    "Only cite numbers present in the input."
                ),
                f"Use case: {use_case}. Ranking metric: {metric_key} ({'higher' if higher_better else 'lower'} wins).\n"
                + json.dumps(slim),
                {
                    "type": "object",
                    "properties": {
                        "summary": {"type": "string"},
                        "next_steps": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["summary", "next_steps"],
                    "additionalProperties": False,
                },
            )
            result["generated_by"] = "claude"
            return result
        except Exception:
            return heuristic
