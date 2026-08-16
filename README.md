# Agentic ML Workbench

An industry-agnostic, LLM-agent-driven analytics platform. Upload a spreadsheet and
get a decision brief: what drives outcomes, what groups exist, where things are
heading - with recommended actions and an honest read on how much to trust them.
AI agents do the analysis; a human approves every step, and every decision is
recorded on a visible trail.

Built for policy-making stakeholders: the goal is not model evaluation, it is
giving decision makers enough evidence to act on.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full design.

## How a run works

1. **Upload** a CSV or Excel file. Multi-sheet workbooks get a sheet picker, and a
   join scout proposes combining sheets when it finds a linking key.
2. **PII screen** - before ANY analysis or AI call, columns that look like personal
   data (emails, Indian mobiles, Aadhaar-like numbers, PAN, names, addresses) are
   flagged with a per-column mask/drop/keep choice. Masking produces a derived
   copy; the original file is stored read-only with its hash.
3. **Profile + health check** - column types, human-friendly names, missing data,
   imbalance, duplicates, size warnings - each with a suggestion.
4. **Remediation** - the engine proposes concrete fixes (impute, de-duplicate,
   fix numbers-stored-as-text, drop mostly-empty columns, optional outlier caps);
   you tick what to apply, or skip. Applied fixes become one derived artifact.
5. **EDA agent** explains the dataset in plain language with charts and proposes
   concrete problem statements.
6. **Set direction** - pick a proposed problem or write your own. If the question
   does not match the data, the agent says so before you continue.
7. **Recommendation agent** picks the use case, ranks the models, and computes
   hyperparameter suggestions from your actual data. The **leakage sentinel**
   flags columns that contain the answer or would not exist at prediction time -
   each is a keep/exclude question; exclusions apply at training only.
8. **Feature agent** proposes optional engineered features (log scale, ratios,
   interactions, text length) - you tick the ones to include.
9. **Choose a path**: run the chosen model, auto-tune it first (you set how many
   combinations), or compare every model on a leaderboard.
10. **Results** land as a decision brief: executive summary, key findings, drivers,
    segment profiles, outlook, recommended actions, and a trust panel. A technical
    appendix holds metrics, the stability check, error slices, the
    decision-threshold tuner and probability check (binary classification),
    what-if scenarios (registered models), interpretation, and all charts.
    A **critic agent** reviews the brief before you see it (claims vs computed
    numbers, causal caveats), and a **trust tier** derived from the stability
    verdict reframes weak-evidence runs as "hypotheses to verify" everywhere -
    UI, markdown and PDF.
11. **Ask the data** - a grounded chat answers follow-up questions from the run's
    own numbers.
12. **Export** - in-app report page, markdown download, or a styled PDF. Every
    action along the way (uploads, agent calls with tokens and latency, approvals,
    declines, transforms, training, exports) is in the activity log, with a data
    lineage breadcrumb (original -> PII mask -> fixes -> features) on the results.

Everything the agents decide is logged in an agent activity drawer (who did what,
with which reasoning, in how many ms) and on the run's decision trail.

## Functionality

- **Four use cases, twelve models**

  | Use case | Models | Primary metric |
  |---|---|---|
  | Classification | Logistic Regression, Random Forest, XGBoost | F1 |
  | Regression | ElasticNet linear, Random Forest, XGBoost | RMSE (+ MAE, R²) |
  | Clustering | K-Means, DBSCAN, Agglomerative | Silhouette |
  | Forecasting | ARIMA/SARIMA, Exponential Smoothing (Holt-Winters), XGBoost lag forecaster | MAPE |

- **Human-in-the-loop gates** - agents propose, nothing runs until approved; the
  direction can be changed later and re-approved from any stage.
- **Data-aware settings** - hyperparameters suggested from the uploaded data, with
  the reasoning shown; a sparkline marks fields still on the suggested value.
