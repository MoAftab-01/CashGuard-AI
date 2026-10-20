from pathlib import Path

import pytest
from pandas.testing import assert_frame_equal
from streamlit.testing.v1 import AppTest

from config import SAMPLE_DATA_PATH
from src.dashboard_service import build_dashboard, format_cents
from src.data_processing import validate_csv
from src.ui.ai_insights import concise
from src.ui.navigation import AREAS, VIEWS, resolve_view
from src.ui.scenario_controls import preset_values

APP = Path(__file__).resolve().parents[1] / "app.py"


def demo():
    app = AppTest.from_file(APP, default_timeout=30).run()
    app.button(key="start_demo").click().run()
    assert not app.exception
    return app


def test_task_navigation_and_home_match_existing_engine_without_duplicate_charts():
    app = demo()
    assert [app.button(key=f"area_{i}").label for i in range(4)] == list(AREAS)
    expected = build_dashboard(validate_csv(SAMPLE_DATA_PATH), "2500.00")
    metrics = {m.label:m.value for m in app.metric}
    assert metrics["Estimated cash balance"] == f"USD {expected.metrics.estimated_balance:,.2f}"
    assert metrics["Estimated 30-day balance"] == format_cents(int(expected.forecast.daily.iloc[-1].balance_cents))
    assert len(app.get("plotly_chart")) == 1
    app.button(key="area_1").click().run()
    assert app.radio(key="navigation").value == "Transactions"
    app.button(key="area_2").click().run()
    assert app.radio(key="navigation").value == "Scenario Simulator"
    app.button(key="area_3").click().run()
    assert app.radio(key="navigation").value == "AI Insights"
    assert not app.exception


@pytest.mark.parametrize("route", list(VIEWS))
def test_deep_links_and_legacy_ids_preserve_all_nine_capabilities(route):
    app = AppTest.from_file(APP, default_timeout=30)
    app.query_params["view"] = VIEWS[route][2]
    app.run()
    assert not app.exception
    assert app.radio(key="navigation").value == route
    assert any(title.value == VIEWS[route][1] for title in app.title)
    assert resolve_view(route) == route


def test_unknown_view_and_financial_query_parameters_cannot_supply_opening_cash():
    app = AppTest.from_file(APP, default_timeout=30)
    app.query_params.update(view="https://untrusted.invalid", opening_balance="999999")
    app.run()
    assert not app.exception and not app.metric
    assert app.text_input(key="opening_balance").value == ""
    assert app.radio(key="navigation").value == "Overview"


@pytest.mark.parametrize("index", range(4))
def test_hypothetical_presets_delegate_to_existing_scenario_and_reset(index):
    app = demo()
    app.button(key="area_2").click().run()
    history = app.session_state["cashguard_private_cache"]["dashboard"][1].balance_history.copy(deep=True)
    app.button(key=f"scenario_preset_{index}").click().run()
    assert not app.exception and not app.error
    result = app.session_state["cashguard_latest_scenario"][1]
    assert not result.forecast.daily.balance_cents.equals(result.baseline.daily.balance_cents)
    if index == 0:
        assert result.closing_balance_change_cents == -50000
    elif index == 1:
        assert result.config.delay_days == 7
    assert_frame_equal(app.session_state["cashguard_private_cache"]["dashboard"][1].balance_history, history)
    app.button(key="scenario_reset").click().run()
    assert not app.exception and not app.error
    result = app.session_state["cashguard_latest_scenario"][1]
    assert_frame_equal(result.forecast.daily, result.baseline.daily)


def test_no_recurring_income_disables_delay_preset_and_invalid_plan_can_be_reset():
    app = AppTest.from_file(APP, default_timeout=30).run()
    app.radio(key="data_source").set_value("Upload CSV").run()
    app.file_uploader[0].set_value(("fictional.csv", b"date,description,amount,category\n2026-01-01,One receipt,100,Income\n", "text/csv")).run()
    app.text_input(key="opening_balance").set_value("0.00").run()
    app.button(key="area_2").click().run()
    assert app.button(key="scenario_preset_1").disabled
    baseline = app.session_state["cashguard_latest_scenario"][1].baseline
    with pytest.raises(ValueError, match="No supported"):
        preset_values("Delayed income", baseline)
    app.text_input(key="scenario_emergency").set_value("nan").run()
    assert app.error and not app.metric
    app.button(key="scenario_reset").click().run()
    assert not app.exception and not app.error and app.metric


def test_concise_excerpt_does_not_change_full_model_text_or_invent_an_answer():
    text = "This is a qualitative sentence. " * 30
    excerpt = concise(text)
    assert len(excerpt) <= 361 and excerpt.endswith("…")
    assert text.startswith(excerpt[:-1])
    assert concise("Insufficient evidence.") == "Insufficient evidence."


def test_only_named_reviewed_redesign_screenshots_are_release_candidates(tmp_path):
    from scripts.prepare_release import UI_ASSETS, candidates
    for name in [*UI_ASSETS, "docs/phase10a/assets/private-finances.png", "var/screenshot.png"]:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"test fixture")
    assert {path.relative_to(tmp_path).as_posix() for path in candidates(tmp_path)} == UI_ASSETS
