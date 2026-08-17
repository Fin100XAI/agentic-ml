# Architecture - Agentic ML Workbench

An industry-agnostic, LLM-agent-driven decision-support workbench. A user
uploads a spreadsheet; agents screen it for personal data, profile it, propose
fixes, explore it, recommend and train a model, and produce a policy-maker
brief - with a human approving every consequential step and every action
landing in one auditable trail.

> Status: POC, local two-server dev setup. The engine is web-independent and
> the LLM provider is swappable.

---

## 1. Principles (see CLAUDE.md for the binding rules)

- **Originals are immutable.** Every transformation produces a derived artifact
  with lineage pointers; raw uploads are stored read-only with a SHA-256 hash.
- **Everything is logged.** One append-only activity log records file events,
  agent calls (provider/model/tokens/latency/mode), approvals, declines,
  transforms, training and exports.
- **LLMs judge and phrase; Python computes.** Every number is deterministic.
  Every agent has a heuristic fallback; the UI badges outputs `claude` or
  `heuristic`.
- **Nothing runs without approval.** Agents propose; the orchestrator gates.
- **Plain language first**; jargon behind info buttons; fixed seed 42.

## 2. Tiers

```
Frontend  React 18 + Vite + TS + Tailwind v4 + Recharts
          screens in src/components/screens, types mirrored in src/types.ts
   |  REST /api (Vite proxy)
Backend   FastAPI (app/): routes, SQLite store, telemetry glue, exports
   |
Engine    pure Python (engine/): profiler, health, pii, remediation, leakage,
          features, joins, insights, validate, suggest, autotune, librarian,
          scoring, rundiff, drift, slices, scenario, multiforecast,
          calibration, intake, catalog/ (model plugins), agents/, orchestrator
```

The engine has no web imports. App-layer concerns (activity log, artifact
ledger) reach it only through injected hooks (`on_event`, `on_artifact`,
provider `on_call`) attached in `app/telemetry.py`.

## 3. The pipeline (every gate is a human decision)

| # | Stage | Who | Gate |
|---|-------|-----|------|
| 0 | **PII screen** at upload | `engine/pii.py` (regex/heuristics, Indian formats first-class) | Per-column mask/drop/keep; runs are 409-blocked until reviewed. Masking = one `pii_mask` derived artifact. **No LLM sees rows before this.** |
| 1 | **Profile + health** | profiler + `health.py` | - |
| 2 | **Remediation** | `remediation.py` proposals, phrased by the remediation agent | Tick fixes / skip; applying = one `remediation` artifact, re-profiled |
| 3 | **EDA** | EDA agent (friendly column names, findings, problem statements) | Human sets/approves the direction; alignment check warns on mismatched questions |
| 4 | **Recommend** | Recommendation agent (use case + ranked models) + settings suggester + **leakage sentinel** (`leakage.py`) + **feature agent** (`features.py`) | Human picks model/settings, ticks engineered features, answers each sentinel flag (keep/exclude) |
| 5 | **Execute** | Model plugin; engineered features become a `feature_eng` artifact; exclusions apply at train time only | - |
| 6 | **Stability + calibration checks** | `validate.py`: k-fold (classification/regression), rolling-origin (forecasting), subsample (clustering). `calibration.py` (binary classification): out-of-fold reliability curve + Brier score, verdict well calibrated / over- / underconfident | - |
| 7 | **Interpret + insights** | Interpretation agent; insight engine (drivers, segments, outlook, residuals) | - |
| 8 | **Trust tier + brief + critic** | tier = evidence downgraded by an unstable verdict; brief agent writes to the tier; **critic agent** verifies claims against computed numbers, hedges overclaims, adds causal caveats | Weak tier reframes actions as "Hypotheses to verify" across UI, markdown and PDF |

Compare (all models ranked) and Auto-tune (randomized search around the
suggestions, user-set combo count) branch from stage 4.

## 3b. Projects, models and the file librarian (Phase 2)

- **Projects** are the top-level container: datasets, runs, artifacts, models,
  glossary and activity all scope to one. A one-time migration created
  "Default Project" for pre-project data.
- **Librarian** (`librarian.py`): a file uploaded into a non-empty project is
  classified by normalized schema fingerprint - same schema proposes STACK
  (union + `source_file` provenance), a shared high-overlap key proposes JOIN,
  a match with a registered model's schema routes toward scoring. All
  assemblies are approval-gated derived artifacts.
- **Model registry** (`model_registry` table): every completed training is a
  versioned entry - purpose, training-data sha256, raw + processed feature
  lists, settings, metrics, stability verdict, content-addressed checkpoint.
  Identity = project + use case + target + algorithm; retraining bumps the
  version, supersedes the old ACTIVE row, and stores a computed change
  summary (data/settings/metric deltas). Nothing is overwritten.
- **Scoring** (`scoring.py`): a fresh file is schema-reconciled (renamed
  columns auto-map, missing features hard-stop in plain language), pushed
  through the SAME training-time lineage (PII mask, remediation fixes,
  engineered features, exclusions), aligned to the trained feature list, and
  predicted. Outputs are score artifacts with CSV download.
- **Briefing view**: unlisted read-only `#/brief/{runId}` route - brief,
  trust panel, headline chart, Ask-the-Data; zero analyst controls or
  mutating calls; print-clean.
- **Glossary** (`glossary` table): the user's own column definitions,
  keyword-matched onto datasets; they override guessed meanings in tooltips
  and are injected into agent prompts with prefer-the-human instruction.
- **Run diff** (`rundiff.py`): two same-kind runs compared - rows/period/PSI
  drift, settings and metric deltas, driver/segment/direction changes - with
  a phrased narrative and markdown export.

## 3c. Monitoring and operations (Phase 3)

