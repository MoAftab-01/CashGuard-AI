"""Exercise actual Streamlit execution and important user controls."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

from src.data_processing import validate_csv

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def test_demo_requires_explicit_opening_then_renders_metrics():
    app = AppTest.from_file(str(APP_PATH), default_timeout=30).run()
    assert not app.exception
    assert not app.metric
    assert any("opening balance" in item.value.lower() for item in app.warning)
    app.sidebar.text_input[0].set_value("2500.00").run()
    assert not app.exception
    assert len(app.metric) == 4
    assert app.metric[0].label == "Estimated cash balance"
    app.sidebar.text_input[0].set_value("nan").run()
    assert not app.exception and app.error and not app.metric


def test_transaction_filters_and_quality_page():
    app = AppTest.from_file(str(APP_PATH), default_timeout=30).run()
    app.sidebar.radio[0].set_value("Transactions").run()
    app.multiselect[0].set_value(["Groceries"]).run()
    assert not app.exception
    assert set(app.dataframe[0].value["category"]) == {"Groceries"}
    app.sidebar.radio[0].set_value("Data quality").run()
    assert not app.exception and app.success


def test_upload_mode_without_file_is_actionable():
    app = AppTest.from_file(str(APP_PATH), default_timeout=30).run()
    app.sidebar.radio[1].set_value("Upload CSV").run()
    assert not app.exception
    assert any("Upload a UTF-8 CSV" in item.value for item in app.info)


def test_invalid_import_cannot_display_partial_financial_totals(monkeypatch):
    result = validate_csv("date,description,amount,category\n2026-01-01,Pay,100,Income\n2026-01-02,Bad,wrong,Other\n")
    monkeypatch.setattr("src.data_processing.validate_csv", lambda *args, **kwargs: result)
    app = AppTest.from_file(str(APP_PATH), default_timeout=30).run()
    app.sidebar.text_input[0].set_value("1000").run()
    assert not app.exception
    assert app.error and not app.metric
    assert any("blocked" in item.value.lower() for item in app.error)


def test_cash_decrease_delta_keeps_negative_sign_for_streamlit_risk_color():
    app = AppTest.from_file(str(APP_PATH), default_timeout=30).run()
    app.sidebar.text_input[0].set_value("2500.00").run()
    app.sidebar.radio[0].set_value("Scenario Simulator").run()
    next(item for item in app.text_input if item.label == "Emergency expense").set_value("500.00").run()
    assert not app.exception
    minimum = next(item for item in app.metric if item.label == "Scenario minimum cash")
    # Streamlit uses a leading minus to select the downward/red indicator.
    assert minimum.delta == "-500.00 USD"
    assert next(item for item in app.metric if item.label == "Closing balance change").value == "USD -500.00"
