"""Markdown analysis report assembled from a run."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from engine.orchestrator import Run


def _metrics_table(metrics: dict[str, Any]) -> str:
    rows = [(k.replace("_", " "), v) for k, v in metrics.items() if v is not None]
    if not rows:
        return "_No metrics recorded._"
    head = "| Metric | Value |\n|---|---|"
    body = "\n".join(f"| {k} | {v} |" for k, v in rows)
    return f"{head}\n{body}"


def build_report(run: Run) -> str:
    lines: list[str] = []
    add = lines.append

    add("# Decision Brief")
    add("")
    add(f"- **Dataset:** {run.filename}")
    if run.profile:
        add(f"- **Size:** {run.profile['n_rows']:,} rows × {run.profile['n_cols']} columns")
    add(f"- **Question:** {run.question or '(not specified)'}")
    add(f"- **Run ID:** {run.id}")
    add(f"- **Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    add("")

    # ---- Decision-ready content first -------------------------------------
    if run.insights:
        ins = run.insights
        brief = ins.get("brief", {})
        ev = ins.get("evidence", {})

        if brief.get("executive_summary"):
            add("## Executive summary")
            add("")
            add(brief["executive_summary"])
            add("")

        if ins.get("findings"):
            add("## Key findings")
            add("")
            for f in ins["findings"]:
                add(f"### {f['headline']}")
                add("")
                add(f.get("detail", ""))
                add("")

        if ins.get("segments"):
            add("## Segment profiles")
            add("")
            for s in ins["segments"]:
                traits = "; ".join(
                    f"{t['feature']} {t['direction']} avg ({t['value']} vs {t['overall']})"
                    for t in s.get("traits", [])
                ) or "—"
                add(f"- **{s['name']}** — {s['share_pct']}% ({s['count']:,} records): {traits}")
            add("")

        if brief.get("recommended_actions"):
            add("## Recommended actions")
            add("")
            for i, a in enumerate(brief["recommended_actions"], 1):
                add(f"{i}. {a}")
            add("")

        add("## How much to trust this")
        add("")
        add(f"**Evidence strength: {ev.get('level', 'unknown')}** — {ev.get('reason', '')}")
        add("")
        for c in list(ev.get("caveats", [])) + list(brief.get("watch_outs", [])):
            add(f"- {c}")
        add("")
        add("---")
        add("")
        add("# Technical appendix")
        add("")

    if run.eda:
        add("## Data exploration (EDA)")
        add("")
        add(run.eda.get("summary", ""))
        add("")
        for f in run.eda.get("key_findings", []):
            add(f"- {f}")
        add("")

    if run.recommendation:
        add("## Agent recommendation")
        add("")
        add(f"- **Use case:** {run.recommendation['use_case']}")
        if run.recommendation.get("target"):
            add(f"- **Target column:** {run.recommendation['target']}")
        add("")
        add(run.recommendation.get("reasoning", ""))
        add("")

    if run.comparison:
        comp = run.comparison
        add("## Model comparison")
        add("")
        metric = comp["primary_metric"].replace("_", " ")
        direction = "higher is better" if comp["higher_is_better"] else "lower is better"
        add(f"Models ranked by **{metric}** ({direction}).")
        add("")
        keys: list[str] = []
        for r in comp["results"]:
            for k in r["metrics"]:
                if k not in keys:
                    keys.append(k)
        head = "| Rank | Model | " + " | ".join(k.replace("_", " ") for k in keys) + " | Status |"
        sep = "|---" * (len(keys) + 3) + "|"
        add(head)
        add(sep)
        for i, r in enumerate(comp["results"], 1):
            vals = " | ".join(str(r["metrics"].get(k, "—")) for k in keys)
            status = "❌ " + r["error"] if r["error"] else ("🏆 best" if r["model_key"] == comp["best_model"] else "ok")
            add(f"| {i} | {r['model_name']} | {vals} | {status} |")
        add("")
        interp = comp.get("interpretation", {})
        if interp.get("summary"):
            add(interp["summary"])
            add("")

    if run.config and run.result:
        add(f"## Final model: {run.config['model_name']}")
        add("")
        add("**Configuration:**")
        add("")
        for k, v in run.config.get("hyperparams", {}).items():
            add(f"- {k}: `{v}`")
        add("")
        add("**Results:**")
        add("")
        add(_metrics_table(run.result["metrics"]))
        add("")

    if run.interpretation:
        add("## Interpretation")
        add("")
        add(run.interpretation.get("summary", ""))
        add("")
        if run.interpretation.get("highlights"):
            add("**Highlights**")
            add("")
            for h in run.interpretation["highlights"]:
                add(f"- {h}")
            add("")
        if run.interpretation.get("next_steps"):
            add("**Suggested next steps**")
            add("")
            for s in run.interpretation["next_steps"]:
                add(f"- {s}")
            add("")

    add("## Decision log")
    add("")
    add("| Stage | Status | Detail |")
    add("|---|---|---|")
    for d in run.decisions:
        add(f"| {d.title} | {d.status} | {d.detail} |")
    add("")
    add("---")
    add("_Generated by Agentic ML Workbench._")
    return "\n".join(lines)
