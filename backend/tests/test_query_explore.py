"""Analytics road: starter questions, chart mapping, explore + export APIs."""
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
test_store = Store(db_path=tmp / "qe.db")
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

from engine.query.executor import execute_plan
from engine.query.plan import QueryPlan
from engine.query.resolve import resolve_plan
from engine.query.starter import starter_questions
from engine.query.vizmap import choose_chart

client = TestClient(app)


def _df() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    districts = ["Pune", "Nashik", "Satara", "Nagpur", "Amravati"]
    return pd.DataFrame({
        "district": rng.choice(districts, 60),
        "scheme": rng.choice(["A", "B"], 60),
        "month": pd.date_range("2024-01-01", periods=60, freq="D").astype(str),
        "enrollment": rng.integers(50, 500, 60),
        "budget": rng.uniform(1e4, 9e4, 60).round(2),
    })


proj = client.post("/api/projects", json={"name": "QE", "description": ""}).json()
pid = proj["id"]
up = client.post(
    "/api/datasets",
    files={"file": ("gov.csv", _df().to_csv(index=False).encode(), "text/csv")},
    data={"project_id": pid, "assembly": "standalone"},
).json()
ds_id = up["dataset_id"]


# ---------- starter questions ----------

def test_starters_generate_and_execute():
    df = _df()
    cands = starter_questions(df, "a1")
    assert 1 <= len(cands) <= 5
    for cand in cands:
        plan = resolve_plan(QueryPlan.model_validate(cand["plan"]),
                            [str(c) for c in df.columns])
        result = execute_plan(plan, df)
        assert result["table"], cand["question"]


def test_starters_lead_with_categorical_ranking():
    cands = starter_questions(_df(), "a1")
    assert "highest total" in cands[0]["question"]


def test_starters_numeric_only_frame():
    df = pd.DataFrame({"x": range(20), "y": np.linspace(0, 5, 20)})
    cands = starter_questions(df, "a1")
    assert len(cands) >= 1
    for cand in cands:
        plan = resolve_plan(QueryPlan.model_validate(cand["plan"]),
                            [str(c) for c in df.columns])
        assert execute_plan(plan, df)["table"]


def test_starters_empty_for_unusable_frame():
    df = pd.DataFrame({"id": [f"row{i}" for i in range(9)]})
    assert starter_questions(df, "a1") == []


# ---------- chart mapping (deterministic, rule 14) ----------

def _run_plan(df: pd.DataFrame, plan_dict: dict):
    plan = resolve_plan(QueryPlan.model_validate(plan_dict),
                        [str(c) for c in df.columns])
    return execute_plan(plan, df), plan


def test_chart_topn_is_hbar():
    df = _df()
    result, plan = _run_plan(df, {"source": "a1", "steps": [
        {"op": "group_by", "columns": ["district"]},
        {"op": "aggregate", "column": "enrollment", "fn": "sum", "alias": "total"},
        {"op": "sort", "column": "total", "dir": "desc"},
        {"op": "top_n", "n": 3},
    ]})
    spec = choose_chart(result, plan)
    assert spec["kind"] == "hbar"
    assert spec["x"] == "district" and spec["y"] == ["total"]


def test_chart_time_axis_is_line():
    df = _df()
    result, plan = _run_plan(df, {"source": "a1", "steps": [
        {"op": "group_by", "columns": ["month"]},
        {"op": "aggregate", "column": "budget", "fn": "sum", "alias": "total"},
        {"op": "sort", "column": "month", "dir": "asc"},
    ]})
    assert choose_chart(result, plan)["kind"] == "line"


def test_chart_single_row_is_kpi():
    df = _df()
    result, plan = _run_plan(df, {"source": "a1", "steps": [
        {"op": "aggregate", "column": "budget", "fn": "sum", "alias": "total_budget"},
        {"op": "aggregate", "column": "budget", "fn": "mean", "alias": "avg_budget"},
    ]})
    spec = choose_chart(result, plan)
    assert spec["kind"] == "kpi"
    assert set(spec["y"]) == {"total_budget", "avg_budget"}


