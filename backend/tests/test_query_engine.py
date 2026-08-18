"""Unit tests for the query engine: every op alone + composed plans,
null handling, limits, and column resolution. Plain-python asserts -
run directly: python tests/test_query_engine.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from engine.query.executor import MAX_ROWS_OUT, QueryExecutionError, execute_plan
from engine.query.plan import QueryPlan
from engine.query.resolve import ColumnResolutionError, resolve_plan

DF = pd.DataFrame({
    "District": ["Pune", "Nashik", "Satara", "Pune", "Nashik", "Satara", "Nagpur", "Nagpur"],
    "Month": ["2026-01", "2026-01", "2026-01", "2026-02", "2026-02", "2026-02", "2026-01", "2026-02"],
    "Female Participants": [40.0, 30.0, np.nan, 44.0, 33.0, 20.0, 10.0, 12.0],
    "Total Participants": [100.0, 90.0, 80.0, 110.0, 95.0, 85.0, 50.0, 60.0],
})


def plan(steps, source="art1"):
    return QueryPlan.model_validate({"source": source, "steps": steps})


def run(steps, frame=DF):
    p = resolve_plan(plan(steps), list(frame.columns))
    return execute_plan(p, frame)


def test_filters():
    r = run([{"op": "filter", "column": "district", "operator": "==", "value": "pune"}])
    assert len(r["table"]) == 2
    r = run([{"op": "filter", "column": "Total Participants", "operator": ">", "value": 90}])
    assert len(r["table"]) == 3  # 100, 110, 95
    r = run([{"op": "filter", "column": "District", "operator": "in", "value": ["Pune", "nagpur"]}])
    assert len(r["table"]) == 4
    r = run([{"op": "filter", "column": "Female Participants", "operator": "is_null"}])
    assert len(r["table"]) == 1
    r = run([{"op": "filter", "column": "District", "operator": "contains", "value": "na"}])
    assert {t["District"] for t in r["table"]} == {"Nashik", "Nagpur"}


def test_derive_and_nulls():
    r = run([
        {"op": "derive", "name": "share", "kind": "percent_of",
         "left": "female participants", "right": "total participants"},
    ])
    first = r["table"][0]
    assert abs(first["share"] - 40.0) < 1e-9
    null_row = [t for t in r["table"] if t["District"] == "Satara" and t["Month"] == "2026-01"][0]
    assert null_row["share"] is None  # null numerator stays null, never invented


def test_group_aggregate_nulls_counted():
    r = run([
        {"op": "group_by", "columns": ["District"]},
        {"op": "aggregate", "column": "Female Participants", "fn": "mean", "alias": "avg_female"},
    ])
    assert len(r["table"]) == 4
    assert r["excluded_null_rows"].get("avg_female") == 1  # Satara Jan is null
    satara = [t for t in r["table"] if t["District"] == "Satara"][0]
    assert abs(satara["avg_female"] - 20.0) < 1e-9  # mean of the one non-null value


def test_sort_topn():
    r = run([
        {"op": "group_by", "columns": ["District"]},
        {"op": "aggregate", "column": "Total Participants", "fn": "sum", "alias": "total"},
        {"op": "sort", "column": "total", "dir": "desc"},
        {"op": "top_n", "n": 2},
    ])
    assert [t["District"] for t in r["table"]] == ["Pune", "Nashik"]
    assert r["table"][0]["total"] == 210.0


def test_time_window_last_n():
    r = run([{"op": "time_window", "column": "Month", "last_n": 1}])
    assert all(t["Month"].startswith("2026-02") for t in r["table"])
    assert any("last 1 of 2 periods" in n for n in r["coverage_notes"])


def test_delta_vs_period():
    r = run([
        {"op": "delta_vs_period", "column": "Total Participants",
         "period_column": "Month", "lag": 1},
        {"op": "filter", "column": "Total Participants__delta", "operator": "not_null"},
    ])
    pune = [t for t in r["table"] if t["District"] == "Pune"][0]
    assert abs(pune["Total Participants__delta"] - 10.0) < 1e-9


def test_pivot():
    r = run([{"op": "pivot", "index": "District", "columns": "Month", "values": "Total Participants"}])
    assert len(r["table"]) == 4 and "2026-01" in r["columns"]


def test_composed_full_plan():
    r = run([
        {"op": "derive", "name": "share", "kind": "ratio",
         "left": "Female Participants", "right": "Total Participants"},
        {"op": "filter", "column": "Month", "operator": "==", "value": "2026-02"},
        {"op": "group_by", "columns": ["District"]},
        {"op": "aggregate", "column": "share", "fn": "mean", "alias": "female_share"},
        {"op": "sort", "column": "female_share", "dir": "asc"},
        {"op": "top_n", "n": 3},
    ])
    # manual pandas verification
    manual = DF[DF.Month == "2026-02"].copy()
    manual["share"] = manual["Female Participants"] / manual["Total Participants"]
    expect = manual.groupby("District")["share"].mean().sort_values().head(3)
    got = {t["District"]: t["female_share"] for t in r["table"]}
    for k, v in expect.items():
        assert abs(got[k] - v) < 1e-9, (k, got[k], v)
    assert [rc["rows"] for rc in r["row_counts"]][0] == len(DF)


def test_resolution_failure_did_you_mean():
    try:
        run([{"op": "filter", "column": "femal participant", "operator": "not_null"}])
        raise AssertionError("unknown column must fail before execution")
    except ColumnResolutionError as e:
        assert "Female Participants" in str(e)


def test_output_limit():
    big = pd.DataFrame({"k": range(MAX_ROWS_OUT + 5), "v": 1.0})
    try:
        p = resolve_plan(plan([{"op": "sort", "column": "v", "dir": "desc"}]), list(big.columns))
        execute_plan(p, big)
        raise AssertionError("over-limit output must fail")
    except QueryExecutionError as e:
        assert "row limit" in str(e)


def test_single_number_answer():
    r = run([{"op": "aggregate", "column": "Total Participants", "fn": "sum"}])
    assert len(r["table"]) == 1 and r["table"][0]["sum_Total Participants"] == 670.0


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\n{len(fns)} query-engine tests passed")
