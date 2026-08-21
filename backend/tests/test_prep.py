"""Data Prep Studio: profiling, the blueprint contract, and the prep API.

Everything here was verified by hand while the module was built; this suite
is what keeps it verified. Deterministic and offline - no API key, no LLM.
"""
import io as _io
import sys
import tempfile
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore")

import pandas as pd

from app.config import settings
settings.anthropic_api_key = ""  # heuristic mode: deterministic + free

tmp = Path(tempfile.mkdtemp())
import app.store as store_mod
from app.store import Store
test_store = Store(db_path=tmp / "prep.db")
store_mod.store = test_store
import app.api.routes_prep2 as rp2
rp2.store = test_store
rp2._SESSION_DIR = tmp / "sessions"
from fastapi.testclient import TestClient
from app.main import app

from engine import prep
from engine.blueprint import (apply_blueprint, build_interview, certify,
                              data_dictionary, propose_blueprint, _summary_rows)
from engine.profile_deep import (humanize_header, norm_name, parse_number,
                                 parse_period, profile_table)

client = TestClient(app)


# ---------------------------------------------------------------- fixtures

def banner_frame() -> pd.DataFrame:
    """A report that opens with a title banner and a blank spacer."""
    return pd.DataFrame([
        ["Scheme Enrolment Report - Government of Maharashtra", None, None],
        [None, None, None],
        ["District Name", "State", "Enrolment"],
        ["Pune", "Maharashtra", 12400],
        ["Nashik", "Maharashtra", 9100],
    ])


def two_tier_frame() -> pd.DataFrame:
    """Month blocks merged over per-column measures - the hardest real shape."""
    rows = [
        ["Collections by district", None, None, None, None],
        [None, None, "(Rs. In Crore)", None, None],
        ["District", "Apr-18", None, "May-18", None],
        [None, "CGST", "SGST", "CGST", "SGST"],
        ["Pune", 10, 11, 12, 13],
        ["Nashik", 20, 21, 22, 23],
    ]
    return pd.DataFrame(rows)


def messy_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "Sr No": [str(i + 1) for i in range(6)],
        "District Name": ["Pune", "Nashik", "Cuttack", "Barmer", "Jaipur", "Total"],
        "Households": ["1,23,456", "98,765", "NA", "2,34,567*", "-", "5,56,788"],
        "Literacy %": [72.5, 88.0, 91.2, 65.4, 77.0, 78.8],
        "Empty Col": [None] * 6,
    })


# ------------------------------------------------------------ value parsing

def test_parse_numbers_as_people_write_them():
    assert parse_number("1,23,456") == 123456      # Indian grouping
    assert parse_number("123,456") == 123456       # western grouping
    assert parse_number("Rs. 1,234.50") == 1234.5  # currency
    assert parse_number("1234*") == 1234           # footnote mark
    assert parse_number("(1,234)") == -1234        # accounting negative
    assert parse_number("45.5%") == 45.5           # percent
    for sentinel in ("NA", "NIL", "-", "n/a", ""):
        assert parse_number(sentinel) is None, sentinel


def test_parse_period_notations():
    kinds = {
        "2018-19": "fiscal_year", "F.Y. 2020-21": "fiscal_year",
        "Apr-18": "month", "April 2018": "month",
        "Q3 2019": "quarter", "2019": "year", "15/03/2021": "date",
    }
    for raw, kind in kinds.items():
        got = parse_period(raw)
        assert got and got["kind"] == kind, f"{raw} -> {got}"
    assert parse_period("Maharashtra") is None
    # Two spellings of one month land on one label
    assert parse_period("Apr-18")["label"] == parse_period("April 2018")["label"]


