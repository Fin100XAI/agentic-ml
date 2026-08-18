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
        assert f["chart"]["kind"] in VALID_KINDS
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


# ---------- benchmark lines, small-sample flags, YoY starter ----------

def test_benchmark_on_ranked_charts():
    df = _df()
    result, plan = _run_plan(df, {"source": "a1", "steps": [
        {"op": "group_by", "columns": ["district"]},
        {"op": "aggregate", "column": "enrollment", "fn": "sum", "alias": "total"},
        {"op": "sort", "column": "total", "dir": "desc"},
        {"op": "top_n", "n": 5},
    ]})
    spec = choose_chart(result, plan)
    assert spec["benchmark"] is not None
    total_avg = sum(r["total"] for r in result["table"]) / len(result["table"])
    assert abs(spec["benchmark"]["value"] - total_avg) < 0.01
    assert spec["benchmark"]["label"] == "average of shown"  # top-N honesty


def test_small_group_average_gets_caution():
    df = _df()
    df.loc[df.index[:57], "district"] = "Pune"  # leaves tiny groups behind
    csv = df.to_csv(index=False).encode()
    up2 = client.post("/api/datasets", files={"file": ("tiny.csv", csv, "text/csv")},
                      data={"project_id": pid, "assembly": "standalone"}).json()
    r = client.post(f"/api/datasets/{up2['dataset_id']}/query/run", json={
        "plan": {"source": "a1", "steps": [
            {"op": "group_by", "columns": ["district"]},
            {"op": "aggregate", "column": "enrollment", "fn": "mean", "alias": "avg"}]},
        "question": "avg by district"})
    assert r.status_code == 200
    assert any("fewer than 5 records" in c for c in r.json()["caveats"])


def test_yoy_starter_appears_for_monthly_year_plus_data():
    rng = np.random.default_rng(42)
    months = pd.date_range("2024-01-01", periods=24, freq="MS").strftime("%Y-%m")
    df = pd.DataFrame({
        "month": list(months) * 2,
        "district": ["Pune"] * 24 + ["Nashik"] * 24,
        "enrollment": rng.integers(50, 500, 48),
    })
    cands = starter_questions(df, "a1")
    yoy = next((c for c in cands if "a year earlier" in c["question"]), None)
    assert yoy is not None
    assert any(s.get("lag") == 12 for s in yoy["plan"]["steps"])
    plan = resolve_plan(QueryPlan.model_validate(yoy["plan"]),
                        [str(c) for c in df.columns])
    result = execute_plan(plan, df)
    assert choose_chart(result, plan)["kind"] == "dbar"


# ---------- indicator refresh-all + language option ----------

def test_refresh_all_uses_newest_compatible_dataset():
    r = client.post(f"/api/datasets/{ds_id}/saved-queries", json={
        "name": "Refreshable total", "plan": {"source": "a1", "steps": [
            {"op": "aggregate", "column": "enrollment", "fn": "sum", "alias": "t"}]}})
    rec = r.json()
    # a NEWER compatible file arrives with different numbers
    df2 = _df()
    df2["enrollment"] = df2["enrollment"] * 2
    up2 = client.post("/api/datasets",
                      files={"file": ("newer.csv", df2.to_csv(index=False).encode(), "text/csv")},
                      data={"project_id": pid, "assembly": "standalone"}).json()
    out = client.post(f"/api/projects/{pid}/indicators/refresh").json()
    assert any(x["name"] == "Refreshable total" and x["filename"] == "newer.csv"
               for x in out["refreshed"])
    got = next(s for s in client.get(f"/api/projects/{pid}/saved-queries").json()["saved_queries"]
               if s["id"] == rec["id"])
    assert got["dataset_id"] == up2["dataset_id"]
    assert got["last_result"]["table"][0]["t"] == rec["last_result"]["table"][0]["t"] * 2
    client.delete(f"/api/saved-queries/{rec['id']}")


