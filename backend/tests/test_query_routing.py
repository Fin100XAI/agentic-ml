"""Route classification: direction-stage additions behave and ML routing
is unchanged for prediction questions."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from engine.agents.recommend_agent import run_recommend_agent
from engine.profiler import profile_dataframe
from engine.query.routing import classify_route


def test_classify_route():
    assert classify_route("predict which customers will churn")["route"] == "model_needed"
    assert classify_route("forecast sales for next quarter")["route"] == "model_needed"
    assert classify_route("top 10 districts by enrollment")["route"] == "direct_query"
    assert classify_route("how many applications came in last month")["route"] == "direct_query"
    assert classify_route("which districts are below 40 and will they improve next year")["route"] == "both"
    assert classify_route("")["route"] == "model_needed"  # neutral defaults to today's behavior
    for r in [classify_route(q) for q in ("predict churn", "top 5 by x", "")]:
        assert r["route_reasoning"]


def test_recommend_agent_carries_route_heuristic():
    rng = np.random.default_rng(42)
    df = pd.DataFrame({
        "district": rng.choice(["A", "B", "C"], 200),
        "enrollment": rng.integers(50, 500, 200),
        "dropped_out": rng.choice(["yes", "no"], 200),
    })
    profile = profile_dataframe(df)

    # prediction question: routes to ML exactly as before (zero behavior change)
    rec = run_recommend_agent(None, profile, "predict who will drop out")
    assert rec["use_case"] in ("classification", "regression", "clustering", "forecasting")
    assert rec["alignment"]["route"] == "model_needed"
    assert rec["alignment"]["aligned"] is True

    # direct question: same recommendation machinery, but the route offers the query path
    rec2 = run_recommend_agent(None, profile, "top 10 districts by enrollment")
    assert rec2["alignment"]["route"] == "direct_query"
    assert rec2["alignment"]["route_reasoning"]


if __name__ == "__main__":
    for fn in [test_classify_route, test_recommend_agent_carries_route_heuristic]:
        fn()
        print(f"PASS  {fn.__name__}")
    print("\nrouting tests passed")
