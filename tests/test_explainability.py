from datetime import date, timedelta

import pandas as pd
import pytest

from src.anomaly_detection import AnomalyDetector
from src.explainability import anomaly_comparisons, ranked_risk_factors, threshold_breaches
from src.forecasting import forecast_cash_flow
from src.risk_engine import assess_risk


def test_category_reference_and_comparisons_use_only_training(transactions):
    train = transactions([(date(2026, 1, 1) + timedelta(days=i), "Groceries", -1000, "Groceries") for i in range(40)])
    test = transactions([(date(2026, 2, 15), "Large purchase", -12000, "Groceries"),
                         (date(2026, 2, 16), "Later purchase", -11999, "Groceries")])
    scored = AnomalyDetector().fit(train).score(test)
    row = scored.iloc[0]
    assert row.reference_scope == "Category and direction" and row.reference_count == 40
    assert row.reference_cents == 1000 and row.amount_ratio == 12
    comparisons = anomaly_comparisons(pd.concat([train, test], ignore_index=True), row)
    assert len(comparisons) == 3 and comparisons["date"].max() <= row.training_end
    assert (comparisons["amount_cents"] == -1000).all()
    corrupted = row.copy()
    corrupted["training_end"] = row.date
    with pytest.raises(ValueError):
        anomaly_comparisons(train, corrupted)


def test_new_category_reports_broader_reference(transactions):
    train = transactions([(date(2026, 1, 1) + timedelta(days=i), "Food", -1000, "Groceries") for i in range(40)])
    test = transactions([(date(2026, 3, 1), "New category", -10000, "Medical")])
    row = AnomalyDetector().fit(train).score(test).iloc[0]
    assert row.reference_scope == "Direction" and row.reference_count == 40
    assert len(anomaly_comparisons(train, row)) == 3


def test_breach_explanations_reconcile_and_distinguish_crossing(transactions):
    data = transactions([(date(2026, 1, 1), "Spend", -1000, "Other")])
    forecast = forecast_cash_flow(data, 50, horizon_days=7, cash_threshold=20)
    frame = threshold_breaches(forecast)
    assert frame["date"].tolist() == list(forecast.shortage_dates)
    assert frame.iloc[0]["status"] == "Crosses below threshold"
    assert (frame.iloc[1:]["status"] == "Remains below threshold").all()
    for row in frame.itertuples():
        assert row.previous_balance_cents + row.inflow_cents - row.outflow_cents == row.balance_cents
        assert row.gap_to_threshold_cents == forecast.cash_threshold_cents - row.balance_cents > 0
    risk = assess_risk(data, forecast)
    factors = ranked_risk_factors(risk)
    assert factors[0].points == max(f.points for f in risk.factors if f.evaluated)