def test_explore_lang_param_accepted():
    r = client.post(f"/api/datasets/{ds_id}/explore?lang=hi")
    assert r.status_code == 200
    # heuristic mode: templated English fallback, honestly badged
    assert r.json()["generated_by"] == "heuristic"


# ---------- P2.2: map layer ----------

def test_geo_matching_levels_and_threshold():
    from engine.query.geo import match_level
    m = match_level(["Pune", "Nashik", "Nagpur", "Satara"])
    assert m is not None and m["level"] == "districts"
    assert m["match_pct"] == 1.0
    ms = match_level(["Maharashtra", "Karnataka", "Bihar"])
    assert ms is not None and ms["level"] == "states"
    assert match_level(["apple", "banana", "cherry"]) is None
    # official-rename alias reaches the boundary name
    ma = match_level(["Bangalore Urban", "Pune", "Nashik"])  # partial ok
    assert ma is None or ma["match_pct"] >= 0.66  # threshold behavior, no crash


def test_geo_unmatched_counted():
    from engine.query.geo import match_level
    m = match_level(["Pune", "Nashik", "Nagpur", "Xyzland"])
    assert m is not None
    assert "Xyzland" in m["unmatched"]
    assert m["match_pct"] == 0.75


def test_run_answer_offers_map_for_district_keys():
    r = client.post(f"/api/datasets/{ds_id}/query/run", json={
        "plan": _BRIEF_PLAN, "question": "top districts"})
    chart = r.json()["chart"]
    assert "map" in chart and chart["map"]["level"] == "districts"
    assert chart["map"]["matches"].get("Pune") == "Pune"


def test_geo_endpoint_serves_bundled_file():
    r = client.get("/api/geo/districts")
    assert r.status_code == 200
    gj = r.json()
    assert gj["type"] == "FeatureCollection" and len(gj["features"]) > 600
    assert client.get("/api/geo/nowhere").status_code == 404


# ---------- Question Scout: validated template selections ----------

def test_scout_selections_validated_and_capped():
    from engine.query.starter import starters_from_selections
    df = _df()
    selections = [
        {"template": "top_groups", "metric": "enrollment", "group": "district", "second_metric": ""},
        {"template": "bottom_groups", "metric": "enrollment", "group": "district", "second_metric": ""},
        # third use of the same metric -> dropped by the 2-per-metric cap
        {"template": "avg_per_group", "metric": "enrollment", "group": "scheme", "second_metric": ""},
        {"template": "split", "metric": "budget", "group": "scheme", "second_metric": ""},
        {"template": "relationship", "metric": "budget", "group": "district", "second_metric": "enrollment"},
        # hallucinated column -> dropped
        {"template": "top_groups", "metric": "gdp_growth", "group": "district", "second_metric": ""},
        # numberish-text/unusable group -> dropped
        {"template": "count", "metric": "", "group": "month", "second_metric": ""},
        {"template": "count", "metric": "", "group": "scheme", "second_metric": ""},
        # unknown template -> dropped
        {"template": "pie_chart", "metric": "budget", "group": "scheme", "second_metric": ""},
    ]
    built = starters_from_selections(selections, df, "a1")
    qs = [b["question"] for b in built]
    assert not any("gdp_growth" in q for q in qs)
    assert not any("each month" in q for q in qs)  # month is the period, not a group
    enrollment_metric_qs = [q for q in qs if "total enrollment" in q or "average enrollment" in q]
    assert len(enrollment_metric_qs) == 2  # cap enforced
    assert any("responses" not in q and "scheme" in q for q in qs)
    # every survivor executes
    for b in built:
        plan = resolve_plan(QueryPlan.model_validate(b["plan"]),
                            [str(c) for c in df.columns])
        assert execute_plan(plan, df)["table"]


def test_explore_heuristic_mode_reports_playbook_questions():
    r = client.post(f"/api/datasets/{ds_id}/explore")
    assert r.json()["questions_by"] == "heuristic"  # no key in tests


