from datetime import date
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def uploaded_app(content: bytes) -> AppTest:
    app = AppTest.from_file(APP, default_timeout=30).run()
    app.sidebar.radio(key="data_source").set_value("Upload CSV").run()
    app.file_uploader[0].set_value(("transactions.csv", content, "text/csv")).run()
    return app


def test_all_analytics_pages_render_and_scenario_changes_recalculate():
    app = AppTest.from_file(APP, default_timeout=30).run()
    app.sidebar.text_input(key="opening_balance").set_value("2500.00").run()
    assert not app.exception
    for page in ["Cash Flow Forecast", "Anomaly Detection", "Risk Analysis", "Scenario Simulator", "AI Insights"]:
        app.sidebar.radio(key="navigation").set_value(page).run()
        assert not app.exception, page
    assert app.button(key="generate_ai_insights").label == "Generate AI Insights"
    app.sidebar.radio(key="navigation").set_value("Scenario Simulator").run()
    before = next(item.value for item in app.metric if item.label == "Closing balance change")
    app.slider(key="scenario_income").set_value(20).run()
    after = next(item.value for item in app.metric if item.label == "Closing balance change")
    assert before == "USD 0.00" and after != before
    assert not app.exception
    app.sidebar.radio(key="navigation").set_value("AI Insights").run()
    assert any("Scenario outcome" in item.value for item in app.subheader)
    app.sidebar.radio(key="navigation").set_value("Scenario Simulator").run()
    assert app.slider(key="scenario_income").value == 20


def test_upload_switch_replaces_prior_results_and_clear_removes_session_cache():
    header = b"date,description,amount,category\n"
    app = uploaded_app(header + b"2026-01-01,Income A,100,Income\n")
    app.sidebar.text_input(key="opening_balance").set_value("10.00").run()
    assert not app.exception and app.metric[0].value == "USD 110.00"
    app.file_uploader[0].set_value(("second.csv", header + b"2026-01-01,Expense B,-20,Other\n", "text/csv")).run()
    assert not app.exception and app.metric[0].value == "USD -10.00"
    app.file_uploader[0].set_value(None).run()
    assert not app.metric
    assert "cashguard_private_cache" not in app.session_state
    app.sidebar.button(key="clear_session").click().run()
    assert not app.exception
    assert app.sidebar.text_input(key="opening_balance").value == ""


def test_uploaded_ambiguous_duplicates_block_totals_until_removal():
    app = uploaded_app(b"date,description,amount,category\n" + b"2026-01-01,Pay,100,Income\n" * 2)
    app.sidebar.text_input(key="opening_balance").set_value("10.00").run()
    assert not app.exception and not app.metric
    assert any("duplicate" in item.value.lower() for item in app.warning)
    app.sidebar.checkbox(key="remove_duplicates").set_value(True).run()
    assert not app.exception and app.metric[0].value == "USD 110.00"


def test_transaction_search_and_empty_filters_are_actionable():
    app = uploaded_app(b"date,description,amount,category\n2026-01-01,Groceries,-10,Groceries\n2026-01-02,Salary,100,Income\n")
    app.sidebar.radio(key="navigation").set_value("Transactions").run()
    app.text_input(key="transaction_search").set_value("grocer").run()
    assert not app.exception
    assert app.dataframe[0].value["description"].tolist() == ["Groceries"]
    app.text_input(key="transaction_search").set_value("not present").run()
    assert not app.exception
    assert any("No transactions match" in item.value for item in app.info)


def test_sparse_anomaly_page_does_not_require_an_opening_balance():
    app = uploaded_app(b"date,description,amount,category\n2026-01-01,Food,-10,Groceries\n")
    app.sidebar.radio(key="navigation").set_value("Anomaly Detection").run()
    assert not app.exception
    assert next(item.value for item in app.metric if item.label == "Transactions scored") == "0"
    assert any("remain unscored" in item.value for item in app.warning)


def test_malformed_upload_never_displays_previous_totals():
    app = uploaded_app(b"date,description,amount,category\n2026-01-01,Food,-10,Groceries\n")
    app.sidebar.text_input(key="opening_balance").set_value("100").run()
    assert app.metric
    app.file_uploader[0].set_value(("invalid.csv", b"date,amount\n2026-01-01,bad\n", "text/csv")).run()
    assert not app.exception and not app.metric
    assert any("blocked" in item.value for item in app.error)


def test_forecast_threshold_and_analysis_date_update_the_dashboard():
    app = AppTest.from_file(APP, default_timeout=30).run()
    app.sidebar.text_input(key="opening_balance").set_value("2500.00").run()
    app.sidebar.radio(key="navigation").set_value("Cash Flow Forecast").run()
    assert next(item.value for item in app.metric if item.label == "Days below threshold") == "0"
    app.sidebar.text_input(key="cash_threshold").set_value("999999.00").run()
    assert not app.exception
    assert next(item.value for item in app.metric if item.label == "Days below threshold") == "30"
    old_balance = next(item.value for item in app.metric if item.label == "Estimated balance at cutoff")
    app.sidebar.date_input[0].set_value(date(2026, 3, 31)).run()
    assert not app.exception
    assert next(item.value for item in app.metric if item.label == "Estimated balance at cutoff") != old_balance


def test_payment_delay_beyond_horizon_is_exposed_in_the_interface():
    app = AppTest.from_file(APP, default_timeout=30).run()
    app.sidebar.text_input(key="opening_balance").set_value("2500.00").run()
    app.sidebar.radio(key="navigation").set_value("Scenario Simulator").run()
    payment = next(item for item in app.selectbox if item.label == "Expected payment to delay")
    payment.select_index(1).run()
    app.number_input(key="scenario_delay").set_value(60).run()
    assert not app.exception
    assert any("moves beyond" in item.value for item in app.warning)
    assert next(item.value for item in app.metric if item.label == "Closing balance change") != "USD 0.00"


def test_invalid_scenario_cannot_leave_a_stale_summary():
    app = uploaded_app(b"date,description,amount,category\n2026-01-01,Income,100,Income\n")
    app.sidebar.text_input(key="opening_balance").set_value("100").run()
    app.sidebar.radio(key="navigation").set_value("Scenario Simulator").run()
    app.text_input(key="scenario_emergency").set_value("nan").run()
    assert not app.exception
    assert any("Check the scenario inputs" in item.value for item in app.error)
    app.sidebar.radio(key="navigation").set_value("AI Insights").run()
    assert not any("Scenario outcome" in item.value for item in app.subheader)
