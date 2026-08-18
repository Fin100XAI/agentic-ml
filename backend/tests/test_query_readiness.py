"""Readiness audit: findings, remediation routing, and answer caveats."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from engine.query.readiness import caveats_for_columns, readiness_audit
from engine.remediation import fit_apply_fixes, propose_fixes, replay_fixes


def _fixture() -> pd.DataFrame:
    rows = []
    districts = ["Pune", "Nashik", "Satara"]
    months = ["2026-01", "2026-02", "2026-04", "2026-05"]  # March missing
    rng = np.random.default_rng(42)
    for m in months:
        for d in districts:
            name = "Nasik" if (d == "Nashik" and m == "2026-04") else d  # spelling drift
            rows.append({"District": name, "Month": m,
                         "Enrollment": int(rng.integers(50, 500))})
    # Satara missing entirely from the last month
    rows = [r for r in rows if not (r["District"] == "Satara" and r["Month"] == "2026-05")]
    return pd.DataFrame(rows)


def test_findings():
    audit = readiness_audit(_fixture())
    kinds = {f["kind"] for f in audit["findings"]}
    assert "period_gap" in kinds, kinds          # March gap
    assert "near_duplicates" in kinds, kinds     # Nashik / Nasik
    assert "key_incomplete" in kinds, kinds      # Satara missing a month
    spelling = next(f for f in audit["findings"] if f["kind"] == "near_duplicates")
    assert spelling["fixable"] and spelling["fix"]["mapping"] == {"Nasik": "Nashik"}
    assert audit["period_column"] == "Month" and audit["key_column"] == "District"


def test_duplicate_keys_detected():
    df = _fixture()
    df = pd.concat([df, df.head(2)], ignore_index=True)
    kinds = {f["kind"] for f in readiness_audit(df)["findings"]}
    assert "duplicate_keys" in kinds


def test_scale_jump_detected():
    df = _fixture()
    df.loc[df.Month >= "2026-04", "Enrollment"] *= 1000  # lakhs vs units
    kinds = {f["kind"] for f in readiness_audit(df)["findings"]}
    assert "scale_jump" in kinds


def test_harmonize_routes_into_remediation_and_replays():
    df = _fixture()
    proposals = propose_fixes(df)
    harm = [p for p in proposals if p["kind"] == "harmonize_values"]
    assert harm and harm[0]["mapping"] == {"Nasik": "Nashik"}
    fixed, fitted = fit_apply_fixes(df, proposals, [harm[0]["id"]])
    assert "Nasik" not in set(fixed["District"])
    assert fitted[harm[0]["id"]]["mapping"] == {"Nasik": "Nashik"}
    # replay on new data applies the same stored mapping
    new = pd.DataFrame({"District": ["Nasik", "Pune"], "Month": ["2026-06"] * 2,
                        "Enrollment": [10, 20]})
    replayed, notes = replay_fixes(new, proposals, [harm[0]["id"]], fitted)
    assert list(replayed["District"]) == ["Nashik", "Pune"] and notes == []


def test_declined_findings_become_answer_caveats():
    audit = readiness_audit(_fixture())
    caveats = caveats_for_columns(audit["findings"], ["month", "enrollment"])
    assert any("Gaps in 'Month'" in c for c in caveats)
    # a question not touching the affected columns carries no such caveat
    assert caveats_for_columns(audit["findings"], ["Enrollment"]) != caveats


def test_approving_fix_removes_finding():
    df = _fixture()
    proposals = propose_fixes(df)
    harm = next(p for p in proposals if p["kind"] == "harmonize_values")
    fixed, _ = fit_apply_fixes(df, proposals, [harm["id"]])
    kinds_after = {f["kind"] for f in readiness_audit(fixed)["findings"]}
    assert "near_duplicates" not in kinds_after


def test_health_carries_readiness_section():
    from engine.health import assess_health
    from engine.profiler import profile_dataframe
    df = _fixture()
    health = assess_health(df, profile_dataframe(df))
    assert "query_readiness" in health
    assert any(f["kind"] == "near_duplicates" for f in health["query_readiness"])


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\n{len(fns)} readiness tests passed")