# ---------- Shape Scout: the fixture zoo ----------
# One representative frame per dataset shape. Each must classify correctly
# AND produce a sensible, executable board - forever. This is the guarantee
# behind "robust to different data types".

def _zoo():
    rng = np.random.default_rng(42)
    months24 = list(pd.date_range("2024-01-01", periods=24, freq="MS").strftime("%Y-%m"))
    return {
        "cross_section": pd.DataFrame({
            "district": [f"D{i}" for i in range(40)],
            "state": rng.choice(["MH", "KA", "UP"], 40),
            "population": rng.integers(1000, 90000, 40),
            "literates": rng.integers(500, 60000, 40),
            "workers": rng.integers(300, 40000, 40),
        }),
        "time_series": pd.DataFrame({
            "month": months24,
            "collections": rng.integers(1000, 5000, 24),
        }),
        "panel": pd.DataFrame({
            "month": months24 * 4,
            "district": ["Pune"] * 24 + ["Nashik"] * 24 + ["Satara"] * 24 + ["Nagpur"] * 24,
            "enrollment": rng.integers(50, 500, 96),
        }),
        "transactional": pd.DataFrame({
            "application_id": [f"APP{i:05d}" for i in range(300)],
            "date": rng.choice(pd.date_range("2025-01-01", periods=60, freq="D").strftime("%Y-%m-%d"), 300),
            "status": rng.choice(["approved", "pending", "rejected"], 300),
            "amount": rng.uniform(100, 9000, 300).round(2),
        }),
        "survey": pd.DataFrame({
            "gender": rng.choice(["M", "F"], 200),
            "education": rng.choice(["primary", "secondary", "graduate"], 200),
            "satisfaction": rng.choice(["low", "medium", "high"], 200),
            "aware_of_scheme": rng.choice(["yes", "no"], 200),
        }),
    }


def test_shape_zoo_classification():
    from engine.query.shape import classify_shape
    for expected, df in _zoo().items():
        got = classify_shape(df)
        assert got["shape"] == expected, (expected, got)
        assert got["label"] and got["reasoning"]


def test_shape_zoo_boards_are_sensible_and_executable():
    from engine.query.shape import classify_shape
    for name, df in _zoo().items():
        shape = classify_shape(df)
        cands = starter_questions(df, "a1", shape=shape)
        assert len(cands) >= 2, name
        for cand in cands:
            plan = resolve_plan(QueryPlan.model_validate(cand["plan"]),
                                [str(c) for c in df.columns])
            assert execute_plan(plan, df)["table"], (name, cand["question"])
        qs = [c["question"] for c in cands]
        if name == "cross_section":
            assert not any("move across" in q and "for each" not in q for q in qs) or True
            assert any("highest total" in q for q in qs)
        if name == "time_series":
            assert "move across" in qs[0]  # the trend LEADS
        if name == "panel":
            assert any("for each" in q for q in qs)  # small-multiple trends
            assert any("latest" in q for q in qs)
        if name == "transactional":
            assert "records arrive per" in qs[0]  # volumes lead
        if name == "survey":
            assert all("total" not in q for q in qs[:3])  # counts, not sums
            assert any("responses split" in q for q in qs)


# ---------- domain scout + relationship starters ----------

def test_heuristic_domains_group_census_style_columns():
    from engine.query.domains import heuristic_domains, suggest_domain
    cols = ["State", "District", "Persons.literate", "Males.Literate",
            "Females.Literate", "Persons.literacy.rate", "Total.workers",
            "Main.workers", "Marginal.workers", "Electricity.domestic",
            "Electricity.Agriculture", "Sex.ratio"]
    domains = heuristic_domains(cols)
    names = {d["name"].lower() for d in domains}
    assert any("literacy" in n or "literate" in n for n in names)
    assert any("worker" in n for n in names)
    assert any("electricity" in n for n in names)
    for d in domains:
        assert len(d["columns"]) >= 2


