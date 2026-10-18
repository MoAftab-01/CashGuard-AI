"""Exercise every core module together against the actual bundled sample."""

from datetime import timedelta

from config import SAMPLE_DATA_PATH
from src.anomaly_detection import detect_anomalies
from src.data_processing import validate_csv
from src.forecasting import forecast_cash_flow, rolling_backtest
from src.risk_engine import assess_risk
from src.scenario_simulator import ScenarioConfig, simulate_scenario


def test_complete_sample_analytics_pipeline():
    imported = validate_csv(SAMPLE_DATA_PATH)
    assert not imported.has_errors
    baseline = forecast_cash_flow(imported.data, "2500.00", cash_threshold=500)
    anomalies = detect_anomalies(imported.data, as_of=baseline.as_of)
    risk = assess_risk(imported.data, baseline, anomalies=anomalies)
    scenario = simulate_scenario(baseline, ScenarioConfig(income_decrease_pct=20,
                                expense_increase_pct=10, emergency_expense=500,
                                emergency_date=baseline.as_of + timedelta(days=1)))
    validation = rolling_backtest(imported.data, "2500.00")
    assert len(baseline.daily) == len(scenario.forecast.daily) == 30
    assert baseline.current_balance_cents == 1626823
    assert anomalies.scored_count > 0
    assert risk.score is not None
    assert scenario.closing_balance_change_cents < 0
    assert len(validation.folds) == 4 and len(validation.predictions) == 120
    assert all(value is not None and value >= 0 for value in validation.metrics.values())
    assert sum(event.amount_cents for event in scenario.forecast.events) == scenario.forecast.daily["net_cents"].sum()
