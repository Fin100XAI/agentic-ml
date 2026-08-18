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

from engine.query.diff import diff_plans
from engine.query.executor import execute_plan
from engine.query.plan import QueryPlan
from engine.query.resolve import resolve_plan
from engine.query.signals import finding_signals, plain_meaning, plain_synthesis
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
    assert 1 <= len(cands) <= 9
    for cand in cands:
        plan = resolve_plan(QueryPlan.model_validate(cand["plan"]),
                            [str(c) for c in df.columns])
        result = execute_plan(plan, df)
        assert result["table"], cand["question"]


def test_starters_cover_both_ends_and_second_measure():
    qs = [c["question"] for c in starter_questions(_df(), "a1")]
    assert any("highest total" in q for q in qs)
    assert any("lowest total" in q for q in qs)  # lagging groups matter
    # two numerics in the fixture -> a second-measure ranking appears
    joined = " ".join(qs)
    assert "enrollment" in joined and "budget" in joined


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


# ---------- follow-up plan diff (P2.3): silent drops must surface ----------

def _plan_of(*steps):
    return {"source": "a1", "steps": list(steps)}


def test_diff_dropped_filter_is_surfaced():
    prior = _plan_of(
        {"op": "filter", "column": "scheme", "operator": "==", "value": "A"},
        {"op": "group_by", "columns": ["district"]},
        {"op": "aggregate", "column": "enrollment", "fn": "sum", "alias": "t"},
    )
    new = _plan_of(
        {"op": "group_by", "columns": ["district"]},
        {"op": "aggregate", "column": "enrollment", "fn": "sum", "alias": "t"},
    )
    d = diff_plans(prior, new)
    assert d["removed"] == ["filter: scheme == A"]  # the wrong-answer risk
    assert d["added"] == [] and d["changed"] == []
    assert d["unchanged_count"] == 2


def test_diff_added_and_changed():
    prior = _plan_of(
        {"op": "group_by", "columns": ["district"]},
        {"op": "aggregate", "column": "enrollment", "fn": "sum", "alias": "t"},
        {"op": "sort", "column": "t", "dir": "desc"},
    )
    new = _plan_of(
        {"op": "filter", "column": "scheme", "operator": "==", "value": "A"},
        {"op": "group_by", "columns": ["month"]},
        {"op": "aggregate", "column": "enrollment", "fn": "sum", "alias": "t"},
        {"op": "sort", "column": "t", "dir": "desc"},
    )
    d = diff_plans(prior, new)
    assert any("scheme == A" in a for a in d["added"])
    assert any("grouping" in c and "month" in c for c in d["changed"])
    assert d["removed"] == []


def test_plan_endpoint_attaches_changes_and_route():
    r = client.post(f"/api/datasets/{ds_id}/query/plan",
                    json={"question": "top 3 district by enrollment"})
    cand = r.json()["plans"][0]
    assert "changes" not in cand  # first question: nothing to diff
    r2 = client.post(f"/api/datasets/{ds_id}/query/plan",
                     json={"question": "top 3 district by budget",
                           "prior_plan": cand["plan"]})
    body = r2.json()
    assert "route" in body
    cand2 = body["plans"][0]
    assert "changes" in cand2
    total = (len(cand2["changes"]["added"]) + len(cand2["changes"]["removed"])
             + len(cand2["changes"]["changed"]))
    assert total >= 1  # the metric changed


def test_prediction_question_gets_model_route():
    r = client.post(f"/api/datasets/{ds_id}/query/plan",
                    json={"question": "predict next month's enrollment"})
    assert r.json()["route"] in ("model_needed", "both")


# ---------- comparison finding: period-over-period delta ----------

def test_delta_starter_runs_and_maps_to_diverging_bars():
    df = _df()
    cands = starter_questions(df, "a1")
    delta = next((c for c in cands if "change from one" in c["question"]), None)
    assert delta is not None
    plan = resolve_plan(QueryPlan.model_validate(delta["plan"]),
                        [str(c) for c in df.columns])
    result = execute_plan(plan, df)
    spec = choose_chart(result, plan)
    assert spec["kind"] == "dbar"
    assert spec["y"][0].endswith("__delta")
    sig = finding_signals(result, spec)
    assert sig["kind"] == "delta"
    assert sig["rises"] + sig["falls"] >= 1
    assert "rose" in plain_meaning(sig)


