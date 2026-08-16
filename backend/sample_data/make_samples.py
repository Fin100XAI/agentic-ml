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
    # Deliberately leaky column for the leakage sentinel: it IS the outcome,
    # written after the fact - exactly what a real export often contains.
    account_status = np.where(churn_flag == 1, "closed", "active")
    return pd.DataFrame({
        "customer_id": [f"C{i:05d}" for i in range(n)],
        "tenure_months": tenure,
        "monthly_charge": monthly,
        "support_calls": support_calls,
        "contract_type": contract,
        "account_status": account_status,
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


def loan_applicants(n: int = 300) -> pd.DataFrame:
    """PII screening demo: fake Indian personal data + a real signal column."""
    first = ["Aarav", "Vivaan", "Diya", "Ananya", "Rohan", "Priya", "Kabir", "Isha", "Arjun", "Meera"]
    last = ["Sharma", "Patel", "Reddy", "Gupta", "Iyer", "Khan", "Das", "Nair", "Singh", "Joshi"]
    names = [f"{rng.choice(first)} {rng.choice(last)}" for _ in range(n)]
    emails = [f"{nm.split()[0].lower()}.{nm.split()[1].lower()}{i}@example.com" for i, nm in enumerate(names)]
    phones = [f"+91 {rng.integers(6, 10)}{rng.integers(100000000, 999999999)}" for _ in range(n)]
    aadhaar = [f"{rng.integers(1000, 9999)} {rng.integers(1000, 9999)} {rng.integers(1000, 9999)}" for _ in range(n)]
    pan = ["".join(rng.choice(list("ABCDEFGHIJKLMNOPQRSTUVWXYZ"), 5)) + str(rng.integers(1000, 9999)) + rng.choice(list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")) for _ in range(n)]
    income = rng.uniform(2.5, 30, n).round(1)  # lakh per year
    amount = (income * rng.uniform(2, 6, n)).round(1)
    approved = (rng.random(n) < 1 / (1 + np.exp(-(0.25 * income - 0.08 * amount)))).astype(int)
    return pd.DataFrame({
        "applicant_name": names,
        "email": emails,
        "phone": phones,
        "aadhaar_no": aadhaar,
        "pan_code": pan,
        "annual_income_lakh": income,
        "loan_amount_lakh": amount,
        "approved": approved,
    })


def churn_drifted(n: int = 400) -> pd.DataFrame:
    """Drift-monitor demo: same schema as customer_churn.csv, shifted world.

    Tenure is much lower (a wave of new customers) and monthly charges are
    higher (price rise) - and the churn mechanics changed, so a model trained
    on the original file also loses accuracy (performance decay).
    """
    tenure = rng.integers(1, 24, n)                       # was 1-72
    monthly = rng.uniform(60, 180, n).round(2)            # was 20-120
    support_calls = rng.poisson(2, n)
    contract = rng.choice(["month-to-month", "one-year", "two-year"], n, p=[0.7, 0.2, 0.1])
    logit = -1.5 + 0.02 * monthly - 0.9 * (contract != "month-to-month") \
        - 0.15 * support_calls                            # different mechanics
    churn_flag = (rng.random(n) < 1 / (1 + np.exp(-logit))).astype(int)
    account_status = np.where(churn_flag == 1, "closed", "active")
    return pd.DataFrame({
        "customer_id": [f"D{i:05d}" for i in range(n)],
        "tenure_months": tenure,
        "monthly_charge": monthly,
        "support_calls": support_calls,
        "contract_type": contract,
        "account_status": account_status,
        "churned": churn_flag,
    })


if __name__ == "__main__":
    churn().to_csv("customer_churn.csv", index=False)
    churn_drifted().to_csv("customer_churn_drifted.csv", index=False)
    segments().to_csv("customer_segments.csv", index=False)
    sales().to_csv("weekly_sales.csv", index=False)
    house_prices().to_csv("house_prices.csv", index=False)
    loan_applicants().to_csv("loan_applicants_pii.csv", index=False)
    print("Wrote customer_churn.csv, customer_churn_drifted.csv, customer_segments.csv, "
          "weekly_sales.csv, house_prices.csv, loan_applicants_pii.csv")