- **Drift monitor** (`drift.py`): a fresh file vs a model version's training
  data - schema changes, PSI on numerics, chi-square on categoricals, and
  (when the outcome came along) performance decay. Verdict `stable |
  drifting | degraded`; "degraded" only when the primary metric is >15%
  relatively worse, never from distribution shift alone.
- **Error slices** (`slices.py`): the held-out predictions are re-grouped by
  every low-cardinality column (numerics banded by quartile); groups whose
  primary metric falls clearly below overall go red and become brief caveats.
  Groups under 20 rows are reported `too_small`, not judged.
- **Scenario what-if** (`scenario.py`): perturb up to three features from the
  registry-stored baseline; the perturbed frame replays the FULL training
  lineage before predicting. Out-of-range moves are flagged as extrapolation;
  response curves plot one feature swept across its observed range. Every
  scenario output carries a fixed correlation-not-causation caveat.
- **Multi-series forecasting** (`multiforecast.py`): a group column (store,
  region, product) fans out to per-group forecasts in parallel, each with its
  own backtest and direction; groups with under 20 points are skipped with
  the reason shown. A sum/mean rollup and ONE compact summary table feed a
  single LLM call - never one call per group.
- **Exogenous regressors** (forecasting catalog): known driver columns enter
  ARIMA as SARIMAX exog and the XGBoost forecaster as contemporaneous +
  1-lag features; Exponential Smoothing honestly reports it cannot use them.
  Futures carry the last known value forward, stated in the result.
- **Imbalance handling** (classification catalog + `suggest.py`): lopsided
  targets (majority >75%) get `class_weight=balanced` / `scale_pos_weight`
  proposals and PR-AUC alongside ROC-AUC. Every binary run computes a
  19-point threshold curve; the results screen has a slider with live
  precision/recall/F1 and confusion matrix, and the approved threshold is
  stored on the registry entry - scoring labels rows with it, not 0.5.
- **Intake inbox** (`intake.py` + `intake_rules`/`intake_items` tables): a
  standing rule ties a model version to an action (score / drift / retrain)
  with an expected cadence. New uploads matching the rule's normalized
  columns (>= 90% coverage, target excluded) are filed as pending inbox
  items. Approval executes the action through the same code paths as doing
  it by hand; decline discards. Cadence never auto-fires anything - overdue
  rules are only flagged.

## 4. Data layer

- `artifacts` table: id, kind (original|derived), parent_ids, transform_type
  (upload | rename | pii_mask | remediation | join | stack | feature_eng |
  score), transform_params, sha256, created_at, file_path.
- Column renames are approved at upload (before the PII screen): a `rename`
  artifact records the mapping, PII findings are remapped, and the alias map
  is stored on the dataset so future files arriving with the ORIGINAL
  headers still match at scoring/drift time. Multi-sheet workbooks whose
  sheets share a normalized schema get a one-click row-wise combine with a
  `source_sheet` provenance column.
- Files live content-addressed in `backend/artifact_store/` (originals
  read-only). `GET /api/artifacts/{id}/lineage` walks the chain; the UI shows
  a breadcrumb (original -> PII mask -> fixes -> features) with hashes in
  tooltips.
- Runs record the artifact they trained on; remediated frames are reattached
  from their artifact on restart.
- Excel: multi-sheet picker plus a join scout (`joins.py`) that proposes safe
  cross-sheet joins (refuses row-multiplying keys).

## 5. Activity log

`activity_log` (Postgres-portable): ts, actor, event_type (file_upload |
pii_review | agent_call | approval | decline | transform | train | score |
drift | intake | export | error), dataset/artifact/run ids, provider, model,
tokens in/out, latency,
mode (llm | fallback), JSON payload. The Claude provider self-reports usage
per call; orchestrator events map through `app/telemetry.py`. `GET
/api/activity` filters; `/api/activity.csv` exports for Excel. The frontend
Log screen is the full view; the per-run drawer stays for context.

## 6. Model catalog

One plugin class per model in `engine/catalog/` (`@register`,
`param_schema()` auto-generates the UI form, `build_estimator()` powers CV).

| Use case | Models | Primary metric |
|---|---|---|
| Classification | logistic_regression, random_forest, xgboost | F1 |
| Regression | elastic_net (alpha 0 = OLS), rf_regressor, xgb_regressor | RMSE (+ MAE, R2) |
| Clustering | kmeans, dbscan, agglomerative | Silhouette |
| Forecasting | arima, exp_smoothing, xgb_forecast | MAPE |

Preprocessing (`catalog/preprocess.py`): datetime expansion to model-usable
parts, one-hot low-cardinality categoricals, median impute, ID drop.

## 7. Agents (all with heuristic fallbacks)

EDA, Recommendation (+alignment), Remediation, Feature, Interpretation,
Brief, Critic, Ask-the-data - each a schema-validated JSON call through
`LLMProvider` (Claude via `output_config` structured outputs). Deterministic
engines around them: profiler, health, PII screen, leakage sentinel, insight
extraction, settings suggester, autotune, stability checker, join scout.

## 8. Storage

SQLite via stdlib `sqlite3` (`app/store.py`): datasets (frame + artifact
pointer + PII state), runs (pickled state sans frame), artifacts,
activity_log, projects, glossary, model_registry (versioned entries with
checkpoint paths, feature ranges, baseline and decision threshold),
intake_rules, intake_items. Schema stays Postgres-portable. One-time
migrations wrap pre-artifact datasets and backfill old decision trails
into the log.

## 9. Exports

Brief-first markdown (`app/report.py`) and PDF (`app/pdf_report.py`, fpdf2,
rendered from the same markdown so they cannot drift). Trust-tier framing
carries into both; exports are logged.
