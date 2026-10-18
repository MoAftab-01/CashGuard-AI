from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from src.visualizations import anomaly_confusion_chart, anomaly_score_chart, forecast_evaluation_chart

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def test_evaluation_is_explicit_and_forecast_inputs_invalidate_results():
    app = AppTest.from_file(APP, default_timeout=30).run()
    app.sidebar.radio(key="navigation").set_value("Model Evaluation").run()
    assert not app.exception and not app.metric
    assert app.button(key="run_forecast_evaluation").disabled
    assert "forecast_evaluation" not in app.session_state["cashguard_private_cache"]
    app.sidebar.text_input(key="opening_balance").set_value("2500.00").run()
    app.button(key="run_forecast_evaluation").click().run()
    assert not app.exception
    metrics = app.dataframe[0].value
    assert len(metrics) == 12 and metrics["mae"].notna().all()
    app.sidebar.checkbox(key="irregular_income").set_value(True).run()
    assert not app.exception and not app.dataframe
    app.button(key="run_forecast_evaluation").click().run()
    assert not app.exception
    app.button(key="run_anomaly_evaluation").click().run()
    assert not app.exception
    assert len(app.metric) == 4
    assert any("False Positive Rate" == item.label for item in app.metric)


def test_sparse_evaluation_discloses_unavailable_scores():
    app = AppTest.from_file(APP, default_timeout=30).run()
    app.sidebar.radio(key="data_source").set_value("Upload CSV").run()
    app.file_uploader[0].set_value(("sparse.csv", b"date,description,amount,category\n2026-01-01,Pay,10,Income\n", "text/csv")).run()
    app.sidebar.text_input(key="opening_balance").set_value("0").run()
    app.sidebar.radio(key="navigation").set_value("Model Evaluation").run()
    app.button(key="run_forecast_evaluation").click().run()
    assert not app.exception and not app.metric
    assert app.dataframe[0].value["mae"].isna().all()
    assert any("No performance scores" in item.value for item in app.warning)


def test_evaluation_charts_use_measured_values_and_fixed_matrix_axes():
    metrics = pd.DataFrame([dict(target="balance", horizon_days=7, method="Measured", mae=12.34)])
    figure = forecast_evaluation_chart(metrics)
    assert figure.data[0].y[0] == 12.34
    confusion = anomaly_confusion_chart({"confusion_matrix": [[8, 2], [1, 3]]})
    assert list(confusion.data[0].z[0]) == [8, 2]
    scored = pd.DataFrame({"is_injected": [False, True], "anomaly_score": [.4, .7]})
    histogram = anomaly_score_chart(scored, .5)
    assert histogram.data[0].x[0] == .4 and histogram.data[1].x[0] == .7
    assert histogram.layout.shapes[0].x0 == .5
