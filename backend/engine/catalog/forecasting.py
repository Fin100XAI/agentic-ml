"""Forecasting models: ARIMA/SARIMA, Exponential Smoothing, XGBoost (lag features)."""
from __future__ import annotations

import warnings
from typing import Any

import numpy as np
import pandas as pd

from .base import ModelPlugin, ParamSpec, register
from .preprocess import RANDOM_SEED


def _prepare_series(
    df: pd.DataFrame, target: str | None, time_column: str | None
) -> tuple[pd.Series, list[str]]:
    """Return (time-ordered numeric series, iso timestamps)."""
    if not target or target not in df.columns:
        raise ValueError("Forecasting requires a numeric target column.")
    work = df.copy()

    if time_column and time_column in work.columns:
        ts = pd.to_datetime(work[time_column], errors="coerce", format="mixed")
        work = work.assign(_ts=ts).dropna(subset=["_ts"]).sort_values("_ts")
        stamps = [t.isoformat() for t in work["_ts"]]
    else:
        stamps = [str(i) for i in range(len(work))]

    series = pd.to_numeric(work[target], errors="coerce").dropna()
    stamps = [stamps[i] for i in range(len(series))] if len(stamps) >= len(series) else stamps
    if len(series) < 20:
        raise ValueError("Need at least 20 observations to forecast.")
    series = series.reset_index(drop=True)
    return series, stamps


def _forecast_metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, Any]:
    err = actual - predicted
    mae = float(np.mean(np.abs(err)))
    rmse = float(np.sqrt(np.mean(err**2)))
    nonzero = actual != 0
    mape = float(np.mean(np.abs(err[nonzero] / actual[nonzero])) * 100) if nonzero.any() else None
    return {
        "mae": round(mae, 4),
        "rmse": round(rmse, 4),
        "mape_pct": round(mape, 2) if mape is not None else None,
    }


def _build_result(
    series: pd.Series,
    stamps: list[str],
    holdout: int,
    fitted_test: np.ndarray,
    future: np.ndarray,
) -> dict[str, Any]:
    """Assemble metrics + chart series (history, test predictions, future forecast)."""
    actual_test = series.iloc[-holdout:].values
    metrics = _forecast_metrics(actual_test, fitted_test)
    metrics["n_observations"] = int(len(series))
    metrics["holdout_size"] = holdout

    history = [
        {"t": stamps[i] if i < len(stamps) else str(i), "actual": round(float(v), 4)}
        for i, v in enumerate(series.values)
    ]
    test_start = len(series) - holdout
    for j, v in enumerate(fitted_test):
        history[test_start + j]["predicted"] = round(float(v), 4)

    forecast = [
        {"t": f"+{j + 1}", "forecast": round(float(v), 4)} for j, v in enumerate(future)
    ]

    return {
        "metrics": metrics,
        "artifacts": {"series": history, "forecast": forecast},
    }


