"""Describe renderer: completeness over the op schema + golden sentences."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.query.describe import OP_TEMPLATES, describe_plan
from engine.query.plan import ALL_STEP_TYPES, QueryPlan


def plan(steps):
    return QueryPlan.model_validate({"source": "a", "steps": steps})


def sentences(steps, name="the district file", labels=None):
    return describe_plan(plan(steps), name, labels)["sentences"]


def test_completeness_every_op_has_a_template():
    ops = set()
    for t in ALL_STEP_TYPES:
        ops.add(t.model_fields["op"].default)
    missing = ops - set(OP_TEMPLATES)
    assert not missing, f"ops without a describe template: {missing} - add one before shipping the op"
    extra = set(OP_TEMPLATES) - ops
    assert not extra, f"templates without an op: {extra}"


GOLDEN = [
    (
        [{"op": "filter", "column": "share", "operator": "<", "value": 40}],
        ["Take the district file.", "Keep rows where share is below 40."],
    ),
    (
        [{"op": "filter", "column": "District", "operator": "in", "value": ["Pune", "Nashik"]}],
        ["Take the district file.", "Keep rows where District is one of Pune, Nashik."],
    ),
    (
        [{"op": "filter", "column": "remarks", "operator": "is_null"}],
        ["Take the district file.", "Keep rows where remarks is empty."],
    ),
    (
        [{"op": "time_window", "column": "Month", "last_n": 3}],
        ["Take the district file.", "Keep only the last 3 periods of Month."],
    ),
    (
        [{"op": "derive", "name": "female_share", "kind": "percent_of",
          "left": "Female", "right": "Total"}],
        ["Take the district file.",
         "For each row, compute female_share = Female as a percent of Total."],
    ),
    (
        [{"op": "group_by", "columns": ["District"]},
         {"op": "aggregate", "column": "Total", "fn": "sum", "alias": "total"}],
        ["Take the district file.", "For each District:",
         "Compute the total of Total (called total)."],
    ),
    (
        [{"op": "aggregate", "column": "Total", "fn": "median"}],
        ["Take the district file.", "Compute the median (middle value) of Total."],
    ),
    (
        [{"op": "sort", "column": "share", "dir": "asc"}, {"op": "top_n", "n": 10}],
        ["Take the district file.", "Sort by share, lowest first.", "Keep the first 10 rows."],
    ),
    (
        [{"op": "pivot", "index": "District", "columns": "Month", "values": "Total"}],
        ["Take the district file.",
         "Arrange as a table: one row per District, one column per Month, showing Total."],
    ),
    (
        [{"op": "delta_vs_period", "column": "Total", "period_column": "Month", "lag": 1}],
        ["Take the district file.",
         "Compute the change in Total versus the previous period of Month."],
    ),
]


def test_golden_plans():
    for steps, expected in GOLDEN:
        got = sentences(steps)
        assert got == expected, f"\nplan: {steps}\ngot:      {got}\nexpected: {expected}"


def test_friendly_labels_and_glossary():
    out = describe_plan(
        plan([{"op": "aggregate", "column": "amt", "fn": "mean"}]),
        "the claims file", labels={"amt": "Claim Amount"},
    )
    assert out["sentences"][1] == "Compute the average of Claim Amount."
    assert "average" in out["glossary"]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS  {fn.__name__}")
    print(f"\n{len(fns)} describe tests passed")