def test_parse_period_every_common_writing():
    """Dates matter, and departments write them every way there is."""
    cases = {
        "Jun-2025": "month", "July 2026": "month", "2026 July": "month",
        "july/2026": "month", "Jun'25": "month", "06/2025": "month",
        "2025-06": "month", "Jun2025": "month", "2025_06": "month",
        "जून 2025": "month", "जुलै-2026": "month",
        "2018-19": "fiscal_year", "FY 2025-26": "fiscal_year", "FY2025": "fiscal_year",
        "Q1 2025": "quarter", "1st Quarter 2025": "quarter", "2025Q1": "quarter",
        "Q1 FY25": "quarter", "H1 2025": "half", "Week 23 2025": "week",
        "2019": "year", "15.06.2025": "date", "31-03-2019": "date",
    }
    for raw, kind in cases.items():
        got = parse_period(raw)
        assert got and got["kind"] == kind, f"{raw} -> {got}"
    # 'Jun-2025' and '2025-06' are the same month however they are written
    assert parse_period("Jun-2025")["key"] == parse_period("2025-06")["key"]
    # a monthly column must never be mistaken for a fiscal year: the second
    # part of a fiscal year has to be the year that follows
    assert parse_period("2025-06")["kind"] == "month"
    assert parse_period("2025-26")["kind"] == "fiscal_year"
    for not_a_period in ("Maharashtra", "CBIC", "1,234", "-", "Anand", "Q5 2025"):
        assert parse_period(not_a_period) is None, not_a_period


def test_humanize_header_reads_cryptic_columns():
    """A header is not a label. Any period inside it moves to the end, where
    a person says it."""
    cases = {
        "financial_year_2018_19_total": "Total, FY2018-19",
        "fy_2024_25_expenditure": "Expenditure, FY2024-25",
        "apr_18_cgst": "CGST, Apr-2018",
        "2025_06_sales": "Sales, Jun-2025",
        "HH_pop_2011": "Households population, 2011",
        "unnamed_3": "Column 3",
    }
    for raw, want in cases.items():
        assert humanize_header(raw) == want, f"{raw} -> {humanize_header(raw)}"
    # an already-readable header is left alone
    assert humanize_header("District Name") == "District Name"


def test_profiled_columns_carry_a_readable_label():
    df = pd.DataFrame({"fy_2024_25_expenditure": [1, 2, 3], "dist_name": ["a", "b", "c"]})
    labels = {c["source_name"]: c["label"] for c in profile_table(df)["columns"]}
    assert labels["fy_2024_25_expenditure"] == "Expenditure, FY2024-25", labels
    assert "district" in labels["dist_name"].lower(), labels


def test_norm_name():
    assert norm_name("Total Amount (Rs.)") == "total_amount_rs"
    assert norm_name("% Literate") == "pct_literate"


# ------------------------------------------------------------ header detect

def test_header_detection_skips_banner():
    hdr = prep.detect_header(banner_frame())
    assert hdr == {"row": 2, "tiers": 1}, hdr
    df = prep.reheader(banner_frame(), hdr["row"], hdr["tiers"])
    assert list(df.columns) == ["District Name", "State", "Enrolment"]
    assert len(df) == 2 and pd.api.types.is_numeric_dtype(df["Enrolment"])


def test_header_detection_two_tier_merged():
    raw = two_tier_frame()
    hdr = prep.detect_header(raw)
    assert hdr["tiers"] == 2 and hdr["row"] == 2, hdr
    df = prep.reheader(raw, hdr["row"], hdr["tiers"])
    # string month labels are preserved verbatim; only real datetimes are
    # reformatted, so 'Apr-18' stays 'Apr-18'
    assert "Apr-18 CGST" in df.columns and "May-18 SGST" in df.columns, list(df.columns)
    assert len(df) == 2


def test_header_detection_leaves_normal_files_alone():
    """A false re-header is worse than the problem it solves."""
    normal = pd.DataFrame([["District", "Enrolment"], ["Pune", 12400], ["Nashik", 9100]])
    assert prep.detect_header(normal) == {"row": 0, "tiers": 1}
    # numeric first data row must not be mistaken for a second header tier
    numeric_first = pd.DataFrame([["year", "amount"], [2022, 100], [2023, 200]])
    assert prep.detect_header(numeric_first) == {"row": 0, "tiers": 1}


