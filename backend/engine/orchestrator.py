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

import time

from engine.agents import (
    run_brief_agent,
    run_eda_agent,
    run_feature_agent,
    run_interpret_agent,
    run_recommend_agent,
    run_remediation_agent,
)
from engine.autotune import autotune as run_autotune_sweep
from engine.catalog import get_model, models_for_use_case
from engine.features import apply_features, propose_features
from engine.health import assess_health
from engine.remediation import apply_fixes, propose_fixes
from engine.insights import build_insights, _original_column
from engine.llm.base import LLMProvider
from engine.profiler import profile_dataframe
from engine.suggest import suggest_hyperparams

STAGES = ["upload", "eda", "recommend", "configure", "execute", "interpret", "compare"]

# Metric used to rank models in a comparison; (key, higher_is_better).
PRIMARY_METRIC = {
    "classification": ("f1", True),
    "clustering": ("silhouette", True),
    "forecasting": ("mape_pct", False),
    "regression": ("rmse", False),
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
    autotune: dict[str, Any] | None = None
    feature_suggestions: list[dict[str, Any]] | None = None
    artifact_id: str | None = None  # the data artifact this run trained on
    remediation: dict[str, Any] | None = None  # {"status", "proposals", "applied_ids"}
    error: str | None = None
    decisions: list[DecisionNode] = field(default_factory=list)
    agent_log: list[dict[str, Any]] = field(default_factory=list)

    def labels(self) -> dict[str, str]:
        """Raw column name -> human-friendly display name."""
        if not self.profile:
            return {}
        return {c["name"]: c.get("display_name", c["name"]) for c in self.profile["columns"]}

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
            "agent_log": self.agent_log,
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
                autotune=self.autotune,
                feature_suggestions=self.feature_suggestions,
                artifact_id=self.artifact_id,
                remediation=self.remediation,
            )
        return d


