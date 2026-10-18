from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def uploaded(raw):
    app = AppTest.from_file(APP, default_timeout=30).run()
    app.sidebar.radio(key="data_source").set_value("Upload CSV").run()
    app.file_uploader[0].set_value(("journey.csv", raw, "text/csv")).run()
    return app


def metric(app, name):
    return next(item.value for item in app.metric if item.label == name)


def test_demo_start_is_explicit_and_does_not_assume_uploaded_opening_cash():
    app = AppTest.from_file(APP, default_timeout=30).run()
    assert app.sidebar.text_input(key="opening_balance").value == "" and not app.metric
    app.sidebar.button(key="start_demo").click().run()
    assert not app.exception and metric(app, "Estimated cash balance") == "USD 16,268.23"
    assert app.sidebar.text_input(key="opening_balance").value == "2500.00"
    app.sidebar.radio(key="data_source").set_value("Upload CSV").run()
    assert not app.metric and not any(item.key == "start_demo" for item in app.button)
    app.sidebar.button(key="clear_session").click().run()
    assert not app.exception and app.sidebar.text_input(key="opening_balance").value == ""


def test_transaction_filters_survive_navigation_and_reset_for_replacement_data():
    app = uploaded(b"date,description,amount,category\n2026-01-01,Salary,100,Income\n2026-01-02,Groceries,-10,Groceries\n")
    app.sidebar.text_input(key="opening_balance").set_value("10.00").run()
    app.sidebar.radio(key="navigation").set_value("Transactions").run()
    app.text_input(key="transaction_search").set_value("Groceries").run()
    app.selectbox(key="transaction_direction").set_value("Expenses").run()
    assert app.dataframe[0].value.description.tolist() == ["Groceries"]
    app.sidebar.radio(key="navigation").set_value("Overview").run()
    assert metric(app, "Estimated cash balance") == "USD 100.00"
    app.sidebar.radio(key="navigation").set_value("Transactions").run()
    assert app.text_input(key="transaction_search").value == "Groceries"
    assert app.selectbox(key="transaction_direction").value == "Expenses"
    assert app.dataframe[0].value.description.tolist() == ["Groceries"]
    app.file_uploader[0].set_value(("replacement.csv", b"date,description,amount,category\n2026-02-01,New payment,25,Income\n", "text/csv")).run()
    assert not app.exception
    assert app.text_input(key="transaction_search").value == ""
    assert app.selectbox(key="transaction_direction").value == "All"
    assert app.dataframe[0].value.description.tolist() == ["New payment"]


def test_anomaly_review_filters_survive_navigation_without_changing_metrics():
    app = AppTest.from_file(APP, default_timeout=30).run()
    app.sidebar.button(key="start_demo").click().run()
    opening = metric(app, "Estimated cash balance")
    app.sidebar.radio(key="navigation").set_value("Anomaly Detection").run()
    app.selectbox(key="anomaly_status").set_value("All scored").run()
    app.text_input(key="anomaly_search").set_value("salary").run()
    before = app.dataframe[0].value.description.tolist()
    assert before
    app.sidebar.radio(key="navigation").set_value("Overview").run()
    assert metric(app, "Estimated cash balance") == opening
    app.sidebar.radio(key="navigation").set_value("Anomaly Detection").run()
    assert app.selectbox(key="anomaly_status").value == "All scored"
    assert app.text_input(key="anomaly_search").value == "salary"
    assert app.dataframe[0].value.description.tolist() == before
    assert not app.exception


def test_emergency_income_stress_and_threshold_keep_historical_metrics_consistent():
    app = AppTest.from_file(APP, default_timeout=30).run()
    app.sidebar.button(key="start_demo").click().run()
    actual = metric(app, "Estimated cash balance")
    app.sidebar.radio(key="navigation").set_value("Scenario Simulator").run()
    app.text_input(key="scenario_emergency").set_value("500.00").run()
    assert metric(app, "Closing balance change") == "USD -500.00"
    app.slider(key="scenario_income").set_value(20).run()
    stressed = metric(app, "Closing balance change")
    assert stressed not in {"USD 0.00", "USD -500.00"}
    app.sidebar.radio(key="navigation").set_value("Cash Flow Forecast").run()
    assert metric(app, "Estimated balance at cutoff") == actual
    app.sidebar.text_input(key="cash_threshold").set_value("999999.00").run()
    assert metric(app, "Days below threshold") == "30"
    app.sidebar.radio(key="navigation").set_value("Scenario Simulator").run()
    assert app.text_input(key="scenario_emergency").value == "500.00"
    assert app.slider(key="scenario_income").value == 20
    assert metric(app, "Closing balance change") == stressed
    app.sidebar.radio(key="navigation").set_value("Overview").run()
    assert metric(app, "Estimated cash balance") == actual
    assert not app.exception


def test_invalid_csv_replacement_blocks_totals_then_recovers_after_correction():
    raw = b"date,description,amount,category\n2026-01-01,Receipt,100,Income\n"
    app = uploaded(raw)
    app.sidebar.text_input(key="opening_balance").set_value("10.00").run()
    assert metric(app, "Estimated cash balance") == "USD 110.00"
    app.file_uploader[0].set_value(("bad.csv", raw + b"2026-01-02,Bad amount,not-money,Other\n", "text/csv")).run()
    assert not app.exception and not app.metric
    assert any("blocked" in item.value.lower() for item in app.error)
    issues = app.dataframe[0].value
    assert "amount" in issues.field.tolist()
    app.file_uploader[0].set_value(("corrected.csv", raw + b"2026-01-02,Expense,-25,Other\n", "text/csv")).run()
    assert not app.exception and metric(app, "Estimated cash balance") == "USD 85.00"
