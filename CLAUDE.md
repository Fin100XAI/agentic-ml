# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project

**Agentic ML Workbench** - an industry-agnostic, LLM-agent-driven ML pipeline POC.
A user uploads a CSV; agents profile it (EDA), recommend a model, and - with the
human approving each step - train it and explain the results with charts and
commentary. Every decision renders as a node in a wire diagram.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full design.

## Stack & layout

- **backend/** - FastAPI + pandas/scikit-learn/XGBoost/statsmodels; Claude via the
  `anthropic` SDK behind a swappable `LLMProvider` (`engine/llm/`).
  - `engine/` is pure Python (no web imports): `profiler.py`, `catalog/` (model
    plugins), `agents/`, `orchestrator.py` (approval-gated pipeline + decision log).
  - `app/` is the FastAPI layer: `api/` routes, in-memory `store.py`.
- **frontend/** - React + Vite + TS + Tailwind v4; React Flow (wire diagram),
  Recharts (result charts). Screens live in `src/components/screens/`.

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
- Agents must degrade gracefully: every agent has a deterministic heuristic
  fallback used when `ANTHROPIC_API_KEY` is unset or a call fails.
- Fixed random seed (42) everywhere randomness exists - runs are reproducible.
- All engine outputs must be JSON-safe (no NaN/inf; see `profiler._clean`).
- Frontend types in `src/types.ts` mirror backend response shapes - keep in sync.
- API key goes in `backend/.env` (`ANTHROPIC_API_KEY=...`); never commit it.

## Gotchas

- Windows: Prophet is deliberately excluded (needs C++ toolchain); forecasting
  uses ARIMA/ExpSmoothing/XGBoost-lags instead.
- statsmodels must be ≥0.14.6 to work with scipy ≥1.16.
- The in-memory store loses datasets/runs on backend restart (POC scope).
