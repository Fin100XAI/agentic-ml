# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project

**Agentic ML Workbench** - an industry-agnostic, LLM-agent-driven decision-support
POC for administrative/policy stakeholders. A user uploads a CSV into a project;
agents screen it for PII, profile it, propose fixes and features, recommend a
model, and - with the human approving each step - train it and explain the
results as a decision brief with charts, trust tiers, and a critic review.
Trained models live in a versioned registry with scoring, drift monitoring,
what-if scenarios, and an approval-gated intake inbox for recurring files.
Every decision lands on a visible timeline and in the unified activity log.
UI design system: warm editorial look - paper surface (#f4f2ec), white cards,
stone borders, deep indigo accent (#4338ca), Fraunces serif for page titles
(font-display), Inter for UI - tokens in frontend/src/index.css, primitives
in frontend/src/components/ui.tsx. Judgment colors (green/amber/red) stay
reserved for judgment states.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full design.

## Project rules (apply to ALL tasks)

1. NEVER mutate original uploaded data. All transformations produce new derived
   artifacts with lineage pointers to parents. Originals are stored read-only
   with a SHA-256 content hash.
2. EVERY action is logged to the unified activity log: file events, agent calls
   (provider, model, tokens, latency, fallback-or-llm), approvals/declines,
   transformations, training jobs, scoring, exports.
3. LLMs only judge and phrase. Every number is computed in Python. Every agent
   has a deterministic fallback used when no API key is set or the call fails.
   UI badges each output as `claude` or `heuristic`.
4. Nothing runs without human approval. Agents propose; the orchestrator gates.
5. Plain language first: every new user-facing surface gets friendly names,
   jargon behind info buttons.
6. Fixed random seed (42) wherever randomness exists.
7. Backend: FastAPI + pandas/sklearn/XGBoost/statsmodels, engine/ is pure Python
   with no web imports, models are plugins in engine/catalog/ (subclass
   ModelPlugin, decorate @register, param_schema() auto-generates the UI form).
   Frontend: React 18 + Vite + TS + Tailwind v4 + Recharts, screens in
   src/components/screens/, types mirrored in src/types.ts.
8. Keep SQLite schema portable to Postgres (no SQLite-only features).
9. Windows-friendly: no packages needing a C++ toolchain.

## Query path rules (apply to ALL query-path tasks)

10. The Query Path is additive. Existing ML-path modules (catalog/, validate,
    suggest, autotune, scoring, drift, slices, scenario, multiforecast,
    calibration) must NOT be modified. Permitted touch points, marked with
    # QUERY-PATH EXTENSION comments, are exactly:
    (a) the direction-stage alignment check (route classification),
    (b) project dashboard + intake inbox (new panels/rule kinds),
    (c) shared additive infrastructure: activity_log event types, artifact
    transform_types, health-screen sections, brief/report renderers, shared
    chart components.
11. The LLM NEVER writes executable code for queries. It emits a structured
    QueryPlan (Pydantic schema); a deterministic interpreter executes it.
    No eval, no generated pandas.
12. Every plan is shown in plain language before execution ("interpreted
    as..."); execution without a visible interpretation is forbidden.
13. Query answers always carry data caveats (missingness, excluded rows,
    coverage, readiness findings) sourced from the same health/profile
    machinery as the ML path.
14. Charts are chosen deterministically from result shape, never by the LLM.
    Chart grammar rules (zero-based bar axes, no dual axes, no 3D,
    colorblind-safe palette, red/amber reserved for judgment states) are
    binding on every chart in the system.
15. Run the FULL existing test suite after every query-path task; any
    ML-path test failure means rule 10 was violated.

## Commands

```powershell
# Backend (port 8000)
cd backend; .\.venv\Scripts\Activate.ps1; uvicorn app.main:app --reload --port 8000

# Frontend (port 5173, proxies /api to 8000)
cd frontend; npm run dev

# Typecheck frontend
cd frontend; npx tsc

# Regenerate sample CSVs
cd backend\sample_data; ..\..\backend\.venv\Scripts\python.exe make_samples.py
```

## Conventions

- **Adding a model** = one class in `backend/engine/catalog/` (subclass
  `ModelPlugin`, decorate with `@register`). Its `param_schema()` auto-generates
  the UI hyperparameter form - no frontend change needed.
- All engine outputs must be JSON-safe (no NaN/inf; see `profiler._clean`).
- Engineered/derived column names use the `__` convention (`col__log`,
  `a__per__b`) so display labels resolve automatically in the orchestrator.
- API key goes in `backend/.env` (`ANTHROPIC_API_KEY=...`); never commit it.
- Use plain hyphens (-) in all generated text, code, and UI; never em dashes.

## Gotchas

- Windows: Prophet is deliberately excluded (needs C++ toolchain); forecasting
  uses ARIMA/ExpSmoothing/XGBoost-lags instead.
- statsmodels must be >=0.14.6 to work with scipy >=1.16.
- xgboost must be >=2.1.4 with scikit-learn >=1.6 (older xgboost lacks
  __sklearn_tags__ and breaks inside Pipelines and cross_val_*).
- The dev launch config (`.claude/launch.json`) starts uvicorn WITHOUT
  --reload; restart the preview server after backend changes.
- PowerShell 5.1: no `&&`; avoid Get-Content/Set-Content on UTF-8 files
  (mojibake) - use Python or [IO.File]::WriteAllText instead.
