from datetime import date, timedelta
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from src.anomaly_detection import AnomalyDetector, AnomalyResult, detect_anomalies
from src.data_processing import empty_transactions, validate_csv
from src.forecasting import ForecastEvent, forecast_cash_flow, project_events
from src.metrics import balance_history, calculate_metrics, monthly_summary, category_expenses
from src.risk_engine import assess_risk
from src.scenario_simulator import ScenarioConfig, simulate_scenario


@pytest.mark.parametrize("amounts", [[], [0], [1], [-1], [100, 333, 98765432100],
                                    [-1, -333, -98765432100], [10, -20, 30, -999999999999]])
def test_signed_totals_and_history_forecast_scenario_reconcile(transactions, amounts):
    rows = [(date(2026, 1, 1) + timedelta(days=i * 4), f"Irregular {i}", cents, "Other")
            for i, cents in enumerate(amounts)]
    data = transactions(rows) if rows else empty_transactions()
    m = calculate_metrics(data, "123.45")
    assert m.estimated_balance == m.opening_balance + m.total_income - m.total_expenses
    assert m.net_cash_flow == Decimal(sum(amounts)) / 100
    assert m.total_expenses >= 0 and m.total_income >= 0
    if rows:
        assert balance_history(data, "123.45").iloc[-1]["estimated_balance"] == pytest.approx(float(m.estimated_balance))
        assert monthly_summary(data)["net"].sum() == pytest.approx(float(m.net_cash_flow))
        assert category_expenses(data)["expenses"].sum() == pytest.approx(float(m.total_expenses))
    f = forecast_cash_flow(data, "123.45", as_of=data["date"].max() if rows else date(2026, 1, 1))
    assert f.current_balance_cents == int(m.estimated_balance * 100)
    config = ScenarioConfig(income_decrease_pct=20, expense_increase_pct=33,
                            emergency_expense="4.31", emergency_date=f.daily.iloc[2]["date"])
    scenario = simulate_scenario(f, config)
    for forecast in (f, scenario.forecast):
        previous = forecast.current_balance_cents
        for row in forecast.daily.itertuples():
            events = [event.amount_cents for event in forecast.events if event.date == row.date]
            assert row.net_cents == row.inflow_cents - row.outflow_cents == sum(events)
            assert row.balance_cents == previous + sum(events)
            assert row.below_threshold == (row.balance_cents < forecast.cash_threshold_cents)
            previous = row.balance_cents
        assert previous == forecast.current_balance_cents + sum(event.amount_cents for event in forecast.events)
    assert sum(event.amount_cents for event in scenario.forecast.events if event.kind == "emergency") == -431


def test_id_duplicate_is_counted_once_across_all_ledger_views():
    row = "2026-01-01,Pay,100.25,Income,0001\n"
    imported = validate_csv("date,description,amount,category,transaction_id\n" + row * 2)
    assert not imported.has_errors and imported.duplicates_removed == 1
    assert calculate_metrics(imported.data, 0).estimated_balance == Decimal("100.25")
    assert forecast_cash_flow(imported.data, 0).current_balance_cents == 10025


@pytest.mark.parametrize("amount", [.5, 1.0, True, Decimal("1.5"), float("nan")])
def test_public_projection_ledger_rejects_fractional_or_boolean_cents(amount):
    event = ForecastEvent("event", date(2026, 1, 2), amount, "baseline", "Invalid cents")
    with pytest.raises(ValueError, match="integer cents"):
        project_events(date(2026, 1, 1), 1, 0, 0, (event,))
    with pytest.raises(ValueError, match="integer cents"):
        project_events(date(2026, 1, 1), 1, amount, 0, ())


def test_batched_walk_forward_matches_original_daily_scoring(regular_history):
    optimized = detect_anomalies(regular_history)
    detector = AnomalyDetector()
    last_fit = None
    for day, group in regular_history.groupby("date"):
        prior = regular_history.loc[regular_history["date"] < day]
        span = (prior["date"].max() - prior["date"].min()).days + 1 if len(prior) else 0
        if len(prior) < 30 or span < 30:
            continue
        if last_fit is None or (day - last_fit).days >= 30:
            detector.fit(prior)
            last_fit = day
        expected = detector.score(group)
        actual = optimized.data.loc[optimized.data["date"] == day]
        np.testing.assert_array_equal(expected["anomaly_score"], actual["anomaly_score"])
        np.testing.assert_array_equal(expected["is_anomaly"], actual["is_anomaly"])
        np.testing.assert_array_equal(expected["is_anomaly"], detector.pipeline_.predict(group) == -1)
        assert expected["training_end"].tolist() == actual["training_end"].tolist()


@pytest.mark.parametrize("expenses,expected", [([100, 300], 0), ([100, 301], 7), ([0, 200], 7), ([0, 0, 300], 15)])
def test_expense_volatility_exact_boundaries(transactions, expenses, expected):
    data = transactions([(date(2026, 1, 1) + timedelta(days=i), "Expense", -cents, "Other")
                         for i, cents in enumerate(expenses)])
    result = assess_risk(data, forecast_cash_flow(data, 10000))
    assert next(f.points for f in result.factors if f.name == "spending_volatility") == expected


@pytest.mark.parametrize("flagged,expected", [(0, 0), (1, 5), (2, 10)])
def test_anomaly_risk_rate_boundaries(regular_history, flagged, expected):
    forecast = forecast_cash_flow(regular_history, 10000)
    scored = regular_history.tail(10).copy()
    scored["is_anomaly"] = pd.array([True] * flagged + [False] * (10 - flagged), dtype="boolean")
    scored["training_end"] = scored["date"].map(lambda day: day - timedelta(days=1))
    risk = assess_risk(regular_history, forecast, anomalies=AnomalyResult(scored, forecast.as_of, ()))
    assert next(f.points for f in risk.factors if f.name == "unusual_activity") == expected


def test_more_opening_cash_cannot_increase_cash_shortfall_or_buffer_points(regular_history):
    scores = []
    for opening in (-10000, 0, 10000):
        risk = assess_risk(regular_history, forecast_cash_flow(regular_history, opening))
        scores.append(sum(f.points for f in risk.factors if f.name in {"low_cash_buffer", "projected_shortfall"}))
    assert scores == sorted(scores, reverse=True) and scores[0] > scores[-1]


@pytest.mark.parametrize("cash_cents,emergency,flagged,score,level", [
    (100000, "0", 0, 0, "Low"),
    (100000, "2000", 0, 30, "Moderate"),
    (6000, "0", 0, 55, "Moderate"),
    (6000, "0", 1, 60, "High"),
])
def test_risk_level_boundaries_use_reconciled_cashflows(transactions, cash_cents, emergency, flagged, score, level):
    data = transactions([(date(2026, 1, 1) + timedelta(days=i), description, amount, category)
                         for i in range(40) for description, amount, category in
                         [("Daily cost", -1000, "Other"), ("Daily receipts", 2000, "Income")]])
    opening = Decimal(cash_cents - sum(data["amount_cents"])) / 100
    forecast = forecast_cash_flow(data, opening)
    stressed = simulate_scenario(forecast, ScenarioConfig(emergency_expense=emergency, emergency_date=forecast.daily.iloc[0]["date"]))
    assessed = data.tail(10).copy()
    assessed["training_end"] = assessed["date"].map(lambda day: day - timedelta(days=1))
    assessed["is_anomaly"] = pd.array([True] * flagged + [False] * (10 - flagged), dtype="boolean")
    risk = assess_risk(data, stressed.forecast, anomalies=AnomalyResult(assessed, forecast.as_of, ()))
    assert risk.score == score and risk.level == level
