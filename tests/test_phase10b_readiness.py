"""Release contracts and accessible values; financial engines remain authoritative."""

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import yaml
from streamlit.testing.v1 import AppTest

from config import SAMPLE_DATA_PATH
from src.dashboard_service import build_dashboard
from src.data_processing import validate_csv
from src.ui.chart_data import chart_alternative, table_values
from src.visualizations import anomaly_confusion_chart, forecast_comparison, anomaly_score_chart

ROOT = Path(__file__).resolve().parents[1]


def test_accessible_forecast_uses_exact_plotted_engine_values_and_threshold():
    bundle = build_dashboard(validate_csv(SAMPLE_DATA_PATH), "2500.00", cash_threshold="20000.00")
    figure = forecast_comparison(bundle.balance_history, bundle.forecast)
    description, rows = chart_alternative(figure)
    baseline = rows.loc[rows.Series == "Baseline projection"]
    assert baseline.iloc[1:]["USD"].tolist() == [int(v) / 100 for v in bundle.forecast.daily.balance_cents]
    assert baseline.iloc[0]["USD"] == bundle.forecast.current_balance_cents / 100
    assert len(rows) == sum(len(trace.x) for trace in figure.data)
    assert "Horizontal reference (USD): 20000.0" in description


def test_accessible_confusion_matrix_retains_labels_and_all_four_counts():
    _, rows = chart_alternative(anomaly_confusion_chart({"confusion_matrix": [[234, 0], [1, 12]]}))
    assert rows.Count.tolist() == [234, 0, 1, 12]
    assert rows.Prediction.tolist() == ["Not flagged", "Flagged unusual"] * 2
    assert rows["Known injection label"].tolist() == ["Background"] * 2 + ["Injected expense"] * 2


def test_histogram_alternative_is_raw_observations_not_fabricated_bin_counts():
    frame = pd.DataFrame({"is_injected": [False, True, True], "anomaly_score": [.1, .5, .9]})
    description, rows = chart_alternative(anomaly_score_chart(frame, .7))
    assert rows["Unusualness score (not probability)"].tolist() == [.1, .5, .9]
    assert "Count" not in rows and "individual observations" in description
    assert "Vertical reference (Unusualness score (not probability)): 0.7" in description


def test_empty_chart_has_no_invented_rows():
    description, rows = chart_alternative(go.Figure())
    assert rows.empty and "Series: none" in description


def test_free_only_template_has_no_disk_database_paid_plan_or_automatic_deploy():
    configuration = yaml.safe_load((ROOT / "render.yaml").read_text())
    assert set(configuration) == {"services"}
    service, = configuration["services"]
    assert service["plan"] == "free" and service["autoDeployTrigger"] == "off"
    assert not service.get("disk") and not service.get("preDeployCommand")
    settings = {entry["key"]: entry for entry in service["envVars"]}
    for key in ("CASHGUARD_API_TOKEN", "CASHGUARD_OPS_TOKEN"):
        assert settings[key] == {"key": key, "generateValue": True}
    for key, value in (("CASHGUARD_PUBLIC_DEMO", "true"), ("CASHGUARD_EXECUTION_MODE", "api"),
                       ("CASHGUARD_INFERENCE_PROVIDER", "deterministic"), ("CASHGUARD_PUBLIC_HTTPS", "true")):
        assert settings[key]["value"] == value


def test_accessible_chart_alternative_is_rendered_and_sections_follow_page_heading():
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    app.button(key="start_demo").click().run()
    assert not app.exception
    assert any("Your cash outlook" == item.value for item in app.header)
    assert any("Chart data:" in item.label for item in app.expander)
    charts = app.get("plotly_chart")
    assert len(charts) == 1 and "Expand Chart data" in charts[0].proto.alt
    assert any(table.proto.alt == "All plotted source values, without recalculation." for table in app.get("table"))


def test_invalid_scenario_names_the_control_without_displaying_partial_results():
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    app.button(key="start_demo").click().run()
    app.button(key="area_2").click().run()
    app.text_input(key="scenario_emergency").set_value("nan").run()
    assert not app.exception and not app.metric
    assert any("Emergency expense: Input should be a finite number" in error.value for error in app.error)
    app.button(key="scenario_reset").click().run()
    assert not app.error and app.metric


def test_readable_tables_keep_money_and_source_unchanged_and_neutralize_markdown():
    description = "![Fictional image](http://127.0.0.1:9/qa.png) [Fictional link](http://127.0.0.1:9/qa) `literal`"
    frame = pd.DataFrame({"description": [description], "amount_cents": [-2500], "date": [pd.Timestamp("2026-01-01")]})
    original = frame.copy(deep=True)
    shown = table_values(frame)
    pd.testing.assert_frame_equal(frame, original)
    assert shown.iloc[:, 1].tolist() == [-2500] and shown.iloc[:, 2].equals(frame.date)
    assert shown.iloc[0, 0] == f"`` {description} ``"