# --------------------------------------------------------------- profiling

def test_profile_reads_types_roles_and_issues():
    p = profile_table(messy_frame())
    by = {c["source_name"]: c for c in p["columns"]}
    assert by["Households"]["dtype"] == "number", by["Households"]["dtype_evidence"]
    assert set(by["Households"]["missing_sentinels"]) >= {"NA", "-"}
    kinds = {q["kind"] for q in by["Households"]["quality"]}
    assert {"indian_grouping", "footnote_marks"} <= kinds, kinds
    assert by["Sr No"]["role"] == "identifier"
    assert by["District Name"]["role"] == "geography"
    assert by["Empty Col"]["missing_pct"] == 100.0


def test_profile_finds_unit_in_the_banner():
    raw = two_tier_frame()
    hdr = prep.detect_header(raw)
    df = prep.reheader(raw, hdr["row"], hdr["tiers"])
    banner = " ".join(str(v) for v in raw.iloc[:hdr["row"]].values.flatten()
                      if pd.notna(v))
    assert (profile_table(df, banner)["table_unit"] or {}).get("unit") == "crore"


def test_wide_blocks_found_and_not_invented():
    wide = pd.DataFrame({
        "State": ["Kerala", "Punjab"],
        "Apr-2021 Revenue": [1, 2], "Apr-2021 Refund": [1, 2],
        "May-2021 Revenue": [1, 2], "May-2021 Refund": [1, 2],
        "Jun-2021 Revenue": [1, 2], "Jun-2021 Refund": [1, 2],
    })
    wb = profile_table(wide)["wide_blocks"]
    assert wb and sorted(wb["measures"]) == ["Refund", "Revenue"]
    assert len(wb["periods"]) == 3 and wb["id_columns"] == ["State"]

    bare = pd.DataFrame({"District": ["A", "B"], "2019": [1, 2], "2020": [3, 4], "2021": [5, 6]})
    assert (profile_table(bare)["wide_blocks"] or {}).get("kind") == "bare_periods"

    # an already-tidy table must NOT be reported as wide
    tidy = pd.DataFrame({
        "Date": [d for d in pd.date_range("2022-01-01", periods=10).astype(str) for _ in range(2)],
        "Store": ["S1", "S2"] * 10, "Units": range(20),
    })
    assert profile_table(tidy)["wide_blocks"] is None


def test_grain_candidates_find_the_key():
    tidy = pd.DataFrame({
        "Date": [d for d in pd.date_range("2022-01-01", periods=10).astype(str) for _ in range(2)],
        "Store": ["S1", "S2"] * 10, "Units": range(20),
    })
    grains = [set(g["columns"]) for g in profile_table(tidy)["grain_candidates"]]
    assert {"Date", "Store"} in grains, grains


# ------------------------------------------------------- summary + combine

def test_summary_rows_reconcile_and_flip_the_recommendation():
    ok = pd.DataFrame({"Item": ["A", "B", "Total"], "Amount": [10, 20, 30]})
    assert _summary_rows(ok)["reconciliation"] == "match"
    bad = pd.DataFrame({"Item": ["A", "B", "Total"], "Amount": [10, 20, 999]})
    assert _summary_rows(bad)["reconciliation"] == "mismatch"
    # a mismatch must not be quietly dropped - the studio recommends keeping it
    q = [x for x in build_interview(profile_table(bad), bad) if x["id"] == "summary_rows"][0]
    assert q["suggested"] == "flag" and "do NOT add up" in q["why"]


def test_reconciliation_skips_non_additive_columns():
    """Rates do not sum, so a total row must not be judged against them."""
    df = pd.DataFrame({"District": ["A", "B", "Total"], "Literacy %": [70.0, 80.0, 75.0]})
    assert _summary_rows(df).get("reconciliation") != "mismatch"


