"""Run-vs-run comparison: what changed between two analyses of the same kind.

Deterministic deltas - data (rows, period coverage, per-column PSI drift),
settings, metrics, findings (driver rankings, segments, forecast direction) -
plus a plain-language narrative (one LLM call, template fallback) and a
markdown export.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

PSI_BINS = 10
PSI_STABLE = 0.1
PSI_MODERATE = 0.25


def psi(a: pd.Series, b: pd.Series, bins: int = PSI_BINS) -> float | None:
    """Population stability index of b vs a (0 = identical distribution)."""
    qa = pd.to_numeric(a, errors="coerce").dropna()
    qb = pd.to_numeric(b, errors="coerce").dropna()
    if len(qa) < 20 or len(qb) < 20:
        return None
    edges = np.unique(np.quantile(qa, np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:
        return None
    edges = edges.astype(float)
    edges[0], edges[-1] = -np.inf, np.inf
    pa = np.histogram(qa, bins=edges)[0] / len(qa)
    pb = np.histogram(qb, bins=edges)[0] / len(qb)
    pa = np.clip(pa, 1e-4, None)
    pb = np.clip(pb, 1e-4, None)
    return float(np.sum((pb - pa) * np.log(pb / pa)))


def _shift_label(v: float) -> str:
    return "stable" if v < PSI_STABLE else "moderate shift" if v < PSI_MODERATE else "major shift"


def _period(df: pd.DataFrame, time_column: str | None) -> list[str] | None:
    if not time_column or time_column not in df.columns:
        return None
    ts = pd.to_datetime(df[time_column], errors="coerce", format="mixed").dropna()
    if ts.empty:
        return None
    return [str(ts.min().date()), str(ts.max().date())]


def diff_runs(run_a: Any, run_b: Any) -> dict[str, Any]:
    """Both runs must be completed and share a use case (caller enforces)."""
    cfg_a, cfg_b = run_a.config or {}, run_b.config or {}
    use_case = cfg_a.get("use_case")

    # Data delta: rows, period coverage, distribution shift on shared numerics
    shared_numeric = [
        c for c in run_a.df.columns
        if c in run_b.df.columns and pd.api.types.is_numeric_dtype(run_a.df[c])
        and run_a.df[c].nunique() > 2
    ]
    drift = []
    for col in shared_numeric[:15]:
        v = psi(run_a.df[col], run_b.df[col])
        if v is not None:
            drift.append({"column": str(col), "psi": round(v, 4), "label": _shift_label(v)})
    drift.sort(key=lambda d: -d["psi"])

    data = {
        "rows": [int(len(run_a.df)), int(len(run_b.df))],
        "period_a": _period(run_a.df, cfg_a.get("time_column")),
        "period_b": _period(run_b.df, cfg_b.get("time_column")),
        "drift": drift,
    }

    # Settings delta
    hp_a, hp_b = cfg_a.get("hyperparams") or {}, cfg_b.get("hyperparams") or {}
    hp_delta = {
        k: [hp_a.get(k), hp_b.get(k)]
        for k in sorted(set(hp_a) | set(hp_b)) if hp_a.get(k) != hp_b.get(k)
    }
    settings = {
        "model": [cfg_a.get("model_name"), cfg_b.get("model_name")],
        "target": [cfg_a.get("target"), cfg_b.get("target")],
        "hyperparams": hp_delta,
        "excluded": [cfg_a.get("excluded") or [], cfg_b.get("excluded") or []],
        "engineered": [
            [s["label"] for s in cfg_a.get("engineered") or []],
            [s["label"] for s in cfg_b.get("engineered") or []],
        ],
    }

    # Metric delta on shared numeric metrics
    m_a = (run_a.result or {}).get("metrics") or {}
    m_b = (run_b.result or {}).get("metrics") or {}
    metrics = {}
    for k in sorted(set(m_a) & set(m_b)):
        va, vb = m_a.get(k), m_b.get(k)
        if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
            metrics[k] = {"a": va, "b": vb, "delta": round(vb - va, 4)}

    # Findings delta
    ins_a, ins_b = run_a.insights or {}, run_b.insights or {}
    drivers_a = [d.get("label") or d["feature"] for d in ins_a.get("drivers") or []]
    drivers_b = [d.get("label") or d["feature"] for d in ins_b.get("drivers") or []]
    findings: dict[str, Any] = {
        "drivers": {
            "a": drivers_a, "b": drivers_b,
            "entered": [d for d in drivers_b if d not in drivers_a],
            "dropped": [d for d in drivers_a if d not in drivers_b],
            "top_changed": bool(drivers_a and drivers_b and drivers_a[0] != drivers_b[0]),
        },
    }
    if use_case == "clustering":
        findings["segments"] = {
            "a": len([s for s in ins_a.get("segments") or [] if s.get("cluster") != -1]),
            "b": len([s for s in ins_b.get("segments") or [] if s.get("cluster") != -1]),
        }
    if use_case == "forecasting":
        findings["direction"] = {
            "a": (ins_a.get("outlook") or {}).get("direction"),
            "b": (ins_b.get("outlook") or {}).get("direction"),
        }

    return {
        "use_case": use_case,
        "a": {"run_id": run_a.id, "filename": run_a.filename, "question": run_a.question,
              "created_at": run_a.created_at, "trust_tier": ins_a.get("trust_tier")},
        "b": {"run_id": run_b.id, "filename": run_b.filename, "question": run_b.question,
              "created_at": run_b.created_at, "trust_tier": ins_b.get("trust_tier")},
        "data": data,
        "settings": settings,
        "metrics": metrics,
        "findings": findings,
    }


def narrative_template(diff: dict[str, Any]) -> str:
    bits: list[str] = []
    ra, rb = diff["data"]["rows"]
    bits.append(f"The second analysis used {rb:,} rows vs {ra:,} before"
                + (f" ({rb - ra:+,})." if rb != ra else " (same size)."))
    major = [d for d in diff["data"]["drift"] if d["label"] != "stable"]
    if major:
        bits.append("Distribution shifts: " + ", ".join(
            f"{d['column']} ({d['label']}, PSI {d['psi']})" for d in major[:3]) + ".")
    else:
        bits.append("Shared columns kept essentially the same distributions.")
    hp = diff["settings"]["hyperparams"]
    if diff["settings"]["model"][0] != diff["settings"]["model"][1]:
        bits.append(f"The model changed from {diff['settings']['model'][0]} to {diff['settings']['model'][1]}.")
    elif hp:
        bits.append("Settings changed: " + ", ".join(f"{k} {a} to {b}" for k, (a, b) in list(hp.items())[:3]) + ".")
    prim = {"classification": "f1", "regression": "rmse", "clustering": "silhouette",
            "forecasting": "mape_pct"}.get(diff["use_case"] or "", "")
    if prim in diff["metrics"]:
        m = diff["metrics"][prim]
        bits.append(f"{prim} moved from {m['a']} to {m['b']} ({m['delta']:+}).")
    dr = diff["findings"]["drivers"]
    if dr["top_changed"]:
        bits.append(f"The top driver changed from '{dr['a'][0]}' to '{dr['b'][0]}' - "
                    "worth understanding before acting on either.")
    if (d := diff["findings"].get("direction")) and d["a"] != d["b"]:
        bits.append(f"The outlook direction changed from {d['a']} to {d['b']}.")
    return " ".join(bits)


def to_markdown(diff: dict[str, Any], narrative: str) -> str:
    lines = ["# Run comparison", ""]
    lines += [f"- **A:** {diff['a']['filename']} - {diff['a']['question'] or '(no question)'} ({diff['a']['run_id']})"]
    lines += [f"- **B:** {diff['b']['filename']} - {diff['b']['question'] or '(no question)'} ({diff['b']['run_id']})", ""]
    lines += ["## What changed and what it means", "", narrative, ""]
    lines += ["## Data", "", f"Rows: {diff['data']['rows'][0]:,} -> {diff['data']['rows'][1]:,}"]
    if diff["data"]["drift"]:
        lines += ["", "| Column | PSI | Shift |", "|---|---|---|"]
        lines += [f"| {d['column']} | {d['psi']} | {d['label']} |" for d in diff["data"]["drift"]]
    lines += ["", "## Metrics", "", "| Metric | A | B | Delta |", "|---|---|---|---|"]
    lines += [f"| {k} | {m['a']} | {m['b']} | {m['delta']:+} |" for k, m in diff["metrics"].items()]
    hp = diff["settings"]["hyperparams"]
    if hp:
        lines += ["", "## Settings changes", ""]
        lines += [f"- {k}: {a} -> {b}" for k, (a, b) in hp.items()]
    dr = diff["findings"]["drivers"]
    if dr["a"] or dr["b"]:
        lines += ["", "## Drivers", "", f"- A: {', '.join(dr['a']) or '-'}", f"- B: {', '.join(dr['b']) or '-'}"]
        if dr["entered"]:
            lines += [f"- New in B: {', '.join(dr['entered'])}"]
        if dr["dropped"]:
            lines += [f"- No longer prominent: {', '.join(dr['dropped'])}"]
    return "\n".join(lines)