@register
class ArimaModel(ModelPlugin):
    key = "arima"
    name = "ARIMA / SARIMA"
    use_case = "forecasting"
    description = "Classical statistical model capturing trend and autocorrelation (optionally seasonality)."
    strengths = "Solid statistical baseline; interpretable orders; handles trend via differencing and seasonality via the seasonal period."

    def param_schema(self) -> list[ParamSpec]:
        return [
            ParamSpec("p", "AR order (p)", "int", 2, "Autoregressive lags.", min=0, max=10, step=1),
            ParamSpec("d", "Differencing (d)", "int", 1, "Degree of differencing for trend.", min=0, max=3, step=1),
            ParamSpec("q", "MA order (q)", "int", 2, "Moving-average lags.", min=0, max=10, step=1),
            ParamSpec("seasonal_period", "Seasonal period", "int", 0, "0 = non-seasonal; e.g. 12 for monthly-with-yearly-cycle.", min=0, max=52, step=1),
            ParamSpec("horizon", "Forecast horizon", "int", 10, "Steps ahead to forecast.", min=1, max=100, step=1),
        ]

    def run(self, df, hyperparams, target=None, features=None, time_column=None):
        from statsmodels.tsa.statespace.sarimax import SARIMAX

        series, stamps = _prepare_series(df, target, time_column)
        horizon = hyperparams["horizon"]
        holdout = max(5, min(len(series) // 5, 50))
        train = series.iloc[:-holdout]

        order = (hyperparams["p"], hyperparams["d"], hyperparams["q"])
        sp = hyperparams["seasonal_period"]
        seasonal_order = (1, 1, 1, sp) if sp and sp > 1 else (0, 0, 0, 0)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fit = SARIMAX(
                train.values, order=order, seasonal_order=seasonal_order,
                enforce_stationarity=False, enforce_invertibility=False,
            ).fit(disp=False)
            test_pred = fit.forecast(steps=holdout)
            full_fit = SARIMAX(
                series.values, order=order, seasonal_order=seasonal_order,
                enforce_stationarity=False, enforce_invertibility=False,
            ).fit(disp=False)
            future = full_fit.forecast(steps=horizon)

        return _build_result(series, stamps, holdout, np.asarray(test_pred), np.asarray(future))


@register
class ExpSmoothingModel(ModelPlugin):
    key = "exp_smoothing"
    name = "Exponential Smoothing (Holt-Winters)"
    use_case = "forecasting"
    description = "Weighted-average model with explicit trend and seasonal components."
    strengths = "Very robust on smooth series with clear trend/seasonality; few parameters; fast."

    def param_schema(self) -> list[ParamSpec]:
        return [
            ParamSpec("trend", "Trend", "select", "add", "Trend component type.", options=["add", "mul", "none"]),
            ParamSpec("seasonal", "Seasonality", "select", "none", "Seasonal component type.", options=["add", "mul", "none"]),
            ParamSpec("seasonal_period", "Seasonal period", "int", 12, "Season length (used when seasonality enabled).", min=2, max=52, step=1),
            ParamSpec("horizon", "Forecast horizon", "int", 10, "Steps ahead to forecast.", min=1, max=100, step=1),
        ]

    def run(self, df, hyperparams, target=None, features=None, time_column=None):
        from statsmodels.tsa.holtwinters import ExponentialSmoothing

        series, stamps = _prepare_series(df, target, time_column)
        horizon = hyperparams["horizon"]
        holdout = max(5, min(len(series) // 5, 50))
        train = series.iloc[:-holdout]

        trend = None if hyperparams["trend"] == "none" else hyperparams["trend"]
        seasonal = None if hyperparams["seasonal"] == "none" else hyperparams["seasonal"]
        sp = hyperparams["seasonal_period"] if seasonal else None
        if seasonal and len(train) < 2 * (sp or 2):
            seasonal, sp = None, None  # not enough data for the requested seasonality

        # Multiplicative components require strictly positive data.
        if (trend == "mul" or seasonal == "mul") and (series <= 0).any():
            trend = "add" if trend else None
            seasonal = "add" if seasonal else None

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fit = ExponentialSmoothing(train.values, trend=trend, seasonal=seasonal, seasonal_periods=sp).fit()
            test_pred = fit.forecast(holdout)
            full = ExponentialSmoothing(series.values, trend=trend, seasonal=seasonal, seasonal_periods=sp).fit()
            future = full.forecast(horizon)

        return _build_result(series, stamps, holdout, np.asarray(test_pred), np.asarray(future))


@register
class XGBForecastModel(ModelPlugin):
    key = "xgb_forecast"
    name = "XGBoost Forecaster (lag features)"
    use_case = "forecasting"
    description = "Gradient boosting over lagged values; a machine-learning approach to forecasting."
    strengths = "Captures non-linear autoregressive patterns classical models miss; good with enough history; no stationarity assumptions."

    def param_schema(self) -> list[ParamSpec]:
        return [
            ParamSpec("n_lags", "Lag window", "int", 12, "How many past values feed each prediction.", min=2, max=60, step=1),
            ParamSpec("n_estimators", "Boosting rounds", "int", 200, "Number of boosted trees.", min=10, max=1000, step=10),
            ParamSpec("learning_rate", "Learning rate", "float", 0.05, "Lower = more robust with more rounds.", min=0.01, max=0.5, step=0.01),
            ParamSpec("horizon", "Forecast horizon", "int", 10, "Steps ahead to forecast (recursive).", min=1, max=100, step=1),
        ]

    def run(self, df, hyperparams, target=None, features=None, time_column=None):
        from xgboost import XGBRegressor

        series, stamps = _prepare_series(df, target, time_column)
        n_lags = min(hyperparams["n_lags"], len(series) // 3)
        if n_lags < 2:
            raise ValueError("Series too short for the requested lag window.")
        horizon = hyperparams["horizon"]
        holdout = max(5, min(len(series) // 5, 50))

        values = series.values.astype(float)
        X_all = np.array([values[i - n_lags:i] for i in range(n_lags, len(values))])
        y_all = values[n_lags:]
        split = len(y_all) - holdout

        model = XGBRegressor(
            n_estimators=hyperparams["n_estimators"],
            learning_rate=hyperparams["learning_rate"],
            max_depth=4,
            random_state=RANDOM_SEED,
        )
        model.fit(X_all[:split], y_all[:split])

        # Recursive prediction over the holdout window.
        window = list(values[split + n_lags - n_lags: split + n_lags])[-n_lags:]
        test_pred = []
        for _ in range(holdout):
            p = float(model.predict(np.array(window[-n_lags:]).reshape(1, -1))[0])
            test_pred.append(p)
            window.append(values[split + n_lags + len(test_pred) - 1] if split + n_lags + len(test_pred) - 1 < len(values) else p)

        # Refit on everything, forecast the future recursively.
        model_full = XGBRegressor(
            n_estimators=hyperparams["n_estimators"],
            learning_rate=hyperparams["learning_rate"],
            max_depth=4,
            random_state=RANDOM_SEED,
        )
        model_full.fit(X_all, y_all)
        window = list(values[-n_lags:])
        future = []
        for _ in range(horizon):
            p = float(model_full.predict(np.array(window[-n_lags:]).reshape(1, -1))[0])
            future.append(p)
            window.append(p)

        return _build_result(series, stamps, holdout, np.asarray(test_pred), np.asarray(future))
