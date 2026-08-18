"""Deterministic reading signals for explore findings.

The analyst agent must never compute - so every number it is allowed to
reason about (shares, ratios, trend changes, peaks) is computed HERE in
Python from the executed result. The LLM only judges and phrases them
(rule 11); the same signals feed the templated fallback meanings.
"""
from __future__ import annotations

from typing import Any


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def finding_signals(result: dict[str, Any], chart: dict[str, Any]) -> dict[str, Any]:
    """-> a small dict of computed facts about one finding's result."""
    table = result.get("table") or []
    if not table:
        return {"kind": "empty"}
    kind = chart.get("kind")
    x = chart.get("x")
    ys = chart.get("y") or []
    y = ys[0] if ys else None

    if kind in ("hbar", "bar") and x and y:
        vals = [(str(r.get(x)), _num(r.get(y))) for r in table]
        vals = [(n, v) for n, v in vals if v is not None]
        if not vals:
            return {"kind": "empty"}
        total = sum(v for _, v in vals)
        top_name, top_val = max(vals, key=lambda t: t[1])
        low_name, low_val = min(vals, key=lambda t: t[1])
        return {
            "kind": "ranked",
            "groups_shown": len(vals),
            "top": top_name,
            "top_value": round(top_val, 2),
            "bottom": low_name,
            "bottom_value": round(low_val, 2),
            "top_share_pct": round(top_val / total * 100, 1) if total else None,
            "top_vs_bottom_ratio": round(top_val / low_val, 1) if low_val else None,
        }

    if kind == "line" and x and y:
        pts = [(str(r.get(x)), _num(r.get(y))) for r in table]
        pts = [(n, v) for n, v in pts if v is not None]
        if len(pts) < 2:
            return {"kind": "empty"}
        first_label, first = pts[0]
        last_label, last = pts[-1]
        peak_label, peak = max(pts, key=lambda t: t[1])
        trough_label, trough = min(pts, key=lambda t: t[1])
        return {
            "kind": "trend",
            "periods": len(pts),
            "first_period": first_label,
            "first_value": round(first, 2),
            "last_period": last_label,
            "last_value": round(last, 2),
            "change_pct": round((last - first) / abs(first) * 100, 1) if first else None,
            "peak_period": peak_label,
            "peak_value": round(peak, 2),
            "trough_period": trough_label,
            "trough_value": round(trough, 2),
        }

    if kind == "kpi":
        return {
            "kind": "kpi",
            "values": {c: table[0].get(c) for c in ys if c in table[0]},
        }

    return {"kind": "table", "rows": len(table)}


def plain_meaning(sig: dict[str, Any]) -> str:
    """Templated fallback: what a finding suggests, from its signals only."""
    kind = sig.get("kind")
    if kind == "ranked":
        share = sig.get("top_share_pct")
        ratio = sig.get("top_vs_bottom_ratio")
        if ratio is not None and ratio >= 3:
            return (f"{sig['top']} is about {ratio}x {sig['bottom']} - a gap this "
                    f"wide usually has a reason worth checking (size, funding, "
                    f"reporting differences).")
        if ratio is not None and ratio >= 1.5:
            return (f"{sig['top']} leads clearly"
                    + (f" with roughly {share}% of the shown total" if share else "")
                    + f", while {sig['bottom']} trails - worth asking what "
                    f"separates them.")
        return (f"The {sig.get('groups_shown', '')} groups shown sit close "
                f"together - no single one dominates, so differences here are "
                f"unlikely to be the main story.")
    if kind == "trend":
        chg = sig.get("change_pct")
        direction = ("held roughly steady" if chg is None or abs(chg) < 10
                     else ("risen" if chg > 0 else "fallen"))
        out = f"Across {sig['periods']} periods the total has {direction}"
        if chg is not None and abs(chg) >= 10:
            out += f" ({chg:+.0f}% from {sig['first_period']} to {sig['last_period']})"
        out += (f"; the peak came in {sig['peak_period']} and the low point in "
                f"{sig['trough_period']}. One-off spikes and dips are worth a "
                f"closer look before reading them as a trend.")
        return out
    if kind == "kpi":
        return ("Treat these as the baseline figures for this file - every "
                "comparison you ask for next is judged against them.")
    return "Open the numbers to read this one directly - it did not fit a standard reading."


def plain_synthesis(findings: list[dict[str, Any]]) -> str:
    """Templated fallback for the whole-board takeaway, from signals only."""
    ranked = next((f["signals"] for f in findings
                   if f.get("signals", {}).get("kind") == "ranked"), None)
    trend = next((f["signals"] for f in findings
                  if f.get("signals", {}).get("kind") == "trend"), None)
    parts: list[str] = []
    if ranked:
        parts.append(f"The clearest split is between {ranked['top']} (highest) "
                     f"and {ranked['bottom']} (lowest)")
    if trend:
        chg = trend.get("change_pct")
        if chg is not None and abs(chg) >= 10:
            parts.append(f"and the overall level has moved {chg:+.0f}% across "
                         f"the observed periods")
        else:
            parts.append("while the overall level has stayed roughly flat "
                         "over time")
    lead = (" ".join(parts) + "." if parts
            else "The starter questions cover totals, rankings and counts.")
    ask = (f"A good next question: why does {ranked['top']} lead {ranked['bottom']} - "
           f"is it size, funding or reporting?" if ranked
           else "Ask a question below to dig into any of these findings.")
    return f"{lead} {ask}"
