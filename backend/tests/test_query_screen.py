"""P1.6 acceptance: the ask loop end-to-end through the API (heuristic
mode for determinism), with events, caveats, gating and route choice."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from app.config import settings
settings.anthropic_api_key = ""  # heuristic mode: deterministic + free

tmp = Path(tempfile.mkdtemp())
import app.store as store_mod
from app.store import Store
test_store = Store(db_path=tmp / "qs.db")
store_mod.store = test_store
import app.api.routes_activity as ra
import app.api.routes_datasets as rd
import app.api.routes_intake as ri
import app.api.routes_query as rq
import app.api.routes_registry as rr
import app.api.routes_runs as rruns
import app.api.routes_projects as rp
import app.telemetry as tel
for mod in (rd, ri, rq, rr, rruns, rp, ra, tel):
    if hasattr(mod, "store"):
        mod.store = test_store
from fastapi.testclient import TestClient
from app.main import app
client = TestClient(app)


def _fixture_csv() -> bytes:
    rows = []
    rng = np.random.default_rng(42)
    for m in ["2026-01", "2026-02", "2026-04"]:  # March gap
        for d in ["Pune", "Nashik", "Satara"]:
            rows.append({"District": d, "Month": m, "Enrollment": int(rng.integers(50, 500))})
    return pd.DataFrame(rows).to_csv(index=False).encode()


proj = client.post("/api/projects", json={"name": "QS", "description": ""}).json()
pid = proj["id"]
up = client.post("/api/datasets", files={"file": ("districts.csv", _fixture_csv(), "text/csv")},
                 data={"project_id": pid, "assembly": "standalone"}).json()
ds_id = up["dataset_id"]


def test_plan_interpret_run_loop():
    r = client.post(f"/api/datasets/{ds_id}/query/plan",
                    json={"question": "top 2 district by enrollment"})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["mode"] == "plan" and p["generated_by"] == "heuristic"
    cand = p["plans"][0]
    assert cand["sentences"][0].startswith("Take '")
    assert any("first 2 rows" in s for s in cand["sentences"])

    run = client.post(f"/api/datasets/{ds_id}/query/run",
                      json={"plan": cand["plan"], "question": "top 2 district by enrollment"})
    assert run.status_code == 200, run.text
    a = run.json()
    assert len(a["result"]["table"]) == 2
    assert a["headline"]
    assert a["result"]["row_counts"][0]["rows"] == 9
    # readiness caveat: the Month gap touches Enrollment? gap columns=[Month];
    # this plan does not use Month, so gap caveat must NOT fire here.
    assert not any("Gaps in 'Month'" in c for c in a["caveats"])


def test_caveats_attach_when_touching_flagged_columns():
    r = client.post(f"/api/datasets/{ds_id}/query/plan",
                    json={"question": "total enrollment last 2 months"})
    cand = r.json()["plans"][0]
    a = client.post(f"/api/datasets/{ds_id}/query/run",
                    json={"plan": cand["plan"], "question": "total enrollment last 2 months"}).json()
    assert any("Gaps in 'Month'" in c for c in a["caveats"]), a["caveats"]
    assert any("last 2 of 3 periods" in c for c in a["caveats"])


def test_clarify_and_events_order():
    r = client.post(f"/api/datasets/{ds_id}/query/plan",
                    json={"question": "summarize the overall vibes please"})
    assert r.json()["mode"] == "clarify"
    ev = client.get(f"/api/activity?project_id={pid}&limit=100").json()["events"]
    types = [e["event_type"] for e in ev]
    assert "query_plan" in types and "query_execute" in types
    # run click logged as approval with the query_run gate
    assert any(e["event_type"] == "approval" and (e.get("payload") or {}).get("gate") == "query_run"
               for e in ev)
    # order: a query_plan precedes the first query_execute (list is newest-first)
    first_exec = max(i for i, t in enumerate(types) if t == "query_execute")
    assert any(t == "query_plan" for t in types[first_exec:]), "plan must precede execute"


def test_pii_gate_applies():
    pii_df = pd.DataFrame({"name": ["A Kumar", "B Singh"] * 10,
                           "mobile": [f"+91 9{n}00000000"[:14] for n in range(20)],
                           "amount": range(20)})
    up2 = client.post("/api/datasets", files={"file": ("pii.csv", pii_df.to_csv(index=False).encode(), "text/csv")},
                      data={"project_id": pid, "assembly": "standalone"}).json()
    assert up2["pii_status"] == "pending"
    r = client.post(f"/api/datasets/{up2['dataset_id']}/query/plan", json={"question": "how many rows"})
    assert r.status_code == 409


def test_route_choice_logged():
    run = client.post("/api/runs", json={"dataset_id": ds_id, "question": "top districts by enrollment"}).json()
    rc = client.post(f"/api/runs/{run['id']}/route-choice", json={"choice": "direct_query"})
    assert rc.status_code == 200
    ev = client.get(f"/api/activity?project_id={pid}&event_type=approval&limit=20").json()["events"]
    assert any((e.get("payload") or {}).get("gate") == "route" for e in ev)


def test_bad_plan_rejected():
    r = client.post(f"/api/datasets/{ds_id}/query/run",
                    json={"plan": {"source": "x", "steps": [{"op": "filter", "column": "nope",
                                                            "operator": "==", "value": "y"}]},
                          "question": "x"})
    assert r.status_code == 400 and "No column called 'nope'" in r.json()["detail"]
    # a NEAR miss gets did-you-mean
    r2 = client.post(f"/api/datasets/{ds_id}/query/run",
                     json={"plan": {"source": "x", "steps": [{"op": "filter", "column": "Distric",
                                                             "operator": "==", "value": "Pune"}]},
                           "question": "x"})
    assert r2.status_code == 400 and "Did you mean 'District'" in r2.json()["detail"]


if __name__ == "__main__":
    for fn in [test_plan_interpret_run_loop, test_caveats_attach_when_touching_flagged_columns,
               test_clarify_and_events_order, test_pii_gate_applies,
               test_route_choice_logged, test_bad_plan_rejected]:
        fn()
        print(f"PASS  {fn.__name__}")
    print("\nquery-screen tests passed")
