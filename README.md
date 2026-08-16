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
2. **Profile + health check** - column types, human-friendly column names, missing
   data, imbalance, duplicates, size warnings - each with a suggestion.
3. **EDA agent** explains the dataset in plain language with charts (histograms,
   top values, correlations, missingness) and proposes concrete problem statements.
4. **Set direction** - pick a proposed problem or write your own. If the question
   does not match the data, the agent says so before you continue.
5. **Recommendation agent** picks the use case, ranks the models, and computes
   hyperparameter suggestions from your actual data (silhouette sweeps for k,
   k-NN eps for DBSCAN, cadence/autocorrelation for seasonality).
6. **Feature agent** proposes optional engineered features (log scale for skewed
   columns, ratios and interactions of the strongest pair, text length) - you tick
   the ones to include.
7. **Choose a path**: run the chosen model, auto-tune it first (you set how many
   combinations), or compare every model on a leaderboard.
8. **Results** land as a decision brief: executive summary, key findings, drivers,
   segment profiles, outlook, recommended actions, and a trust panel. A technical
   appendix holds metrics, a stability check, model interpretation, and all charts.
9. **Ask the data** - a grounded chat answers follow-up questions from the run's
   own numbers.
10. **Export** - in-app report page, markdown download, or a styled PDF.

Everything the agents decide is logged in an agent activity drawer (who did what,
with which reasoning, in how many ms) and on the run's decision trail.

## Functionality

- **Three use cases, nine models**

  | Use case | Models | Primary metric |
  |---|---|---|
  | Classification | Logistic Regression, Random Forest, XGBoost | F1 |
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
- **Graceful degradation** - every agent has a deterministic heuristic fallback
  used when no API key is set or a call fails; the UI badges each output as
  `claude` or `heuristic`.
- **Reproducible** - fixed random seed (42) everywhere randomness exists.

## The agents

| Agent | What it does | Fallback |
|---|---|---|
| EDA agent | Plain-language dataset briefing, friendly column names, problem statements | profiling heuristics |
| Recommendation agent | Use case + model ranking + question/data alignment check | rule-based ranking |
| Feature agent | Curates engineered-feature candidates in plain language | deterministic picks |
| Interpretation agent | Judges results, explains metrics, suggests next steps | metric thresholds |
| Brief agent | Executive summary, recommended actions, watch-outs | template from insights |
| Ask-the-data agent | Grounded Q&A over the run's own numbers | keyword lookup |
| Compare summarizer | Plain-language read of the leaderboard | metric comparison |

Deterministic engines do the numbers the agents talk about: profiler, health
checks, insight extraction (drivers, segments, outlook), settings suggester,
autotune, stability checker, join scout. Python computes every figure; the LLM
only judges and phrases - so numbers cannot be hallucinated.

## Tech stack

**Backend** (`backend/`)
- FastAPI + Uvicorn, Pydantic request models, python-multipart uploads
- pandas + NumPy, scikit-learn, XGBoost, statsmodels (>= 0.14.6), openpyxl
- Claude via the `anthropic` SDK (model `claude-opus-5`, schema-validated JSON
  through structured outputs) behind a swappable `LLMProvider` interface
- fpdf2 for PDF export; stdlib `sqlite3` + pickle for persistence
- `engine/` is pure Python with no web imports: `profiler`, `health`, `insights`,
  `suggest`, `autotune`, `validate`, `features`, `joins`, `catalog/` (model
  plugins), `agents/`, `orchestrator` (approval-gated pipeline + decision log)
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
- Uploads are capped at 50 MB; stability checks skip above 50k rows with an
  honest note.
- Forecasting is single-series; other numeric columns appear as chart overlays,
  not regressors.
- No auth or deployment hardening - this is a local proof of concept.