def test_combine_stack_join_and_review():
    y1 = pd.DataFrame({"District Name": ["Pune", "Nashik"], "Enrolment": [1, 2]})
    y2 = pd.DataFrame({"district_name": ["Pune", "Nashik"], "enrolment": [3, 4]})
    prop = prep.propose_combine({"scheme_2022.csv": y1, "scheme_2023.csv": y2})
    assert prop["strategy"] == "stack" and prop["add_year_column"]
    df, _ = prep.apply_combine({"scheme_2022.csv": y1, "scheme_2023.csv": y2}, prop)
    assert list(df["year"]) == [2022, 2022, 2023, 2023]
    assert "District Name" in df.columns  # spellings harmonised

    a = pd.DataFrame({"State": ["MH", "KA", "TN"], "literacy": [82, 77, 80]})
    b = pd.DataFrame({"state": ["MH", "KA", "TN"], "income": [1, 2, 3]})
    pj = prep.propose_combine({"lit.csv": a, "inc.csv": b})
    assert pj["strategy"] == "join" and pj["join_key"]
    joined, _ = prep.apply_combine({"lit.csv": a, "inc.csv": b}, pj)
    assert joined.shape == (3, 3)

    unrelated = {"x.csv": pd.DataFrame({"a": [1]}),
                 "y.csv": pd.DataFrame({"zz": ["m"], "qq": [2]})}
    assert prep.propose_combine(unrelated)["strategy"] == "review"


def test_join_quality_reports_silent_loss():
    a = pd.DataFrame({"State": ["MH", "KA", "TN"], "x": [1, 2, 3]})
    b = pd.DataFrame({"State": ["MH", "KA", "GJ"], "y": [1, 2, 3]})
    q = prep.join_quality({"a": a, "b": b}, "State")
    assert q["checked"] and q["shared_keys"] == 2
    assert q["verdict"] != "clean"
    missing = {m for s in q["per_sheet"] for m in s["unmatched_examples"]}
    assert {"TN", "GJ"} <= missing, missing


def test_junk_and_footer_rows():
    df = pd.DataFrame({
        "District": ["Pune", "Nashik", "Grand Total", None, None],
        "Value": [1, 2, 3, None, None],
        "Note": [None, None, None, None, "provisional figures"],
    })
    scan = prep.junk_scan(df)
    assert scan["total_like_rows"] >= 1 and scan["footer_rows"] >= 1
    cleaned, removed = prep.drop_junk(df, True, True, drop_footer=True)
    assert removed >= 2 and len(cleaned) == 2


# ------------------------------------------------------- blueprint contract

def _bp_for(df: pd.DataFrame, banner: str = ""):
    p = profile_table(df, banner)
    answers = {q["id"]: q["suggested"] for q in build_interview(p, df)}
    return p, propose_blueprint(p, answers, df)


def test_blueprint_builds_certifies_and_documents():
    df = messy_frame()
    _, bp = _bp_for(df)
    built, steps = apply_blueprint(df, bp)
    assert len(built) == 5, f"total row should be gone: {len(built)}"
    assert "empty_col" not in built.columns
    assert pd.api.types.is_numeric_dtype(built["households"])
    assert built["households"].max() == 234567     # Indian grouping parsed
    assert int(built["households"].isna().sum()) == 2  # NA and - became null
    assert any("summary" in s for s in steps), steps
    cert = certify(built, bp)
    assert cert["verdict"] == "ready", cert["checks"]
    doc = data_dictionary(built, bp)
    assert "| `households` |" in doc and "## Columns" in doc


def test_blueprint_reshapes_wide_to_long():
    raw = two_tier_frame()
    hdr = prep.detect_header(raw)
    df = prep.reheader(raw, hdr["row"], hdr["tiers"])
    _, bp = _bp_for(df)
    assert bp["reshape"] is not None
    built, _ = apply_blueprint(df, bp)
    assert "period" in built.columns
    assert {"cgst", "sgst"} <= set(built.columns), list(built.columns)
    assert len(built) == 4  # 2 districts x 2 months


