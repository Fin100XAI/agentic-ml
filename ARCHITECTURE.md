# Architecture — Agentic ML Workbench (FIN_ML_POC)

An industry-agnostic, LLM-agent-driven workbench. A user uploads a CSV; LLM agents
profile it, run EDA, recommend an appropriate ML approach, and (with the human
approving each step) train a model, then explain the results with charts and
written commentary. Every meaningful decision is human-approved and visualized as a
node in a **wire diagram** of the run.

> Status: POC. Runs locally (two dev servers). Designed so the ML/agent core is
> independent of the web layer and the LLM provider is swappable.

---

## 1. Principles

- **Human-in-the-loop.** Agents *propose*; nothing advances without explicit human approval.
- **Provider-swappable.** Claude now, open-source models later — all LLM calls go through one `LLMProvider` interface.
- **Pluggable model catalog.** Each ML model is one self-describing plugin; adding a model is a single file, and the UI hyperparameter form is generated from its schema.
- **Industry-agnostic.** No domain assumptions — the profiler infers structure from the data itself.
- **UI-independent core.** The `engine` package (profiler, catalog, agents, orchestrator) has no FastAPI/React imports and could run from a script or notebook.

---

## 2. High-level design

Three tiers:

```
Frontend (React + Vite + TS + Tailwind + shadcn/ui)
  Upload · EDA review · Recommendation/approval · Hyperparameter form
  · Results dashboard (Recharts) · Wire diagram (React Flow)
        │  REST (JSON) + SSE for progress
Backend (FastAPI)
  Routes · Run/session store · Orchestrator (drives pipeline, enforces approval gates)
        │
Engine (pure Python, no web deps)
  Profiler/EDA · Model catalog · Agents (Claude) · LLMProvider
```

---

## 3. The agent pipeline (approval-gated)

Each stage produces a proposal the human must approve before the next stage runs.
The orchestrator records every stage as a **decision node** for the wire diagram.

| # | Stage | Agent | Output | Gate |
|---|-------|-------|--------|------|
| 1 | **Profile & EDA** | EDA agent | Inferred schema, stats, missingness, correlations, candidate targets/problem type, plain-language summary | Human reviews; may add a free-text question ("what do you want to understand?") |
| 2 | **Recommend** | Recommendation agent | Chosen use case (classification/clustering/forecasting), ranked model(s) with rationale, proposed hyperparameters | Human approves / edits model & hyperparameters |
| 3 | **Run** | — (execution) | Trained model, metrics, prediction artifacts | Human approves the run |
| 4 | **Interpret** | Interpretation agent | Charts + written commentary, findings, next-step suggestions | Presented to human |

The **wire diagram** renders stages 1→4 as nodes, each showing the decision made,
the agent's recommendation, and its approval state.

---

## 4. Model catalog (2–3 per use case)

The recommendation agent ranks and picks; the human can override.

| Use case | Models | Key metrics |
|----------|--------|-------------|
| **Classification** | Logistic Regression · Random Forest · XGBoost | accuracy, precision/recall, F1, ROC-AUC, confusion matrix |
| **Clustering** | K-Means · DBSCAN · Agglomerative | silhouette, Davies–Bouldin, cluster sizes |
| **Forecasting** | ARIMA/SARIMA · Prophet · Exponential Smoothing | MAE, RMSE, MAPE, forecast vs. actual |

**Model plugin interface** (each model implements):

```
name, use_case, description
param_schema()      -> JSON-schema-like spec that drives the UI hyperparameter form
default_hyperparams()
fit(X, y, hyperparams)
predict(model, X)
metrics(model, X, y) -> dict
artifacts(...)      -> chart-ready data (confusion matrix, cluster coords, forecast series, ...)
```

---

## 5. LLM layer

```
LLMProvider (interface): complete(messages, tools?) -> response
  └── ClaudeProvider  (Anthropic SDK; model id from config)
  └── (future) OpenSourceProvider / local
```

Agents are thin: each builds a prompt from structured engine data, calls the
provider, and returns a validated structured result. The provider is selected by
config/env so swapping to an open-source model later touches one place. (Exact
Claude model ids and SDK usage are pinned from the current Claude API reference at
implementation time.)

---

## 6. Backend layout

```
backend/
  app/
    main.py                 # FastAPI app, CORS, router mount
    config.py               # settings/env (API key, model id, provider)
    api/
      routes_datasets.py    # upload, profile
      routes_runs.py        # recommend, set-hyperparams, run, results, decisions
    store.py                # in-memory run/session store (POC)
    schemas.py              # pydantic request/response models
  engine/
    profiler.py             # EDA / data profiling
    llm/
      base.py               # LLMProvider interface
      claude.py             # Claude implementation
    agents/
      eda_agent.py
      recommend_agent.py
      interpret_agent.py
    catalog/
      base.py               # model plugin interface + registry
      classification.py
      clustering.py
      forecasting.py
    orchestrator.py         # pipeline + approval gates + decision log
  requirements.txt
  .env.example
```

## 7. Frontend layout

```
frontend/
  src/
    api/client.ts           # typed fetch wrapper + SSE
    pages/                   # Upload, EDA, Recommend, Hyperparams, Results
    components/
      WireDiagram.tsx        # React Flow decision graph
      charts/                # Recharts wrappers
      ui/                    # shadcn/ui primitives
    lib/, hooks/, types.ts
  index.html, vite.config.ts, tailwind.config.js
```

---

## 8. Core API (POC)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/datasets` | Upload CSV → returns dataset id |
| POST | `/api/datasets/{id}/profile` | Run EDA agent → EDA summary |
| POST | `/api/runs` | Start a run (dataset id + user question) |
| POST | `/api/runs/{id}/recommend` | Recommendation agent → ranked models + hyperparams |
| POST | `/api/runs/{id}/hyperparams` | Approve/override model + hyperparameters |
| POST | `/api/runs/{id}/execute` | Train/run model |
| POST | `/api/runs/{id}/interpret` | Interpretation agent → commentary |
| GET  | `/api/runs/{id}` | Full run state (decisions, results) for the wire diagram |
| GET  | `/api/runs/{id}/events` | SSE progress stream |

---

## 9. Out of scope for the POC (later)

- Persistence (DB), auth/multi-user, background job queue.
- Deployment/hosting, model versioning/registry.
- Deep-learning models, automated feature engineering beyond basics.
- Open-source LLM provider implementation (interface is ready; impl is later).

---

## 10. Run (local)

```bash
# backend
cd backend && python -m venv .venv && .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# frontend
cd frontend && npm install && npm run dev   # http://localhost:5173
```