# ---------- anomaly scout: IQR outliers inside signals ----------

def test_outlier_flagged_and_mentioned():
    table = [{"g": c, "t": v} for c, v in
             [("a", 100), ("b", 110), ("c", 95), ("d", 105), ("e", 102), ("f", 990)]]
    result = {"table": table, "columns": ["g", "t"], "dtypes": {"t": "int64"}}
    chart = {"kind": "bar", "x": "g", "y": ["t"], "threshold": None, "note": None}
    sig = finding_signals(result, chart)
    assert any(o["label"] == "f" and o["direction"] == "high" for o in sig["outliers"])
    assert "anomaly scout" in plain_meaning(sig).lower()


def test_no_outliers_on_flat_data():
    table = [{"g": c, "t": 100 + i} for i, c in enumerate("abcdef")]
    result = {"table": table, "columns": ["g", "t"], "dtypes": {"t": "int64"}}
    chart = {"kind": "bar", "x": "g", "y": ["t"], "threshold": None, "note": None}
    assert finding_signals(result, chart)["outliers"] == []


# ---------- analyst signals (computed in Python, phrased by the agent) ----------

def test_signals_ranked_and_meaning():
    result = {"table": [{"district": "Nagpur", "total": 4000},
                        {"district": "Pune", "total": 1000}],
              "columns": ["district", "total"], "dtypes": {"total": "int64"}}
    chart = {"kind": "hbar", "x": "district", "y": ["total"], "threshold": None, "note": None}
    sig = finding_signals(result, chart)
    assert sig["kind"] == "ranked"
    assert sig["top"] == "Nagpur" and sig["bottom"] == "Pune"
    assert sig["top_vs_bottom_ratio"] == 4.0
    assert sig["top_share_pct"] == 80.0
    meaning = plain_meaning(sig)
    assert "Nagpur" in meaning and "4" in meaning  # states the gap, no new math


def test_signals_trend():
    table = [{"m": f"2025-0{i+1}", "t": v} for i, v in enumerate([100, 120, 90, 150])]
    result = {"table": table, "columns": ["m", "t"], "dtypes": {"t": "int64"}}
    chart = {"kind": "line", "x": "m", "y": ["t"], "threshold": None, "note": None}
    sig = finding_signals(result, chart)
    assert sig["kind"] == "trend"
    assert sig["change_pct"] == 50.0
    assert sig["peak_period"] == "2025-04" and sig["trough_period"] == "2025-03"
    assert "risen" in plain_meaning(sig)


def test_synthesis_fallback_mentions_extremes():
    findings = [{"signals": {"kind": "ranked", "top": "Nagpur", "bottom": "Pune",
                             "top_value": 4000, "bottom_value": 1000,
                             "groups_shown": 2, "top_share_pct": 80.0,
                             "top_vs_bottom_ratio": 4.0}},
                {"signals": {"kind": "trend", "periods": 4, "change_pct": 50.0,
                             "first_period": "a", "last_period": "b",
                             "peak_period": "x", "trough_period": "y"}}]
    syn = plain_synthesis(findings)
    assert "Nagpur" in syn and "Pune" in syn and "+50%" in syn


# ---------- P2.1: full grammar mappings + completeness ----------

VALID_KINDS = {"kpi", "bar", "hbar", "line", "dbar", "scatter", "sbar",
               "multiples", "table"}


def test_chart_two_metrics_per_key_is_scatter():
    df = _df()
    result, plan = _run_plan(df, {"source": "a1", "steps": [
        {"op": "group_by", "columns": ["district"]},
        {"op": "aggregate", "column": "enrollment", "fn": "sum", "alias": "total_enr"},
        {"op": "aggregate", "column": "budget", "fn": "sum", "alias": "total_bud"},
    ]})
    spec = choose_chart(result, plan)
    assert spec["kind"] == "scatter"
    assert spec["y"] == ["total_enr", "total_bud"]