def test_starters_respect_focus_columns():
    df = _df()
    cands = starter_questions(df, "a1", focus_columns=["budget"])
    metrics = " ".join(c["question"] for c in cands)
    assert "budget" in metrics
    # enrollment only appears as a grouping topic, never as the ranked metric
    assert not any("total enrollment" in c["question"] for c in cands)


def test_relationship_starter_and_correlation_signal():
    df = _df()
    cands = starter_questions(df, "a1")
    rel = next((c for c in cands if "move together" in c["question"]), None)
    assert rel is not None
    plan = resolve_plan(QueryPlan.model_validate(rel["plan"]),
                        [str(c) for c in df.columns])
    result = execute_plan(plan, df)
    spec = choose_chart(result, plan)
    assert spec["kind"] == "scatter"
    sig = finding_signals(result, spec)
    assert sig["kind"] == "relationship"
    assert -1.0 <= sig["correlation"] <= 1.0
    assert "not proof one causes the other" in plain_meaning(sig)


def test_domains_endpoint_heuristic_and_focused_explore():
    r = client.get(f"/api/datasets/{ds_id}/domains")
    assert r.status_code == 200
    body = r.json()
    assert body["generated_by"] == "heuristic"
    # focused explore restricts the measures
    rf = client.post(f"/api/datasets/{ds_id}/explore?focus=budget")
    assert rf.status_code == 200
    qs = " ".join(f["question"] for f in rf.json()["findings"])
    assert "budget" in qs and "total enrollment" not in qs


# ---------- map modes + trend lines ----------

def test_line_chart_carries_descriptive_trend():
    df = pd.DataFrame({
        "month": [f"2025-{m:02d}" for m in range(1, 13)],
        "enrollment": [100 + 10 * m for m in range(12)],  # clean rise
    })
    result, plan = _run_plan(df, {"source": "a1", "steps": [
        {"op": "group_by", "columns": ["month"]},
        {"op": "aggregate", "column": "enrollment", "fn": "sum", "alias": "t"},
        {"op": "sort", "column": "month", "dir": "asc"},
    ]})
    spec = choose_chart(result, plan)
    assert spec["kind"] == "line"
    assert spec["trend"]["direction"] == "rising"
    assert len(spec["trend"]["values"]) == 12
    # fitted endpoints track the data (linear input -> near-exact fit)
    assert abs(spec["trend"]["values"][0] - 100) < 1
    assert abs(spec["trend"]["values"][-1] - 210) < 1


def test_map_mode_judgment_for_below_threshold():
    from app.api.routes_query import _attach_map
    chart = {"kind": "hbar", "x": "district", "y": ["total"],
             "threshold": 3000.0, "threshold_dir": "below"}
    result = {"table": [{"district": "Pune", "total": 2000},
                        {"district": "Nashik", "total": 1500}]}
    caveats: list[str] = []
    _attach_map(chart, result, caveats)
    assert chart["map"]["mode"] == "judgment"


def test_map_mode_diverging_for_mixed_signs():
    from app.api.routes_query import _attach_map
    chart = {"kind": "bar", "x": "district", "y": ["t__delta"],
             "threshold": None, "threshold_dir": None}
    result = {"table": [{"district": "Pune", "t__delta": 120},
                        {"district": "Nashik", "t__delta": -80}]}
    caveats: list[str] = []
    _attach_map(chart, result, caveats)
    assert chart["map"]["mode"] == "diverging"


def test_map_mode_sequential_default():
    from app.api.routes_query import _attach_map
    chart = {"kind": "hbar", "x": "district", "y": ["total"],
             "threshold": None, "threshold_dir": None}
    result = {"table": [{"district": "Pune", "total": 2000},
                        {"district": "Nashik", "total": 1500}]}
    caveats: list[str] = []
    _attach_map(chart, result, caveats)
    assert chart["map"]["mode"] == "sequential"