def test_value_rules_catch_real_mistakes():
    df = pd.DataFrame({
        "District": ["Pune", "Nashik", "Atlantis"],
        "Literacy %": [72.5, 88.0, 120.0],
        "Scheme": ["A", "B", "A"],
    })
    _, bp = _bp_for(df)
    built, _ = apply_blueprint(df, bp)
    failed = {c["check"] for c in certify(built, bp)["checks"] if not c["passed"]}
    assert any("never above 100" in f for f in failed), failed
    assert any("holds places" in f for f in failed), failed


def test_place_check_tolerates_spelling_but_flags_non_places():
    """The boundary files write '&' where departmental files write 'and', and
    each carries its own misspellings. Only genuinely non-geographic values
    should be reported."""
    from engine.blueprint import _unmatched_places
    series = pd.Series([
        "Andaman and Nicobar Island",   # '&' in the boundary file
        "Daman and Diu",                # same
        "Dadra and Nagar Haveli",       # boundary file spells it Dadara/Havelli
        "Maharashtra", "Anand",         # 'Anand' must survive the 'and' rule
        "CBIC",                         # genuinely not a place
    ])
    assert _unmatched_places(series) == ["CBIC"], _unmatched_places(series)


def test_certify_catches_a_broken_key():
    df = pd.DataFrame({"District": ["Pune", "Pune"], "Value": [1, 2]})
    p = profile_table(df)
    bp = propose_blueprint(p, {"grain": "District"}, df)
    built, _ = apply_blueprint(df, bp)
    checks = {c["check"]: c["passed"] for c in certify(built, bp)["checks"]}
    assert checks.get("Key is unique") is False, checks


# --------------------------------------------------------------------- API

def _new_session() -> str:
    return client.post("/api/prep2/session").json()["id"]


def _upload(sid: str, name: str, content: bytes):
    return client.post(f"/api/prep2/{sid}/files",
                       files={"file": (name, content, "application/octet-stream")})


def test_api_single_sheet_runs_end_to_end():
    sid = _new_session()
    csv = messy_frame().to_csv(index=False).encode()
    assert _upload(sid, "districts.csv", csv).status_code == 200

    prof = client.post(f"/api/prep2/{sid}/profile")
    assert prof.status_code == 200, prof.text
    qs = client.post(f"/api/prep2/{sid}/interview").json()["questions"]
    assert qs and all(q["suggested"] is not None for q in qs)

    answers = {q["id"]: q["suggested"] for q in qs}
    bp = client.post(f"/api/prep2/{sid}/blueprint", json={"answers": answers}).json()["blueprint"]
    built = client.post(f"/api/prep2/{sid}/build", json={"blueprint": bp}).json()
    assert built["certificate"]["verdict"] == "ready", built["certificate"]

    for kind in ("csv", "dictionary", "schema", "recipe"):
        r = client.get(f"/api/prep2/{sid}/export/{kind}")
        assert r.status_code == 200 and len(r.content) > 50, kind

    reg = client.post(f"/api/prep2/{sid}/register", json={"name": "prep-test"})
    assert reg.status_code == 200 and reg.json()["rows"] == 5


def test_api_refuses_to_silently_drop_sheets():
    """Several sheets: the officer decides how they combine. The old code
    quietly analysed the first one and discarded the rest."""
    sid = _new_session()
    _upload(sid, "a.csv", pd.DataFrame({"a": [1, 2], "b": [3, 4]}).to_csv(index=False).encode())
    _upload(sid, "b.csv", pd.DataFrame({"zz": ["m", "n"], "qq": [5, 6]}).to_csv(index=False).encode())

    blocked = client.post(f"/api/prep2/{sid}/profile")
    assert blocked.status_code == 409, blocked.text

    plan = client.post(f"/api/prep2/{sid}/combine-plan").json()
    assert plan["needs_decision"] and plan["proposal"]["strategy"] == "review"
    assert plan["note"], "the officer must be told why they have to choose"

    # 'review' is a question, never a silent answer
    refused = client.post(f"/api/prep2/{sid}/profile",
                          json={"spec": plan["proposal"]})
    assert refused.status_code == 400

    chosen = {**plan["proposal"], "strategy": "single", "pick": "a.csv"}
    ok = client.post(f"/api/prep2/{sid}/profile", json={"spec": chosen})
    assert ok.status_code == 200 and ok.json()["profile"]["n_cols"] == 2