- **Auto-tune** - randomized search around the suggestions with a per-model time
  budget; found settings pre-fill the form for approval, never auto-run.
- **Compare** - trains every model of the use case, ranks them, one click to
  generate insights with the winner.
- **Stability checks** - stratified k-fold cross-validation (classification),
  rolling-origin backtests (forecasting), subsample stability (clustering); the
  verdict feeds the trust panel, and honest skips explain when data is too small.
- **Feature engineering** - agent-proposed, human-approved, applied only to the
  approved run; engineered columns get plain-language names everywhere
  ("Spend per Income", "Balance (log scale)").
- **Datetime expansion** - date columns become model-usable parts automatically
  (days since latest, month, day of week).
- **Interactive charts** - forecast views (recent/full/zoom) with an uncertainty
  band and companion-series overlay; cluster scatter with point size, opacity and
  per-group filters; drivers, distributions, correlations, confusion matrix.
- **Plain language first** - friendly column names generated in the backend; raw
  headers only in tooltips; jargon behind info buttons with a metric glossary.
- **Excel support** - multi-sheet picker plus a join scout that proposes and
  executes safe cross-sheet joins (refuses row-multiplying keys).
- **Persistence** - datasets and runs survive backend restarts (SQLite).
- **Progress honesty** - expected time on every wait, elapsed timers,
  cannot-stop-midway notices.
- **Projects** - the top-level container: each project holds its own datasets,
  analyses, trained models, data dictionary and audit trail.
- **File librarian** - a new file in a non-empty project is classified
  automatically: same schema offers row-stacking (with provenance), a shared
  key offers a join, and a match with a trained model routes to scoring.
- **Model registry** - every training is a versioned model with purpose, exact
  data hash, settings, metrics and a loadable checkpoint. Retraining bumps the
  version with a computed what-changed summary; nothing is ever overwritten.
- **Score new data** - pick a model version, drop a fresh file: columns
  auto-match by meaning, the training-time preparation replays exactly, and
  you get predictions, a distribution chart and a CSV - or a plain-language
  stop if required columns are missing.
- **Shareable briefing** - a read-only link per analysis showing only the
  decision brief, trust panel, headline chart and grounded Q&A; prints clean.
- **Data dictionary** - your own column definitions beat AI guesses in
  tooltips and in every agent prompt.
- **Run comparison** - pick two analyses and get what changed: data drift
  (PSI), settings, metrics, drivers - with a narrative and markdown export.
- **Drift monitor** - drop a fresh file on any model version: schema changes,
  distribution shift (PSI / chi-square) per column, and - when the outcome
  came along - actual performance decay. Verdict is stable / drifting /
  degraded, and "degraded" is only said when accuracy really fell.
- **Error slices** - the held-out predictions are re-checked per group
  (category levels, numeric bands); groups the model serves clearly worse go
  red, become brief caveats, and tiny groups are honestly marked too-small.
- **Scenario what-if** - move up to three drivers from their observed
  baseline and see the predicted response, with extrapolation warnings and
  response curves; every answer carries a correlation-not-causation caveat.
- **Multi-series forecasting** - a store/region/product column fans out to
  parallel per-group forecasts, each backtested; a rollup chart, per-group
  table with honest skips, and one summary narrative.
- **Known drivers in forecasts** - promotion/price-style columns enter ARIMA
  and the XGBoost forecaster as regressors; Exponential Smoothing says
  plainly that it cannot use them.
- **Imbalance handling** - lopsided outcomes get balanced class weights
  proposed automatically, PR-AUC reported, and a decision-threshold slider
  with live precision/recall trade-off; the approved threshold is what
  scoring uses, not a blanket 0.5.
- **Calibration check** - out-of-fold reliability curve + Brier score decide
  whether the model's probabilities can be read literally; a miscalibrated
  verdict makes the brief talk in rankings, not percentages.