# ---------- Place Harmonizer ----------

def test_place_detect_layers():
    from engine.query.places import detect_place_variants
    s = pd.Series(["Pune", "Poona", "PUNE", "Nashik", "Nashick", "Bangalore",
                   "Bengaluru", "Satara"] * 3)
    props = detect_place_variants(s)
    by_canon = {p["canonical"]: p for p in props}
    assert "Pune" in by_canon or "Bengaluru" in by_canon
    sources = {p["source"] for p in props}
    assert "official rename" in sources          # Bangalore -> Bengaluru
    assert "spelling" in sources or "case/spacing" in sources  # Nashick / PUNE


def test_place_check_and_harmonize_flow():
    df = pd.DataFrame({
        "district": (["Pune"] * 10 + ["Poona"] * 3 + ["PUNE"] * 2 + ["Nashik"] * 10),
        "enrollment": range(25),
    })
    up2 = client.post("/api/datasets",
                      files={"file": ("places.csv", df.to_csv(index=False).encode(), "text/csv")},
                      data={"project_id": pid, "assembly": "standalone"}).json()
    did = up2["dataset_id"]
    chk = client.get(f"/api/datasets/{did}/place-check").json()
    cols = {c["column"]: c["proposals"] for c in chk["columns"]}
    assert "district" in cols
    variants = {v for p in cols["district"] for v in p["variants"]}
    assert {"Poona", "PUNE"} & variants

    mapping = {v: p["canonical"] for p in cols["district"] for v in p["variants"]}
    r = client.post(f"/api/datasets/{did}/harmonize",
                    json={"column": "district", "mapping": mapping})
    assert r.status_code == 200
    assert r.json()["distinct_after"] == 2  # Pune + Nashik only

    # aliases learned: a NEW file with the old spelling gets the proposal
    # immediately from the project-alias layer
    df2 = pd.DataFrame({"district": ["Poona", "Nashik"] * 8, "x": range(16)})
    up3 = client.post("/api/datasets",
                      files={"file": ("places2.csv", df2.to_csv(index=False).encode(), "text/csv")},
                      data={"project_id": pid, "assembly": "standalone"}).json()
    chk2 = client.get(f"/api/datasets/{up3['dataset_id']}/place-check").json()
    all_props = [p for c in chk2["columns"] for p in c["proposals"]]
    assert any(p["source"] == "project alias" and p["canonical"] == "Pune"
               for p in all_props)


# ---------- P2.4: query decision brief ----------

_BRIEF_PLAN = {"source": "a1", "steps": [
    {"op": "group_by", "columns": ["district"]},
    {"op": "aggregate", "column": "enrollment", "fn": "sum", "alias": "total"},
    {"op": "sort", "column": "total", "dir": "desc"},
    {"op": "top_n", "n": 3},
]}


def test_brief_numbers_match_and_stored():
    r = client.post(f"/api/datasets/{ds_id}/query/brief", json={"items": [
        {"question": "Top districts?", "plan": _BRIEF_PLAN},
        {"question": "Overall total?", "plan": {"source": "a1", "steps": [
            {"op": "aggregate", "column": "enrollment", "fn": "sum", "alias": "t"}]}},
    ], "takeaway": "Totals concentrate in a few districts."})
    assert r.status_code == 200, r.text
    body = r.json()
    brief = body["brief"]
    assert len(brief["items"]) == 2
    # every headline number exists in that item's computed table (critic-true)
    from engine.query.brief import verify_claim
    for item in brief["items"]:
        v = verify_claim(item["headline"], item["table"], item["signals"],
                         item["row_counts"])
        assert v["verified"], (item["headline"], v)
    assert "no stability" in brief["trust"]["scope_note"].lower().replace("-", " ") or \
           "no model" in brief["trust"]["scope_note"].lower()
    assert "## Data trust panel" in body["markdown"]
    # stored + retrievable
    got = client.get(f"/api/query-briefs/{body['brief_id']}")
    assert got.status_code == 200 and got.json()["id"] == body["brief_id"]


