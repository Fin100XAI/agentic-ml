"""Planner acceptance: 15-question set (LLM), fallback coverage, ambiguity
and clarify behavior. LLM section runs only when a key is configured."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.agents.query_planner import run_query_planner
from engine.query.fallback_planner import fallback_plan

DISTRICT_CTX = {
    "artifact_id": "art-district",
    "dataset_name": "district participation file",
    "today": "2026-08-18",
    "columns": [
        {"name": "District", "label": "District", "dtype": "object",
         "samples": ["Pune", "Nashik", "Satara", "Nagpur"]},
        {"name": "Month", "label": "Month", "dtype": "object",
         "samples": ["2026-01", "2026-02"]},
        {"name": "Female Participants", "label": "Female Participants", "dtype": "float64", "samples": [40, 30]},
        {"name": "Total Participants", "label": "Total Participants", "dtype": "float64", "samples": [100, 90]},
        {"name": "Block Type", "label": "Block Type", "dtype": "object", "samples": ["Tribal", "Urban", "Rural"]},
    ],
    "glossary": {"participation rate": "female participants divided by total participants"},
}

CHURN_CTX = {
    "artifact_id": "art-churn",
    "dataset_name": "customer churn file",
    "today": "2026-08-18",
    "columns": [
        {"name": "customer_id", "label": "Customer ID", "dtype": "object", "samples": ["C001"]},
        {"name": "tenure_months", "label": "Tenure (months)", "dtype": "int64", "samples": [12, 40]},
        {"name": "monthly_charge", "label": "Monthly Charge", "dtype": "float64", "samples": [45.2]},
        {"name": "support_calls", "label": "Support Calls", "dtype": "int64", "samples": [2, 7]},
        {"name": "contract_type", "label": "Contract Type", "dtype": "object",
         "samples": ["monthly", "annual"]},
        {"name": "churned", "label": "Churned", "dtype": "object", "samples": ["yes", "no"]},
    ],
    "glossary": {},
}


def steps_of(result, i=0):
    return result["plans"][i]["plan"]["steps"]


def has(steps, op, **fields):
    for s in steps:
        if s["op"] != op:
            continue
        if all(str(s.get(k, "")).lower() == str(v).lower() for k, v in fields.items()):
            return True
    return False


def mentions(steps, column):
    return column.lower() in json.dumps(steps).lower()


# (context, question, checker) - checker takes the planner result, returns bool
QUESTIONS = [
    (DISTRICT_CTX, "top 5 districts by total participants",
     lambda r: r["mode"] == "plan" and has(steps_of(r), "top_n", n=5)
     and mentions(steps_of(r), "Total Participants")),
    (DISTRICT_CTX, "bottom 3 districts by female participants",
     lambda r: r["mode"] == "plan" and has(steps_of(r), "top_n", n=3)
     and has(steps_of(r), "sort", dir="asc")),
    (DISTRICT_CTX, "average total participants by district",
     lambda r: r["mode"] == "plan" and has(steps_of(r), "aggregate", fn="mean")
     and has(steps_of(r), "group_by")),
    (DISTRICT_CTX, "which districts have a participation rate below 40 percent",
     lambda r: r["mode"] == "plan" and has(steps_of(r), "derive")
     and any(s["op"] == "filter" and s["operator"] in ("<", "<=") for s in steps_of(r))),
    (DISTRICT_CTX, "how many rows are there per block type",
     lambda r: r["mode"] == "plan" and has(steps_of(r), "aggregate", fn="count")
     and mentions(steps_of(r), "Block Type")),
    (DISTRICT_CTX, "female participants as a share of total, by district, last 1 month",
     lambda r: r["mode"] == "plan" and has(steps_of(r), "derive")
     and (has(steps_of(r), "time_window") or mentions(steps_of(r), "Month"))),
    (DISTRICT_CTX, "change in total participants versus the previous month per district",
     lambda r: r["mode"] == "plan" and has(steps_of(r), "delta_vs_period")),
    (DISTRICT_CTX, "show total participants with one row per district and one column per month",
     lambda r: r["mode"] == "plan" and has(steps_of(r), "pivot")),
    (CHURN_CTX, "average monthly charge by contract type",
     lambda r: r["mode"] == "plan" and has(steps_of(r), "aggregate", fn="mean")
     and mentions(steps_of(r), "monthly_charge") and mentions(steps_of(r), "contract_type")),
    (CHURN_CTX, "how many customers churned",
     lambda r: r["mode"] == "plan" and mentions(steps_of(r), "churned")
     and (has(steps_of(r), "aggregate", fn="count") or has(steps_of(r), "aggregate", fn="nunique")
          or has(steps_of(r), "group_by"))),
    (CHURN_CTX, "customers with more than 5 support calls",
     lambda r: r["mode"] == "plan"
     and any(s["op"] == "filter" and s.get("operator") in (">", ">=") for s in steps_of(r))),
    (CHURN_CTX, "top 10 customers by monthly charge",
     lambda r: r["mode"] == "plan" and has(steps_of(r), "top_n", n=10)
     and has(steps_of(r), "sort", dir="desc")),
    (CHURN_CTX, "median tenure of churned customers",
     lambda r: r["mode"] == "plan" and has(steps_of(r), "aggregate", fn="median")
     and any(s["op"] == "filter" for s in steps_of(r))),
    (CHURN_CTX, "number of distinct contract types",
     lambda r: r["mode"] == "plan" and has(steps_of(r), "aggregate", fn="nunique")),
    (CHURN_CTX, "share of customers on monthly contracts with above 60 monthly charge",
     lambda r: r["mode"] in ("plan", "ambiguous") and len(r["plans"]) >= 1
     and any(s["op"] == "filter" for s in steps_of(r))),
]

# The five shapes the fallback must handle without any LLM.
FALLBACK_SET = [
    ("top 5 district by total participants",
     lambda p: any(s["op"] == "top_n" and s["n"] == 5 for s in p["steps"])),
    ("average monthly charge by contract type",
     lambda p: any(s["op"] == "aggregate" and s["fn"] == "mean" for s in p["steps"])
     and any(s["op"] == "group_by" for s in p["steps"])),
    ("how many rows per block type",
     lambda p: any(s["op"] == "aggregate" and s["fn"] == "count" for s in p["steps"])),
    ("support calls above 5",
     lambda p: any(s["op"] == "filter" and s["operator"] == ">" and s["value"] == 5.0
                   for s in p["steps"])),
    ("total participants last 2 months",
     lambda p: any(s["op"] == "time_window" and s.get("last_n") == 2 for s in p["steps"])),
]


def _ctx_cols(ctx):
    return [c["name"] for c in ctx["columns"]]


def _ctx_numeric(ctx):
    return [c["name"] for c in ctx["columns"] if "int" in c["dtype"] or "float" in c["dtype"]]


def test_fallback_shapes():
    for q, check in FALLBACK_SET:
        ctx = DISTRICT_CTX if "participants" in q or "block" in q or "district" in q else CHURN_CTX
        p = fallback_plan(q, _ctx_cols(ctx), None, _ctx_numeric(ctx))
        assert p is not None, f"fallback returned None for: {q}"
        assert check(p), f"fallback wrong shape for: {q} -> {p['steps']}"


def test_fallback_via_planner_no_provider():
    r = run_query_planner(None, "top 5 district by total participants", DISTRICT_CTX)
    assert r["mode"] == "plan" and r["generated_by"] == "heuristic"
    r = run_query_planner(None, "please summarize the vibes", DISTRICT_CTX)
    assert r["mode"] == "clarify"


def _provider():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.config import settings
    if not settings.llm_enabled:
        return None
    from engine.llm.claude import ClaudeProvider
    return ClaudeProvider(settings.anthropic_api_key, settings.anthropic_model)


def test_llm_question_set():
    provider = _provider()
    if provider is None:
        print("  (no API key - LLM section skipped)")
        return
    correct, failures = 0, []
    for ctx, q, check in QUESTIONS:
        r = run_query_planner(provider, q, ctx)
        try:
            ok = check(r)
        except Exception:
            ok = False
        if ok:
            correct += 1
        else:
            failures.append((q, r["mode"], r["plans"][:1], r.get("last_error")))
    print(f"  LLM planner: {correct}/{len(QUESTIONS)} correct")
    for q, mode, plans, err in failures:
        print(f"    MISS: {q} -> mode={mode} err={err} plan={json.dumps(plans)[:200]}")
    assert correct >= 13, f"only {correct}/15 correct"


def test_llm_ambiguity_and_nonsense():
    provider = _provider()
    if provider is None:
        return
    ctx = json.loads(json.dumps(DISTRICT_CTX))
    ctx["columns"].append({"name": "Female Participants (Rural)", "label": "Female Participants (Rural)",
                           "dtype": "float64", "samples": [12.0]})
    r = run_query_planner(provider, "average female participants by district", ctx)
    assert (r["mode"] == "ambiguous" and len(r["plans"]) == 2) or r["mode"] in ("plan", "clarify"), r["mode"]
    r2 = run_query_planner(provider, "what is the meaning of life?", DISTRICT_CTX)
    assert r2["mode"] == "clarify", r2["mode"]


if __name__ == "__main__":
    for fn in [test_fallback_shapes, test_fallback_via_planner_no_provider,
               test_llm_question_set, test_llm_ambiguity_and_nonsense]:
        fn()
        print(f"PASS  {fn.__name__}")
    print("\nplanner tests passed")