def test_chart_small_groups_is_bar():
    df = _df()
    result, plan = _run_plan(df, {"source": "a1", "steps": [
        {"op": "group_by", "columns": ["scheme"]},
        {"op": "aggregate", "column": "enrollment", "fn": "mean", "alias": "avg"},
    ]})
    assert choose_chart(result, plan)["kind"] == "bar"


def test_chart_threshold_filter_becomes_reference_line():
    df = _df()
    result, plan = _run_plan(df, {"source": "a1", "steps": [
        {"op": "group_by", "columns": ["district"]},
        {"op": "aggregate", "column": "enrollment", "fn": "sum", "alias": "total"},
        {"op": "filter", "column": "total", "operator": ">", "value": 3000},
        {"op": "sort", "column": "total", "dir": "desc"},
        {"op": "top_n", "n": 5},
    ]})
    spec = choose_chart(result, plan)
    assert spec["threshold"] == 3000.0


def test_chart_too_many_categories_falls_back_to_table():
    df = pd.DataFrame({
        "name": [f"unit_{i}" for i in range(80)],
        "value": np.arange(80, dtype=float),
    })
    result, plan = _run_plan(df, {"source": "a1", "steps": [
        {"op": "group_by", "columns": ["name"]},
        {"op": "aggregate", "column": "value", "fn": "sum", "alias": "total"},
    ]})
    spec = choose_chart(result, plan)
    assert spec["kind"] == "table"
    assert "80" in (spec["note"] or "")


# ---------- API: explore / export / path-choice ----------

def test_explore_endpoint_heuristic():
    r = client.post(f"/api/datasets/{ds_id}/explore")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["generated_by"] == "heuristic"
    assert len(body["findings"]) >= 3
    for f in body["findings"]:
        assert f["headline"]
        assert f["chart"]["kind"] in {"kpi", "bar", "hbar", "line", "table"}
        assert f["sentences"]
        assert f["result"]["table"]
    ev = client.get(f"/api/activity?project_id={pid}&limit=100").json()["events"]
    types = [e["event_type"] for e in ev]
    assert types.count("query_plan") >= len(body["findings"])
    assert "query_execute" in types


def test_query_export_csv_logged():
    plan = {"source": "a1", "steps": [
        {"op": "group_by", "columns": ["district"]},
        {"op": "aggregate", "column": "enrollment", "fn": "sum", "alias": "total"},
        {"op": "sort", "column": "total", "dir": "desc"},
    ]}
    r = client.post(f"/api/datasets/{ds_id}/query/export",
                    json={"plan": plan, "question": "totals by district"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "district" in r.text.splitlines()[0]
    ev = client.get(f"/api/activity?project_id={pid}&event_type=export&limit=20").json()["events"]
    assert any((e.get("payload") or {}).get("kind") == "query_answer" for e in ev)


def test_board_export_markdown():
    r = client.post(f"/api/datasets/{ds_id}/explore/export", json={"items": [{
        "question": "Which district leads?",
        "headline": "Pune leads.",
        "sentences": ["Group rows by district."],
        "table": [{"district": "Pune", "total": 410}],
    }]})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")
    assert "# Initial findings" in r.text
    assert "| district |" in r.text


def test_path_choice_logged():
    r = client.post(f"/api/datasets/{ds_id}/path-choice", json={"choice": "analytics"})
    assert r.status_code == 200
    ev = client.get(f"/api/activity?project_id={pid}&event_type=approval&limit=20").json()["events"]
    assert any((e.get("payload") or {}).get("gate") == "path" for e in ev)


def test_run_answer_includes_chart_and_plan():
    plan = {"source": "a1", "steps": [
        {"op": "group_by", "columns": ["district"]},
        {"op": "aggregate", "column": "enrollment", "fn": "sum", "alias": "total"},
        {"op": "sort", "column": "total", "dir": "desc"},
        {"op": "top_n", "n": 3},
    ]}
    r = client.post(f"/api/datasets/{ds_id}/query/run",
                    json={"plan": plan, "question": "top 3 districts"})
    assert r.status_code == 200, r.text
    a = r.json()
    assert a["chart"]["kind"] == "hbar"
    assert a["plan"]["steps"][0]["op"] == "group_by"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v) and k != "test_store"]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print("\nquery-explore tests passed")