def test_api_stacks_two_years_when_approved():
    sid = _new_session()
    y1 = pd.DataFrame({"District Name": ["Pune", "Nashik"], "Enrolment": [1, 2]})
    y2 = pd.DataFrame({"district_name": ["Pune", "Nashik"], "enrolment": [3, 4]})
    _upload(sid, "scheme_2022.csv", y1.to_csv(index=False).encode())
    _upload(sid, "scheme_2023.csv", y2.to_csv(index=False).encode())
    plan = client.post(f"/api/prep2/{sid}/combine-plan").json()
    assert plan["proposal"]["strategy"] == "stack"
    prof = client.post(f"/api/prep2/{sid}/profile", json={"spec": plan["proposal"]})
    assert prof.status_code == 200
    assert prof.json()["profile"]["n_rows"] == 4


def test_api_pii_blocks_registration_until_dropped():
    sid = _new_session()
    df = pd.DataFrame({
        "District": ["Pune", "Nashik", "Satara", "Latur", "Akola", "Nanded"],
        "Contact": ["9876543210", "9812345678", "9898989898",
                    "9811118888", "9822227777", "9833336666"],
        "Value": [1, 2, 3, 4, 5, 6],
    })
    _upload(sid, "people.csv", df.to_csv(index=False).encode())
    prof = client.post(f"/api/prep2/{sid}/profile").json()
    assert prof["profile"]["pii_columns"], "phone column must be detected"

    qs = client.post(f"/api/prep2/{sid}/interview").json()["questions"]
    answers = {q["id"]: q["suggested"] for q in qs}
    bp = client.post(f"/api/prep2/{sid}/blueprint", json={"answers": answers}).json()["blueprint"]
    # force the PII column back in to prove registration refuses it
    for c in bp["columns"]:
        if c.get("source_name") == "Contact":
            c["action"] = "keep"
    client.post(f"/api/prep2/{sid}/build", json={"blueprint": bp})
    blocked = client.post(f"/api/prep2/{sid}/register", json={"name": "leaky"})
    assert blocked.status_code == 400 and "Personal data" in blocked.json()["detail"]


def test_api_build_rejects_a_broken_blueprint():
    sid = _new_session()
    _upload(sid, "d.csv", messy_frame().to_csv(index=False).encode())
    client.post(f"/api/prep2/{sid}/profile")
    qs = client.post(f"/api/prep2/{sid}/interview").json()["questions"]
    bp = client.post(f"/api/prep2/{sid}/blueprint",
                     json={"answers": {q["id"]: q["suggested"] for q in qs}}).json()["blueprint"]

    clash = {**bp, "columns": [dict(c) for c in bp["columns"]]}
    keep = [c for c in clash["columns"] if c["action"] != "drop"]
    keep[0]["name"] = keep[1]["name"]
    assert client.post(f"/api/prep2/{sid}/build", json={"blueprint": clash}).status_code == 400

    nothing = {**bp, "columns": [{**c, "action": "drop"} for c in bp["columns"]]}
    assert client.post(f"/api/prep2/{sid}/build", json={"blueprint": nothing}).status_code == 400


