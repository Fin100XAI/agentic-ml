# Agentic ML Workbench (FIN_ML_POC)

An industry-agnostic, LLM-agent-driven ML workbench. Upload a CSV and agents profile
it, run EDA, recommend an ML approach, and - with you approving each step - train a
model and explain the results with charts and written commentary. Every decision is
human-approved and shown as a node in a wire diagram of the run.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full design.

## Stack

- **Frontend:** React + Vite + TypeScript, Tailwind + shadcn/ui, React Flow, Recharts
- **Backend:** FastAPI, pandas, scikit-learn, XGBoost, statsmodels/Prophet
- **LLM:** Claude (Anthropic), behind a swappable `LLMProvider` interface

## Quick start

### Backend

```bash
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # Windows PowerShell
pip install -r requirements.txt
copy .env.example .env               # then add your ANTHROPIC_API_KEY
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev                          # http://localhost:5173
```

## Use cases (POC)

- **Classification** - Logistic Regression, Random Forest, XGBoost
- **Clustering** - K-Means, DBSCAN, Agglomerative
- **Forecasting** - ARIMA/SARIMA, Prophet, Exponential Smoothing
