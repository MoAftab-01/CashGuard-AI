import importlib.util
import json
import sys

import pytest

from src import experiment_tracking as tracking


def test_tracking_disabled_is_optional_and_has_no_import_or_files(monkeypatch):
    monkeypatch.setattr(tracking, "local_tracking_uri", lambda *_: pytest.fail("Disabled tracking created storage"))
    assert tracking.track_legacy_evaluation(None, None).status == "disabled"
    assert tracking.track_candidate_evaluation(None, None, None, None).status == "disabled"


@pytest.mark.parametrize("uri", ["https://example.com", "http://192.168.1.1:5000", "http://127.0.0.1:5000/path", "sqlite://///server/db"])
def test_tracking_rejects_external_endpoints(uri):
    with pytest.raises(ValueError):
        tracking.local_tracking_uri(uri)


def test_real_local_mlflow_records_metrics_and_allowlisted_artifacts(tmp_path, monkeypatch):
    if importlib.util.find_spec("mlflow") is None:
        pytest.skip("Optional MLflow is not installed; install requirements-mlops.txt")
    from config import SAMPLE_DATA_PATH
    from mlflow import MlflowClient
    from src.data_processing import validate_csv
    from src.evaluation import evaluate_anomalies, evaluate_forecasts
    from src.evaluation_data import anomaly_benchmark

    # Route test artifacts to a private temporary local directory.
    monkeypatch.setattr(tracking, "PROJECT_ROOT", tmp_path)
    uri = "sqlite:///" + (tmp_path / "runs.db").as_posix()
    benchmark = anomaly_benchmark()
    anomaly = evaluate_anomalies(benchmark.train, benchmark.test, benchmark.labels)
    forecast = evaluate_forecasts(validate_csv(SAMPLE_DATA_PATH).data, "2500.00")
    result = tracking.track_legacy_evaluation(forecast, anomaly, enabled=True, tracking_uri=uri)
    assert result.status == "logged" and len(result.run_ids) == 2
    client = MlflowClient(tracking_uri=uri)
    run = client.get_run(result.run_ids[-1])
    assert run.info.status == "FINISHED" and run.data.metrics["f1"] == anomaly.metrics["f1"]
    assert run.data.params["seed"] == "42" and len(run.data.params["train_sha256"]) == 64
    assert run.data.tags["data_origin"] == "synthetic"
    paths = {item.path for item in client.list_artifacts(run.info.run_id, "evaluation")}
    assert paths == {"evaluation/aggregate_metrics.json", "evaluation/evaluation_0.html", "evaluation/evaluation_1.html"}
    aggregate = json.loads((tmp_path / "var/mlflow/artifacts" / run.info.run_id / "artifacts/evaluation/aggregate_metrics.json").read_text())
    assert aggregate["confusion_matrix"] == anomaly.metrics["confusion_matrix"]
    assert not any(name.endswith((".csv", ".pkl", ".joblib")) for name in paths)


def test_tracking_server_outage_is_graceful_and_environment_restored(monkeypatch):
    if importlib.util.find_spec("mlflow") is None:
        pytest.skip("Optional MLflow is not installed")
    monkeypatch.setenv("MLFLOW_HTTP_REQUEST_TIMEOUT", "7")
    result = tracking._record([], True, "http://127.0.0.1:9")
    assert result.status == "failed" and result.error_code == "tracking_unavailable"
    import os
    assert os.environ["MLFLOW_HTTP_REQUEST_TIMEOUT"] == "7"


def test_missing_optional_mlflow_does_not_break_evaluation(monkeypatch):
    monkeypatch.setitem(sys.modules, "mlflow", None)
    result = tracking._record([], True, "http://127.0.0.1:9")
    assert result.status == "failed" and not result.run_ids


def test_modified_demo_cannot_be_labeled_as_approved_synthetic(tmp_path, monkeypatch):
    private = tmp_path / "private.csv"
    private.write_text("PRIVATE-TRANSACTION-DATA")
    monkeypatch.setattr(tracking, "SAMPLE_DATA_PATH", private)
    result = tracking._record([], True, None)
    assert result.status == "rejected" and not result.run_ids