def test_api_recipe_replays_on_next_months_file():
    """The whole point of the recipe: same preparation, new file, no re-work."""
    sid = _new_session()
    _upload(sid, "jan.csv", messy_frame().to_csv(index=False).encode())
    client.post(f"/api/prep2/{sid}/profile")
    qs = client.post(f"/api/prep2/{sid}/interview").json()["questions"]
    bp = client.post(f"/api/prep2/{sid}/blueprint",
                     json={"answers": {q["id"]: q["suggested"] for q in qs}}).json()["blueprint"]
    client.post(f"/api/prep2/{sid}/build", json={"blueprint": bp})
    recipe = client.get(f"/api/prep2/{sid}/export/recipe").json()
    assert recipe["version"] >= 2 and recipe["blueprint"]["columns"]

    nxt = messy_frame()
    nxt["Households"] = ["9,99,999", "88,888", "NA", "7,77,777", "-", "27,66,664"]
    sid2 = _new_session()
    _upload(sid2, "jan.csv", nxt.to_csv(index=False).encode())
    out = client.post(f"/api/prep2/{sid2}/replay", json={"recipe": recipe})
    assert out.status_code == 200, out.text
    body = out.json()
    assert body["certificate"]["verdict"] == "ready"
    assert body["preview"]["n_rows"] == 5           # total row dropped again
    assert "households" in body["preview"]["columns"]


def test_api_replay_reports_what_the_new_file_lacks():
    sid = _new_session()
    _upload(sid, "full.csv", messy_frame().to_csv(index=False).encode())
    client.post(f"/api/prep2/{sid}/profile")
    qs = client.post(f"/api/prep2/{sid}/interview").json()["questions"]
    bp = client.post(f"/api/prep2/{sid}/blueprint",
                     json={"answers": {q["id"]: q["suggested"] for q in qs}}).json()["blueprint"]
    client.post(f"/api/prep2/{sid}/build", json={"blueprint": bp})
    recipe = client.get(f"/api/prep2/{sid}/export/recipe").json()

    thin = messy_frame().drop(columns=["Literacy %"])
    sid2 = _new_session()
    _upload(sid2, "full.csv", thin.to_csv(index=False).encode())
    body = client.post(f"/api/prep2/{sid2}/replay", json={"recipe": recipe}).json()
    assert body["warnings"], "a missing column must be reported, not skipped silently"
    assert any("Literacy" in w for w in body["warnings"]), body["warnings"]


def test_api_session_survives_a_restart():
    sid = _new_session()
    _upload(sid, "d.csv", messy_frame().to_csv(index=False).encode())
    client.post(f"/api/prep2/{sid}/profile")
    rp2._S.clear()  # simulate the process going away
    again = client.post(f"/api/prep2/{sid}/interview")
    assert again.status_code == 200, "unfinished prep work must survive a restart"
    assert again.json()["questions"]


def test_api_unknown_session_is_404():
    assert client.post("/api/prep2/nosuchsession/interview").status_code == 404


# --------------------------------------------------------------- agent schemas
def test_response_schemas_are_hardened_before_they_are_sent():
    """A schema that omits additionalProperties is rejected with a 400.

    The API refuses an object schema that does not forbid extra properties,
    and every agent wraps its call in try/except - so a forgotten line does
    not raise, it silently degrades to the heuristic fallback and the agent
    only looks like it chose the rule-based answer. Hardening centrally is
    what stops that; this pins it.
    """
    from engine.llm.claude import _strict

    out = _strict({"type": "object", "properties": {
        "labels": {"type": "array", "items": {
            "type": "object",
            "properties": {"column": {"type": "string"},
                           "nested": {"type": "object",
                                      "properties": {"a": {"type": "string"}}}},
            "required": ["column"]}}},
        "required": ["labels"]})

    assert out["additionalProperties"] is False
    item = out["properties"]["labels"]["items"]
    assert item["additionalProperties"] is False, "objects inside arrays too"
    assert item["properties"]["nested"]["additionalProperties"] is False
    # non-objects are left alone
    assert "additionalProperties" not in item["properties"]["column"]
    assert out["required"] == ["labels"]


def test_hardening_leaves_an_already_correct_schema_alone():
    from engine.llm.claude import _strict

    schema = {"type": "object", "properties": {"a": {"type": "string"}},
              "required": ["a"], "additionalProperties": False}
    assert _strict(schema) == schema


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in fns:
        try:
            fn()
            print(f"PASS  {name}")
        except Exception as exc:
            failed += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(fns) - failed}/{len(fns)} prep tests passed")
    sys.exit(1 if failed else 0)