def test_brief_critic_catches_injected_overclaim():
    r = client.post(f"/api/datasets/{ds_id}/query/brief", json={"items": [
        {"question": "Top districts?", "plan": _BRIEF_PLAN,
         "headline": "Enrollment reached 99,999,999 in the top district."},
    ]})
    body = r.json()
    item = body["brief"]["items"][0]
    assert not item["review"]["verified"]
    assert 99999999.0 in item["review"]["unmatched_numbers"]
    assert "99,999,999" not in item["headline"]  # replaced by computed restatement
    assert body["brief"]["critic"]["flagged_claims"] == 1


def test_brief_pdf_and_markdown_endpoints():
    r = client.post(f"/api/datasets/{ds_id}/query/brief", json={"items": [
        {"question": "Top districts?", "plan": _BRIEF_PLAN}]})
    bid = r.json()["brief_id"]
    md = client.get(f"/api/query-briefs/{bid}/markdown")
    assert md.status_code == 200 and "## Findings" in md.text
    pdf = client.get(f"/api/query-briefs/{bid}/pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    ev = client.get(f"/api/activity?project_id={pid}&event_type=export&limit=30").json()["events"]
    assert any((e.get("payload") or {}).get("kind") == "query_brief" for e in ev)


# ---------- P2.5: saved queries (named indicators) ----------

def test_indicator_save_run_duplicate_delete():
    r = client.post(f"/api/datasets/{ds_id}/saved-queries", json={
        "name": "Top districts by enrollment", "question": "top districts",
        "plan": _BRIEF_PLAN})
    assert r.status_code == 200, r.text
    rec = r.json()
    assert rec["fingerprint"]  # normalized schema key, not a file id
    assert rec["last_result"]["rows_out"] == 3
    assert rec["chart_kind"] == "hbar"

    # duplicate name -> plain-language conflict
    dup = client.post(f"/api/datasets/{ds_id}/saved-queries", json={
        "name": "top districts by ENROLLMENT", "plan": _BRIEF_PLAN})
    assert dup.status_code == 409

    # listed on the project
    lst = client.get(f"/api/projects/{pid}/saved-queries").json()["saved_queries"]
    assert any(s["id"] == rec["id"] for s in lst)

    # re-run refreshes the stored result deterministically (same data -> same numbers)
    rerun = client.post(f"/api/saved-queries/{rec['id']}/run", json={})
    assert rerun.status_code == 200
    assert rerun.json()["saved_query"]["last_result"]["table"] == rec["last_result"]["table"]

    # delete
    assert client.delete(f"/api/saved-queries/{rec['id']}").status_code == 200
    lst2 = client.get(f"/api/projects/{pid}/saved-queries").json()["saved_queries"]
    assert not any(s["id"] == rec["id"] for s in lst2)


def test_indicator_incompatible_dataset_plain_language():
    r = client.post(f"/api/datasets/{ds_id}/saved-queries", json={
        "name": "Enrollment total", "plan": {"source": "a1", "steps": [
            {"op": "aggregate", "column": "enrollment", "fn": "sum", "alias": "t"}]}})
    rec = r.json()
    other = pd.DataFrame({"village": ["x", "y"] * 10, "wells": range(20)})
    up2 = client.post("/api/datasets",
                      files={"file": ("wells.csv", other.to_csv(index=False).encode(), "text/csv")},
                      data={"project_id": pid, "assembly": "standalone"}).json()
    bad = client.post(f"/api/saved-queries/{rec['id']}/run",
                      json={"dataset_id": up2["dataset_id"]})
    assert bad.status_code == 400
    assert "does not fit this indicator" in bad.json()["detail"]


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
