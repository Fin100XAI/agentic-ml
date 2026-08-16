"""Generate sample CSVs for exercising all four use cases."""
from __future__ import annotations

import numpy as np
import pandas as pd

rng = np.random.default_rng(42)


def churn(n: int = 800) -> pd.DataFrame:
    """Classification: customer churn."""
    tenure = rng.integers(1, 72, n)
    monthly = rng.uniform(20, 120, n).round(2)
    support_calls = rng.poisson(2, n)
    contract = rng.choice(["month-to-month", "one-year", "two-year"], n, p=[0.5, 0.3, 0.2])
    logit = -2.5 + 0.03 * (72 - tenure) + 0.015 * monthly + 0.35 * support_calls \
        - 1.2 * (contract != "month-to-month")
    churn_flag = (rng.random(n) < 1 / (1 + np.exp(-logit))).astype(int)
    return pd.DataFrame({
        "customer_id": [f"C{i:05d}" for i in range(n)],
        "tenure_months": tenure,
        "monthly_charge": monthly,
        "support_calls": support_calls,
        "contract_type": contract,
        "churned": churn_flag,
    })


def segments(n: int = 600) -> pd.DataFrame:
    """Clustering: customer spending segments."""
    centers = [(25, 30, 2), (55, 80, 8), (40, 150, 15)]
    rows = []
    for cx, cy, cz in centers:
        k = n // len(centers)
        rows.append(np.column_stack([
            rng.normal(cx, 6, k), rng.normal(cy, 15, k), np.abs(rng.normal(cz, 3, k)),
        ]))
    data = np.vstack(rows)
    return pd.DataFrame({
        "age": data[:, 0].round(0),
        "monthly_spend": data[:, 1].round(2),
        "purchases_per_month": data[:, 2].round(1),
    })


def sales(n: int = 156) -> pd.DataFrame:
    """Forecasting: weekly sales with trend + yearly seasonality."""
    t = np.arange(n)
    value = 1000 + 8 * t + 200 * np.sin(2 * np.pi * t / 52) + rng.normal(0, 60, n)
    dates = pd.date_range("2023-01-01", periods=n, freq="W")
    return pd.DataFrame({"week": dates.strftime("%Y-%m-%d"), "sales": value.round(2)})


def house_prices(n: int = 700) -> pd.DataFrame:
    """Regression: house sale price driven by size, age, location tier."""
    sqft = rng.uniform(450, 3200, n)
    age = rng.integers(0, 60, n)
    bedrooms = np.clip((sqft / 700 + rng.normal(0, 0.7, n)).round(), 1, 6)
    tier = rng.choice(["suburb", "midtown", "prime"], n, p=[0.5, 0.35, 0.15])
    tier_bump = np.select([tier == "prime", tier == "midtown"], [1.45, 1.15], 1.0)
    price = (60_000 + 145 * sqft - 900 * age + 12_000 * bedrooms) * tier_bump \
        + rng.normal(0, 18_000, n)
    return pd.DataFrame({
        "listing_id": [f"H{i:05d}" for i in range(n)],
        "sqft": sqft.round(0),
        "age_years": age,
        "bedrooms": bedrooms.astype(int),
        "location_tier": tier,
        "sale_price": price.round(0),
    })


if __name__ == "__main__":
    churn().to_csv("customer_churn.csv", index=False)
    segments().to_csv("customer_segments.csv", index=False)
    sales().to_csv("weekly_sales.csv", index=False)
    house_prices().to_csv("house_prices.csv", index=False)
    print("Wrote customer_churn.csv, customer_segments.csv, weekly_sales.csv, house_prices.csv")