def test_chart_pivot_is_stacked_bar():
    df = _df()
    result, plan = _run_plan(df, {"source": "a1", "steps": [
        {"op": "pivot", "index": "district", "columns": "scheme",
         "values": "enrollment"},
    ]})
    spec = choose_chart(result, plan)
    assert spec["kind"] == "sbar"
    assert 2 <= len(spec["y"]) <= 6


def test_chart_grouped_time_series_is_small_multiples():
    df = _df()
    df["month"] = [f"2025-{(i % 6) + 1:02d}" for i in range(len(df))]
    result, plan = _run_plan(df, {"source": "a1", "steps": [
        {"op": "group_by", "columns": ["month", "scheme"]},
        {"op": "aggregate", "column": "enrollment", "fn": "sum", "alias": "total"},
        {"op": "sort", "column": "month", "dir": "asc"},
    ]})
    spec = choose_chart(result, plan)
    assert spec["kind"] == "multiples"
    assert spec["facet"] == "scheme"


def test_chart_completeness_every_shape_maps():
    """Every result shape the executor can produce must land on a valid
    ChartSpec kind - no plan may leave the board chartless-by-accident."""
    df = _df()
    plans = [
        # every step type appears at least once across these plans
        [{"op": "filter", "column": "scheme", "operator": "==", "value": "A"}],
        [{"op": "time_window", "column": "month", "last_n": 3}],
        [{"op": "derive", "name": "per_unit", "kind": "ratio",
          "left": "budget", "right": "enrollment"},
         {"op": "group_by", "columns": ["district"]},
         {"op": "aggregate", "column": "per_unit", "fn": "mean", "alias": "avg_pu"}],
        [{"op": "group_by", "columns": ["district"]},
         {"op": "aggregate", "column": "enrollment", "fn": "sum", "alias": "t"},
         {"op": "sort", "column": "t", "dir": "desc"},
         {"op": "top_n", "n": 3}],
        [{"op": "pivot", "index": "district", "columns": "scheme",
          "values": "enrollment"}],
        [{"op": "group_by", "columns": ["month"]},
         {"op": "aggregate", "column": "enrollment", "fn": "sum", "alias": "t"},
         {"op": "sort", "column": "month", "dir": "asc"},
         {"op": "delta_vs_period", "column": "t", "period_column": "month", "lag": 1}],
        [{"op": "aggregate", "column": "enrollment", "fn": "sum", "alias": "t"}],
        [{"op": "group_by", "columns": ["district"]},
         {"op": "aggregate", "column": "district", "fn": "count", "alias": "n"}],
    ]
    used_ops = {s["op"] for p in plans for s in p}
    from engine.query.plan import ALL_STEP_TYPES
    all_ops = {t.model_fields["op"].default for t in ALL_STEP_TYPES}
    assert used_ops == all_ops, f"missing coverage for: {all_ops - used_ops}"
    for steps in plans:
        result, plan = _run_plan(df, {"source": "a1", "steps": steps})
        spec = choose_chart(result, plan)
        assert spec["kind"] in VALID_KINDS, (steps, spec)


# ---------- API: explore / export / path-choice ----------

def test_explore_endpoint_heuristic():
    r = client.post(f"/api/datasets/{ds_id}/explore")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["generated_by"] == "heuristic"
    assert len(body["findings"]) >= 3
    assert body["synthesis"]  # the analyst's takeaway is always present
    for f in body["findings"]:
        assert f["headline"]
        assert f["meaning"]  # every finding explained in plain language
        assert f["chart"]["kind"] in {"kpi", "bar", "hbar", "line", "dbar", "table"}
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


def test_overview_endpoint():
    r = client.get(f"/api/datasets/{ds_id}/overview")
    assert r.status_code == 200, r.text
    prof = r.json()["profile"]
    assert prof["n_rows"] == 60 and prof["n_cols"] == 5
    cols = {c["name"]: c for c in prof["columns"]}
    assert "histogram" in cols["enrollment"]
    assert "top_values" in cols["district"]
    ev = client.get(f"/api/activity?project_id={pid}&limit=100").json()["events"]
    assert any(e["event_type"] == "profile" for e in ev)


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