- **Automated intake** - standing rules recognize recurring files (new
  monthly extract, fresh applicant list) and queue score / drift-check /
  retrain proposals in an inbox. Approve executes, decline discards, and a
  cadence flags overdue arrivals - nothing ever auto-runs.
- **Graceful degradation** - every agent has a deterministic heuristic fallback
  used when no API key is set or a call fails; the UI badges each output as
  `claude` or `heuristic`.
- **Reproducible** - fixed random seed (42) everywhere randomness exists.

## The agents

| Agent | What it does | Fallback |
|---|---|---|
| EDA agent | Plain-language dataset briefing, friendly column names, problem statements | profiling heuristics |
| Recommendation agent | Use case + model ranking + question/data alignment check | rule-based ranking |
| Remediation agent | Phrases and prioritizes data-fix proposals for the goal | deterministic proposals |
| Feature agent | Curates engineered-feature candidates in plain language | deterministic picks |
| Interpretation agent | Judges results, explains metrics, suggests next steps | metric thresholds |
| Brief agent | Executive summary, recommended actions, watch-outs - written to the trust tier | template from insights |
| Critic agent | Reviews the brief: claims vs computed numbers, overclaim hedging, causal caveats | template caveat |
| Ask-the-data agent | Grounded Q&A over the run's own numbers | keyword lookup |
| Compare summarizer | Plain-language read of the leaderboard | metric comparison |

Deterministic engines do the numbers the agents talk about: profiler, health
checks, PII screen, remediation proposals, leakage sentinel, insight extraction,
settings suggester, autotune, stability checker, join scout. Python computes
every figure; the LLM only judges and phrases - so numbers cannot be
hallucinated. Every agent call is logged with provider, model, tokens, latency
and llm-or-fallback mode.

## Tech stack

**Backend** (`backend/`)
- FastAPI + Uvicorn, Pydantic request models, python-multipart uploads
- pandas + NumPy, scikit-learn, XGBoost, statsmodels (>= 0.14.6), openpyxl
- Claude via the `anthropic` SDK (model `claude-opus-5`, schema-validated JSON
  through structured outputs) behind a swappable `LLMProvider` interface
- fpdf2 for PDF export; stdlib `sqlite3` + pickle for persistence
- `engine/` is pure Python with no web imports: `profiler`, `health`, `insights`,
  `suggest`, `autotune`, `validate`, `features`, `joins`, `librarian`,
  `scoring`, `rundiff`, `drift`, `slices`, `scenario`, `multiforecast`,
  `calibration`, `intake`, `catalog/` (model plugins), `agents/`,
  `orchestrator` (approval-gated pipeline + decision log)
- Adding a model = one class in `engine/catalog/` (subclass `ModelPlugin`,
  decorate with `@register`); its `param_schema()` auto-generates the UI form

**Frontend** (`frontend/`)
- React 18 + Vite + TypeScript
- Tailwind CSS v4 (`@tailwindcss/vite`, design tokens via `@theme`) - light
  glassmorphism theme
- Recharts for all charts, lucide-react icons
- Screens in `src/components/screens/`; API client and mirrored backend types in
  `src/api/` and `src/types.ts`

## Quick start

### Backend (port 8000)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# optional: put ANTHROPIC_API_KEY=... in backend\.env (heuristic mode without it)
uvicorn app.main:app --reload --port 8000
```

### Frontend (port 5173, proxies /api to 8000)

```powershell
cd frontend
npm install
npm run dev
```

Sample datasets live in `backend/sample_data/` (regenerate with
`python make_samples.py` from that folder).

## Notes and limits (POC scope)

- Windows-friendly on purpose: Prophet is excluded (needs a C++ toolchain);
  forecasting uses ARIMA/ExpSmoothing/XGBoost-lags instead.
- Uploads are capped at 50 MB; stability and calibration checks skip very
  large (or very small) data with an honest note.
- Future driver values in forecasts carry the last known value forward -
  stated in the result rather than hidden.
- No auth or deployment hardening - this is a local proof of concept.
