from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
import pytest
from pydantic import ValidationError

from src.forecasting import forecast_cash_flow
from src.scenario_simulator import ScenarioConfig, simulate_scenario


def test_zero_scenario_is_identity_and_does_not_mutate_baseline(regular_history):
    baseline = forecast_cash_flow(regular_history, 1000)
    before = baseline.daily.copy(deep=True)
    result = simulate_scenario(baseline, ScenarioConfig())
    pd.testing.assert_frame_equal(result.forecast.daily, baseline.daily)
    assert result.forecast.events == baseline.events
    assert result.closing_balance_change_cents == 0
    result.forecast.daily.loc[0, "balance_cents"] = -1
    pd.testing.assert_frame_equal(baseline.daily, before)


@pytest.mark.parametrize("percentage", [10, 20, 30])
def test_income_decreases_reduce_closing_balance_exactly(regular_history, percentage):
    baseline = forecast_cash_flow(regular_history, 1000)
    result = simulate_scenario(baseline, ScenarioConfig(income_decrease_pct=percentage))
    assert result.closing_balance_change_cents == -300000 * percentage // 100
    assert result.forecast.current_balance_cents == baseline.current_balance_cents


def test_combined_expense_increase_and_emergency_reconcile(regular_history):
    baseline = forecast_cash_flow(regular_history, 0)
    config = ScenarioConfig(income_decrease_pct=20, expense_increase_pct=10,
                            emergency_expense="123.45", emergency_date=date(2026, 5, 10))
    result = simulate_scenario(baseline, config)
    assert result.closing_balance_change_cents == -60000 - 13000 - 12345
    assert result.forecast.daily["inflow_cents"].sum() == 240000
    assert result.forecast.daily["outflow_cents"].sum() == 143000 + 12345
    pd.testing.assert_frame_equal(result.forecast.daily, simulate_scenario(baseline, config).forecast.daily)


def test_delayed_payment_preserves_total_and_changes_intermediate_balances(regular_history):
    baseline = forecast_cash_flow(regular_history, 0)
    payment = next(event for event in baseline.events if event.amount_cents > 0)
    result = simulate_scenario(baseline, ScenarioConfig(delayed_event_id=payment.event_id, delay_days=5))
    assert result.closing_balance_change_cents == 0
    assert result.forecast.daily.iloc[0]["balance_cents"] == baseline.daily.iloc[0]["balance_cents"] - payment.amount_cents
    assert any(event.date == payment.date + timedelta(days=5) and event.event_id == payment.event_id for event in result.forecast.events)
    assert not result.deferred_events


def test_delayed_payment_outside_horizon_is_preserved_as_deferred(regular_history):
    baseline = forecast_cash_flow(regular_history, 0)
    payment = next(event for event in baseline.events if event.amount_cents > 0)
    result = simulate_scenario(baseline, ScenarioConfig(delayed_event_id=payment.event_id, delay_days=35))
    assert result.closing_balance_change_cents == -payment.amount_cents
    assert result.deferred_events[0].amount_cents == payment.amount_cents
    assert result.deferred_events[0].date == date(2026, 6, 5)
    assert payment.event_id not in {event.event_id for event in result.forecast.events}
    assert any("beyond" in warning for warning in result.forecast.warnings)


def test_emergency_recalculates_threshold_dates(transactions):
    history = transactions([(date(2026, 1, 1), "No activity", 0, "Other")])
    baseline = forecast_cash_flow(history, 100, cash_threshold=50)
    result = simulate_scenario(baseline, ScenarioConfig(emergency_expense=60, emergency_date=date(2026, 1, 5)))
    assert not baseline.shortage_dates
    assert result.forecast.shortage_dates[0] == date(2026, 1, 5)
    assert len(result.forecast.shortage_dates) == 27


def test_percentage_rounding_uses_half_up_cents(transactions):
    data = transactions([(date(2026, month, 1), "Pay", 101, "Income") for month in (1, 2, 3)])
    baseline = forecast_cash_flow(data, 0, horizon_days=31)
    result = simulate_scenario(baseline, ScenarioConfig(income_decrease_pct=50))
    assert result.forecast.daily["inflow_cents"].sum() == 51


@pytest.mark.parametrize("kwargs", [
    {"income_decrease_pct": -1}, {"income_decrease_pct": 101}, {"income_decrease_pct": "nan"},
    {"expense_increase_pct": "inf"}, {"expense_increase_pct": -1},
    {"emergency_expense": "0.001", "emergency_date": date(2026, 1, 1)},
    {"emergency_expense": -1}, {"emergency_expense": 1},
    {"delay_days": 3}, {"delayed_event_id": "x"}, {"delayed_event_id": "", "delay_days": 3},
    {"delay_days": True}, {"unknown_control": 10},
])
def test_invalid_scenarios_are_rejected(kwargs):
    with pytest.raises(ValidationError):
        ScenarioConfig(**kwargs)


def test_nonexistent_expense_and_outside_horizon_controls_fail(regular_history):
    baseline = forecast_cash_flow(regular_history, 0)
    expense = next(event for event in baseline.events if event.amount_cents < 0)
    for config in [ScenarioConfig(delayed_event_id="missing", delay_days=1),
                   ScenarioConfig(delayed_event_id=expense.event_id, delay_days=1),
                   ScenarioConfig(emergency_expense=10, emergency_date=baseline.as_of),
                   ScenarioConfig(emergency_expense=10, emergency_date=date(2027, 1, 1))]:
        with pytest.raises(ValueError):
            simulate_scenario(baseline, config)