class Orchestrator:
    """Stateless driver: every method advances one run one stage."""

    def __init__(self, provider: LLMProvider | None) -> None:
        self.provider = provider
        # Optional app-layer hook (run, event_dict) -> None feeding the unified
        # activity log. The engine works identically without it.
        self.on_event: Any = None
        # Optional app-layer hook (run, df, transform_type, params) -> artifact_id
        # materializing a derived data artifact. None = no artifact ledger.
        self.on_artifact: Any = None

    def _emit(self, run: Run, event_type: str, actor: str, payload: dict[str, Any],
              mode: str | None = None, latency_ms: int | None = None) -> None:
        if self.on_event is None:
            return
        try:
            self.on_event(run, {
                "event_type": event_type, "actor": actor, "payload": payload,
                "mode": mode, "latency_ms": latency_ms,
            })
        except Exception:
            pass  # logging must never break the pipeline

    def _log(
        self, run: Run, agent: str, action: str, decision: str, reasoning: str,
        generated_by: str, started: float,
    ) -> None:
        duration_ms = int((time.time() - started) * 1000)
        run.agent_log.append({
            "agent": agent,
            "action": action,
            "decision": decision,
            "reasoning": reasoning,
            "generated_by": generated_by,
            "duration_ms": duration_ms,
            "timestamp": _now(),
        })
        self._emit(
            run, "agent_call", agent,
            {"action": action, "decision": decision[:500]},
            mode="llm" if generated_by == "claude" else "fallback",
            latency_ms=duration_ms,
        )

    # -- Stage 1a: profile (fast, deterministic) -------------------------------
    def start(self, run: Run, question: str) -> Run:
        run.question = question or ""
        run.decisions.append(
            DecisionNode(
                stage="upload", title="Dataset uploaded", status="done",
                detail=f"{run.filename}: {len(run.df):,} rows × {run.df.shape[1]} cols",
            )
        )
        node = DecisionNode(stage="profile", title="Data profiling")
        run.decisions.append(node)
        try:
            started = time.time()
            run.profile = profile_dataframe(run.df)
            run.profile["health"] = assess_health(run.df, run.profile)
            health = run.profile["health"]
            n_issues = len(health["issues"])
            node.status = "done"
            node.detail = f"Profiled {run.profile['n_cols']} columns; data health: {health['score']}."
            self._log(
                run, "Profiler", "Profiled the dataset",
                f"{run.profile['n_rows']:,} rows × {run.profile['n_cols']} cols; health '{health['score']}' with {n_issues} finding(s).",
                "; ".join(i["title"] for i in health["issues"][:4]) or "No data-quality issues detected.",
                "deterministic", started,
            )
            run.stage = "profiled"

            # Remediation proposals (optional gate before EDA; non-fatal).
            try:
                started = time.time()
                proposals = propose_fixes(run.df)
                if proposals:
                    proposals, generated_by = run_remediation_agent(
                        self.provider, proposals, run.question
                    )
                    run.remediation = {
                        "status": "pending", "proposals": proposals,
                        "generated_by": generated_by,
                    }
                    self._log(
                        run, "Remediation agent", "Proposed data fixes",
                        "; ".join(p["description"] for p in proposals[:4]),
                        "Approve, adjust or skip - fixes produce a new derived copy; the original stays untouched.",
                        generated_by, started,
                    )
                else:
                    run.remediation = {"status": "none", "proposals": []}
            except Exception:
                run.remediation = {"status": "none", "proposals": []}
        except Exception as exc:  # surface profiling errors to the UI
            node.status = "error"
            node.detail = str(exc)
            run.error = str(exc)
        return run

    # -- Gate: human approves (or skips) the data fixes -----------------------
    def apply_remediation(self, run: Run, accepted_ids: list[str], skip: bool = False) -> Run:
        rem = run.remediation or {"proposals": [], "status": "none"}
        if rem.get("status") != "pending":
            raise ValueError("No pending remediation for this run.")
        proposals = rem["proposals"]
        node = DecisionNode(stage="remediation", title="Data remediation")
        run.decisions.append(node)

        if skip or not accepted_ids:
            rem["status"] = "skipped"
            rem["applied_ids"] = []
            node.status = "approved"
            node.human_input = {"skipped": True}
            node.detail = "Fixes skipped - continuing on the data as uploaded."
            self._emit(run, "decline", "user", {"gate": "remediation", "note": "skipped all fixes"})
            return run

        accepted = [p["id"] for p in proposals if p["id"] in set(accepted_ids)]
        declined = [p["id"] for p in proposals if p["id"] not in set(accepted_ids)]
        fixed = apply_fixes(run.df, proposals, accepted)
        if self.on_artifact is not None:
            try:
                run.artifact_id = self.on_artifact(
                    run, fixed, "remediation", {"fixes": accepted}
                )
            except Exception:
                pass
        before = len(run.df)
        run.df = fixed
        # Re-profile so EDA and everything after sees the fixed frame.
        run.profile = profile_dataframe(run.df)
        run.profile["health"] = assess_health(run.df, run.profile)

        rem["status"] = "applied"
        rem["applied_ids"] = accepted
        node.status = "approved"
        node.human_input = {"applied": accepted, "declined": declined}
        node.detail = (
            f"{len(accepted)} fix(es) applied - {before:,} rows in, {len(run.df):,} out; "
            f"health now '{run.profile['health']['score']}'."
        )
        self._emit(run, "approval", "user", {"gate": "remediation", "applied": accepted})
        for pid in declined:
            self._emit(run, "decline", "user", {"gate": "remediation", "fix": pid})
        return run

    # -- Stage 1b: EDA agent (slower; separate call so the UI can show progress)
    def run_eda(self, run: Run) -> Run:
        if run.profile is None:
            raise ValueError("Profile the dataset first.")
        node = DecisionNode(stage="eda", title="AI data analysis")
        run.decisions.append(node)
        try:
            started = time.time()
            run.eda = run_eda_agent(self.provider, run.profile)
            node.status = "proposed"
            node.agent_output = {"summary": run.eda.get("summary", "")}
            node.detail = "Findings ready; awaiting your review."
            self._log(
                run, "EDA agent", "Analyzed the dataset",
                run.eda.get("summary", ""),
                "Key findings: " + " | ".join(run.eda.get("key_findings", [])[:3]),
                run.eda.get("generated_by", "heuristic"), started,
            )
            run.stage = "eda"
        except Exception as exc:
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
        self._emit(run, "approval", "user", {"gate": "direction", "comment": comment})

        rec_node = DecisionNode(stage="recommend", title="Model recommendation")
        run.decisions.append(rec_node)
        try:
            started = time.time()
            run.recommendation = run_recommend_agent(self.provider, run.profile, run.question)
            self._log(
                run, "Recommendation agent", "Chose the analysis approach",
                f"Use case: {run.recommendation['use_case']}; "
                f"ranking: {', '.join(m['key'] for m in run.recommendation['ranked_models'])}; "
                f"target: {run.recommendation.get('target') or '-'}.",
                run.recommendation.get("reasoning", ""),
                run.recommendation.get("generated_by", "heuristic"), started,
            )
            # Data-aware hyperparameter suggestions for every model of the use case.
            started = time.time()
            run.recommendation["model_configs"] = suggest_hyperparams(
                run.df,
                run.recommendation["use_case"],
                target=run.recommendation.get("target"),
                time_column=run.recommendation.get("time_column"),
            )
            cfgs = run.recommendation["model_configs"]
            self._log(
                run, "Settings suggester", "Computed settings from your data",
                "; ".join(f"{k}: {v['hyperparams']}" for k, v in list(cfgs.items())[:3]),
                " ".join(v["rationale"] for v in list(cfgs.values())[:2]),
                "deterministic", started,
            )
            # Agent-proposed feature engineering (non-fatal, human approves later).
            try:
                started = time.time()
                candidates = propose_features(
                    run.df, run.recommendation.get("target"), run.recommendation["use_case"]
                )
                run.feature_suggestions = run_feature_agent(
                    self.provider, candidates, run.question,
                    run.recommendation["use_case"], run.labels(),
                )
                if run.feature_suggestions:
                    self._log(
                        run, "Feature agent", "Proposed engineered features",
                        "; ".join(f["label"] for f in run.feature_suggestions),
                        "Each is optional - tick the ones to include when approving the model.",
                        run.feature_suggestions[0].get("generated_by", "heuristic"), started,
                    )
            except Exception:
                run.feature_suggestions = []

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
        feature_ids: list[str] | None = None,
    ) -> Run:
        model = get_model(model_key)  # raises KeyError on bad key
        coerced = model.coerce_hyperparams(hyperparams)
        chosen = [
            s for s in (run.feature_suggestions or [])
            if s["id"] in set(feature_ids or [])
        ]
        run.config = {
            "model_key": model_key,
            "model_name": model.name,
            "use_case": model.use_case,
            "hyperparams": coerced,
            "target": target,
            "features": features,
            "time_column": time_column,
            "engineered": chosen,
        }
        rec_node = run.node("recommend")
        if rec_node and rec_node.status == "proposed":
            rec_node.status = "approved"
            rec_node.human_input = {"chosen_model": model_key}

        detail = f"{model.name} configured; ready to run."
        if chosen:
            detail += f" Includes {len(chosen)} engineered feature(s): " + ", ".join(
                s["label"] for s in chosen
            ) + "."
        node = DecisionNode(
            stage="configure", title="Configuration approved", status="approved",
            human_input={
                "model": model_key, "hyperparams": coerced, "target": target,
                "engineered_features": [s["label"] for s in chosen],
            },
            detail=detail,
        )
        run.decisions.append(node)
        run.stage = "configure"
        self._emit(run, "approval", "user", {
            "gate": "config", "model": model_key,
            "engineered_features": [s["label"] for s in chosen],
        })
        return run

    # -- Stage: execute ---------------------------------------------------------
    def execute(self, run: Run) -> Run:
        if not run.config:
            raise ValueError("No approved configuration to execute.")
        node = DecisionNode(stage="execute", title=f"Run {run.config['model_name']}")
        run.decisions.append(node)
        try:
            started = time.time()
            model = get_model(run.config["model_key"])
            engineered = run.config.get("engineered") or []
            df_run = apply_features(run.df, engineered)
            if engineered and self.on_artifact is not None:
                try:
                    run.artifact_id = self.on_artifact(
                        run, df_run, "feature_eng",
                        {"features": [s["id"] for s in engineered]},
                    )
                except Exception:
                    pass  # the ledger must never block training
            run.result = model.run(
                df_run,
                run.config["hyperparams"],
                target=run.config.get("target"),
                features=run.config.get("features"),
                time_column=run.config.get("time_column"),
            )
            self._add_display_labels(run)
            node.status = "done"
            node.agent_output = {"metrics": run.result["metrics"]}
            node.detail = "Model trained and evaluated."
            self._log(
                run, "Model runner", f"Trained {run.config['model_name']}",
                f"Metrics: {run.result['metrics']}",
                f"Settings used: {run.config['hyperparams']}",
                "deterministic", started,
            )
            self._run_stability_check(run)
            run.stage = "execute"
            run.error = None
            self._emit(run, "train", "system", {
                "model": run.config["model_key"], "metrics": run.result["metrics"],
            })
        except Exception as exc:
            node.status = "error"
            node.detail = str(exc)
            run.error = str(exc)
            self._emit(run, "error", "system", {"stage": "execute", "error": str(exc)[:500]})
            return run

        # Interpretation + insight extraction run automatically after execution.
        self._interpret(run)
        self._build_insights(run)
        return run

    def _run_stability_check(self, run: Run) -> None:
        """Non-fatal resampling check attached to the result payload."""
        from .validate import stability_check

        try:
            started = time.time()
            df_run = apply_features(run.df, run.config.get("engineered") or [])
            val = stability_check(df_run, run.config, run.result["metrics"])
        except Exception:
            return
        if not val:
            return
        run.result["validation"] = val
        self._log(
            run, "Stability checker", val.get("label", "Stability check"),
            "Skipped." if val.get("skipped") else
            f"{val.get('metric')} across resamples: {val.get('folds')} "
            f"(mean {val.get('mean')}, spread {val.get('std')}) - {val.get('verdict')}.",
            val.get("note", ""),
            "deterministic", started,
        )

    _DATE_PART_LABELS = {
        "days_since": "days since latest",
        "month": "month",
        "day_of_week": "day of week",
        "log": "log scale",
        "length": "text length",
    }

    def _add_display_labels(self, run: Run) -> None:
        """Attach human-friendly labels to chart artifacts (feature importance etc.)."""
        if not run.result or not run.profile:
            return
        labels = run.labels()
        raw_cols = list(labels.keys())
        for fi in run.result["artifacts"].get("feature_importance", []):
            feat = fi["feature"]
            if "__per__" in feat:
                a, b = feat.split("__per__", 1)
                fi["label"] = f"{labels.get(a, a)} per {labels.get(b, b)}"
                continue
            if "__x__" in feat:
                a, b = feat.split("__x__", 1)
                fi["label"] = f"{labels.get(a, a)} x {labels.get(b, b)}"
                continue
            if "__" in feat:
                # Engineered part like signup_date__month -> "Signup date (month)"
                src, part = feat.split("__", 1)
                part_lbl = self._DATE_PART_LABELS.get(part, part.replace("_", " "))
                fi["label"] = f"{labels.get(src, src)} ({part_lbl})"
                continue
            src = _original_column(feat, raw_cols)
            if src and src != feat:
                # One-hot feature like contract_type_two-year -> "Contract type: two-year"
                suffix = feat[len(src) + 1 :]
                fi["label"] = f"{labels[src]}: {suffix}"
            else:
                fi["label"] = labels.get(feat, feat)
        for cs in run.result["artifacts"].get("context_series", []):
            cs["label"] = labels.get(cs["name"], cs["name"])

    def _build_insights(self, run: Run) -> None:
        """Turn the model run into decision-ready findings + an executive brief."""
        node = DecisionNode(stage="insights", title="Insight extraction")
        run.decisions.append(node)
        try:
            started = time.time()
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
                display_labels=run.labels(),
            )
            # Fold data-health warnings into the trust caveats.
            health = (run.profile or {}).get("health", {})
            for issue in health.get("issues", []):
                if issue["severity"] in ("warning", "critical"):
                    insights["evidence"]["caveats"].append(f"{issue['title']}: {issue['suggestion']}")
            # A shaky stability check is a trust issue too.
            val = (run.result or {}).get("validation") or {}
            if val.get("verdict") == "variable":
                insights["evidence"]["caveats"].append(
                    f"Stability check ({val.get('label', 'resampling')}): scores ranged "
                    f"{min(val['folds'])} to {max(val['folds'])} across resamples - "
                    "results depend somewhat on which rows were used."
                )
            self._log(
                run, "Insight engine", "Extracted decision-ready findings",
                f"{len(insights.get('findings', []))} findings; evidence: {insights.get('evidence', {}).get('level')}.",
                insights.get("outcome_summary", ""),
                "deterministic", started,
            )
            started = time.time()
            insights["brief"] = run_brief_agent(self.provider, insights, run.question)
            self._log(
                run, "Brief agent", "Wrote the executive brief",
                insights["brief"].get("executive_summary", "")[:300],
                "Actions: " + " | ".join(insights["brief"].get("recommended_actions", [])[:2]),
                insights["brief"].get("generated_by", "heuristic"), started,
            )
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
            started = time.time()
            run.interpretation = run_interpret_agent(
                self.provider,
                run.config["model_name"],
                run.config["use_case"],
                run.config["hyperparams"],
                run.result["metrics"],
                run.result["artifacts"],
                run.question,
            )
            self._log(
                run, "Interpretation agent", "Judged the model's results",
                f"Assessment: {run.interpretation.get('assessment')}. {run.interpretation.get('summary', '')[:200]}",
                " | ".join(run.interpretation.get("highlights", [])[:2]),
                run.interpretation.get("generated_by", "heuristic"), started,
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

    # -- Auto-tune: try hyperparameter combinations for every model -------------
    def run_autotune(
        self, run: Run, target: str | None, time_column: str | None,
        n_candidates: int | None = None,
    ) -> Run:
        if not run.recommendation:
            raise ValueError("Approve the EDA first so a use case is chosen.")
        use_case = run.recommendation["use_case"]
        started = time.time()

        node = DecisionNode(stage="autotune", title=f"Auto-tune {use_case} models")
        run.decisions.append(node)

        result = run_autotune_sweep(
            run.df, use_case, target, time_column,
            run.recommendation.get("model_configs", {}),
            n_candidates=n_candidates,
        )
        run.autotune = result

        # Fold the tuned settings back into the suggestions the UI pre-fills.
        cfgs = run.recommendation.setdefault("model_configs", {})
        tuned_summary = []
        for key, r in result["models"].items():
            if r["error"] is None and r["best_score"] is not None:
                cfgs[key] = {
                    "hyperparams": r["best_hyperparams"],
                    "rationale": (
                        f"Auto-tuned: best of {r['n_tried']} tried combinations "
                        f"({result['metric']} {r['best_score']} vs {r['suggested_score']} suggested"
                        + (f", +{r['improvement_pct']}% better" if (r["improvement_pct"] or 0) > 0 else "")
                        + ")."
                    ),
                }
                tuned_summary.append(f"{r['model_name']}: {result['metric']}={r['best_score']}")

        node.status = "done"
        node.detail = f"Tried combinations for {len(result['models'])} models; tuned settings applied."
        self._log(
            run, "Auto-tuner", f"Searched settings for all {use_case} models",
            "; ".join(tuned_summary) or "No valid scores produced.",
            f"Sampled combinations around the suggested settings, validated on held-out data, ranked by {result['metric']}.",
            "deterministic", started,
        )
        return run

    # -- Stage: compare all models of the use case ------------------------------
    def compare(self, run: Run, target: str | None, time_column: str | None) -> Run:
        if not run.recommendation:
            raise ValueError("Approve the EDA first so a use case is chosen.")
        use_case = run.recommendation["use_case"]
        suggestions = run.recommendation.get("model_configs", {})
        metric_key, higher_better = PRIMARY_METRIC[use_case]
        started_cmp = time.time()

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
        self._log(
            run, "Model runner", f"Compared all {use_case} models",
            "; ".join(f"{r['model_name']}: {metric_key}={r['metrics'].get(metric_key)}" for r in rows),
            f"Ranked by {metric_key} ({'higher' if higher_better else 'lower'} wins); winner: {best['model_name'] if best else 'none'}.",
            "deterministic", started_cmp,
        )
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
                "If two models score similarly, prefer the simpler one - it is easier to trust and explain.",
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
                    "Only cite numbers present in the input. Style rule: use plain "
                    "hyphens (-) only; never use em dashes or en dashes in your output."
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
