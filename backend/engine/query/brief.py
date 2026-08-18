"""Query decision brief (P2.4): selected answers -> a defensible document.

Every plan is RE-EXECUTED at brief time (deterministic - the numbers in the
document are the numbers in the data), every phrased claim is verified by a
deterministic critic against the computed tables and signals, and the trust
panel is data-quality-only - it says explicitly that no model stability tier
applies because nothing was modeled.
"""
from __future__ import annotations

import re
from typing import Any

_NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*")


def _claim_numbers(text: str) -> list[float]:
    out = []
    for m in _NUM_RE.findall(text or ""):
        try:
            out.append(float(m.replace(",", "")))
        except ValueError:
            pass
    return out


def _allowed_values(table: list[dict], signals: dict[str, Any],
                    row_counts: list[dict]) -> set[float]:
    vals: set[float] = set()
    for row in table:
        for v in row.values():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                vals.add(round(float(v), 2))
            elif isinstance(v, str):
                vals.update(_claim_numbers(v))  # period labels like 2025-04
    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            for v in node.values():
                _walk(v)
        elif isinstance(node, (int, float)) and not isinstance(node, bool):
            vals.add(round(float(node), 2))
        elif isinstance(node, str):
            vals.update(_claim_numbers(node))
    _walk(signals or {})
    for rc in row_counts or []:
        vals.add(float(rc.get("rows", -1)))
    return vals


def _matches(claim: float, allowed: set[float]) -> bool:
    if claim in allowed or round(claim, 2) in allowed:
        return True
    for a in allowed:
        if a == 0:
            continue
        # rounding in prose: 4,076 -> "about 4,100"; shares to whole percents
        if abs(claim - a) <= max(0.51, abs(a) * 0.006):
            return True
        # compact prose: "3.6k" / "1.2 million"
        if abs(claim * 1000 - a) <= abs(a) * 0.03 or abs(claim * 1_000_000 - a) <= abs(a) * 0.03:
            return True
    # small counts ("top 5", "five districts") up to 31 are structural
    return claim.is_integer() and 0 <= claim <= 31


def verify_claim(text: str, table: list[dict], signals: dict[str, Any],
                 row_counts: list[dict]) -> dict[str, Any]:
    """The deterministic critic: every number in a phrased claim must exist
    in the computed table, the signals, or the row counts."""
    allowed = _allowed_values(table, signals, row_counts)
    unmatched = [n for n in _claim_numbers(text) if not _matches(n, allowed)]
    return {"verified": not unmatched, "unmatched_numbers": unmatched[:5]}


def brief_markdown(brief: dict[str, Any]) -> str:
    """Render the stored brief as markdown - the single source the PDF,
    the download and the read-only view all derive from."""
    b = brief
    lines = [f"# {b['title']}", ""]
    lines += [f"_Prepared {b['created_at']} from {b['filename']} - every number "
              f"recomputed from the data at export time._", ""]
    if b.get("takeaway"):
        lines += ["## What to take away", b["takeaway"], ""]
    lines += ["## Findings", ""]
    for i, item in enumerate(b["items"], 1):
        lines.append(f"### {i}. {item['question']}")
        lines.append("")
        lines.append(f"**{item['headline']}**")
        lines.append("")
        if item.get("meaning"):
            lines.append(f"_{item['meaning']}_")
            lines.append("")
        if not item["review"]["verified"]:
            lines.append("- [!] The critic could not verify every number in the "
                         "original phrasing; a computed restatement is shown.")
        for c in item.get("caveats", [])[:4]:
            lines.append(f"- Caveat: {c}")
        table = item.get("table") or []
        if table:
            cols = list(table[0].keys())
            lines.append("")
            lines.append("| " + " | ".join(cols) + " |")
            lines.append("|" + "---|" * len(cols))
            for row in table[:15]:
                lines.append("| " + " | ".join(str(row.get(c, "")) for c in cols) + " |")
        lines.append("")
    lines += ["## How each answer was computed", ""]
    for i, item in enumerate(b["items"], 1):
        lines.append(f"{i}. " + " ".join(item.get("sentences", [])))
    lines.append("")
    lines += ["", "## Data trust panel", ""]
    for t in b["trust"]["lines"]:
        lines.append(f"- {t}")
    lines += ["", f"_{b['trust']['scope_note']}_", ""]
    lines += ["---",
              f"_Provenance: dataset {b['provenance']['artifact_id'] or b['provenance']['dataset_id']}; "
              f"phrasing mode: {b['provenance']['generated_by']}; plans stored with this "
              f"brief; every execution is in the activity log._"]
    return "\n".join(lines)
