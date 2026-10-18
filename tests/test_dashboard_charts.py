import numpy as np

from src.scenario_simulator import ScenarioConfig, simulate_scenario
from src.visualizations import forecast_comparison, risk_contributions


def test_forecast_chart_uses_engine_values_and_a_shared_cutoff_anchor(demo_dashboard):
    _, bundle = demo_dashboard
    scenario = simulate_scenario(bundle.forecast, ScenarioConfig(income_decrease_pct=20))
    figure = forecast_comparison(bundle.balance_history, bundle.forecast, scenario=scenario.forecast)
    assert [trace.name for trace in figure.data] == ["Historical estimate", "Baseline projection", "Scenario projection"]
    for trace, forecast in zip(figure.data[1:], (bundle.forecast, scenario.forecast)):
        assert trace.x[0] == forecast.as_of
        assert trace.y[0] == forecast.current_balance_cents / 100
        np.testing.assert_array_equal(trace.y[1:], forecast.daily["balance_cents"].to_numpy() / 100)
    assert figure.layout.shapes[0].y0 == bundle.forecast.cash_threshold_cents / 100
    assert figure.layout.font.color is None
    assert figure.layout.paper_bgcolor == "rgba(0,0,0,0)"


def test_risk_chart_displays_actual_points(demo_dashboard):
    risk = demo_dashboard[1].risk
    figure = risk_contributions(risk)
    assert list(figure.data[0].x) == [factor.points for factor in risk.factors]
