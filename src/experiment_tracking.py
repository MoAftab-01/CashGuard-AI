"""Optional allowlisted tracking of explicit fictional benchmark evaluations only.

No autologging, transaction artifacts, model pickles, prompts, IDs or user histories.
Importing this module never imports MLflow or starts a tracking run.
"""

import hashlib
import json
import math
import os
import tempfile
from functools import wraps
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

from config import PROJECT_ROOT, SAMPLE_DATA_PATH
from src.settings import loopback_url

DEMO_SHA256 = "1d992cbd20c2b5265890db4dad4cb2420572788d2ccdbccfe3f7df4fe171f369"
EXPERIMENT = "cashguard-synthetic-v1"


@dataclass(frozen=True)
class TrackingResult:
    status: str
    run_ids: tuple[str, ...] = ()
    error_code: str | None = None


def local_tracking_uri(uri=None):
    if uri is None:
        directory = PROJECT_ROOT / "var" / "mlflow"
        directory.mkdir(parents=True, exist_ok=True)
        return "sqlite:///" + (directory / "mlflow.db").as_posix()
    if uri.startswith("sqlite:///"):
        raw = uri.removeprefix("sqlite:///")
        if not raw or raw.startswith(("//", "\\\\")) or "?" in raw or "#" in raw:
            raise ValueError("Only a local SQLite database or loopback HTTP tracking is permitted")
        path = Path(raw).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        return "sqlite:///" + path.as_posix()
    return loopback_url(uri)


def dataset_fingerprint(frame):
    return hashlib.sha256(frame.to_csv(index=False, lineterminator="\n").encode()).hexdigest()


def _forecast_metrics(frame):
    names = {"Recurring + residual": "recurring_residual", "Last balance (zero net)": "last_balance"}
    result = {}
    for row in frame.to_dict("records"):
        for metric in ("mae", "rmse", "bias"):
            value = row[metric]
            if value is not None and math.isfinite(float(value)):
                key = f"{names[row['method']]}_{row['target']}_{row['horizon_days']}_{metric}"
                result[key] = float(value)
    return result


def _record(entries, enabled, tracking_uri):
    if not enabled:
        return TrackingResult("disabled")
    # Protect the synthetic designation if someone replaces the bundled file.
    try:
        if hashlib.sha256(SAMPLE_DATA_PATH.read_bytes()).hexdigest() != DEMO_SHA256:
            return TrackingResult("rejected", error_code="unrecognized_synthetic_demo")
    except OSError:
        return TrackingResult("failed", error_code="synthetic_demo_unavailable")
    completed, active, client = [], None, None
    previous = {name: os.environ.get(name) for name in (
        "MLFLOW_HTTP_REQUEST_TIMEOUT", "MLFLOW_HTTP_REQUEST_MAX_RETRIES", "MLFLOW_ALLOW_HTTP_REDIRECTS",
        "MLFLOW_SUPPRESS_PRINTING_URL_TO_STDOUT", "NO_PROXY", "no_proxy")}
    try:
        os.environ["MLFLOW_DISABLE_TELEMETRY"] = "true"
        os.environ["MLFLOW_HTTP_REQUEST_TIMEOUT"] = "2"
        os.environ["MLFLOW_HTTP_REQUEST_MAX_RETRIES"] = "0"
        os.environ["MLFLOW_ALLOW_HTTP_REDIRECTS"] = "false"
        # MLflow's URL printer emits emoji before committing HTTP run termination;
        # Windows cp1252 consoles can otherwise leave a completed run RUNNING.
        os.environ["MLFLOW_SUPPRESS_PRINTING_URL_TO_STDOUT"] = "true"
        os.environ["NO_PROXY"] = os.environ["no_proxy"] = "127.0.0.1,localhost,::1"
        from mlflow import MlflowClient

        uri = local_tracking_uri(tracking_uri)
        network_tracking = uri.startswith("http://")
        client = MlflowClient(tracking_uri=uri)
        experiment = client.get_experiment_by_name(EXPERIMENT)
        if experiment is None:
            # Explicitly local artifacts, including with a loopback tracking server.
            artifacts = (PROJECT_ROOT / "var" / "mlflow" / "artifacts").resolve()
            artifacts.mkdir(parents=True, exist_ok=True)
            experiment_id = client.create_experiment(EXPERIMENT,
                artifact_location=None if network_tracking else artifacts.as_uri())
        else:
            experiment_id = experiment.experiment_id
        from urllib.parse import urlsplit
        location = urlsplit(client.get_experiment(experiment_id).artifact_location)
        expected_scheme = "mlflow-artifacts" if network_tracking else "file"
        if location.scheme != expected_scheme or location.netloc:
            return TrackingResult("rejected", error_code="nonlocal_artifact_store")
        for name, params, metrics, figures, aggregate in entries:
            run = client.create_run(experiment_id, tags={"mlflow.runName": name,
                    "data_origin": "synthetic", "validation_scope": "known synthetic benchmark replay",
                    "evaluation_timestamp": datetime.now(timezone.utc).isoformat()})
            active = run.info.run_id
            run_location = urlsplit(run.info.artifact_uri)
            if run_location.scheme != expected_scheme or run_location.netloc:
                raise ValueError("Nonlocal run artifact store")
            for key, value in params.items():
                client.log_param(active, key, value)
            for package in ("numpy", "pandas", "scikit-learn", "mlflow", "plotly"):
                client.log_param(active, "version_" + package, version(package))
            for key, value in metrics.items():
                if value is not None and math.isfinite(float(value)):
                    client.log_metric(active, key, float(value))
            with tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                (directory / "aggregate_metrics.json").write_text(json.dumps(aggregate, allow_nan=False, indent=2), encoding="utf-8")
                for index, figure in enumerate(figures):
                    figure.write_html(directory / f"evaluation_{index}.html", include_plotlyjs=True)
                for path in directory.iterdir():
                    client.log_artifact(active, str(path), artifact_path="evaluation")
            client.set_terminated(active, status="FINISHED")
            if client.get_run(active).info.status != "FINISHED":
                raise RuntimeError("Tracking run was not finished")
            completed.append(active)
            active = None
        return TrackingResult("logged", tuple(completed))
    except Exception:
        if client is not None and active is not None:
            try:
                client.set_terminated(active, status="FAILED")
            except Exception:
                pass
        # Evaluations remain valid and saved if optional tracking/storage fails.
        return TrackingResult("failed", tuple(completed), "tracking_unavailable")
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _forecast_entry(forecast):
    from src.visualizations import forecast_evaluation_chart
    return ("forecast", {"horizons": "7,14,30", "min_history_days": 90, "step_days": 30,
                         "lookback_days": 180, "irregular_income": False, "opening_balance": "2500.00",
                         "demo_sha256": DEMO_SHA256, "seed": 42},
            _forecast_metrics(forecast.metrics), [forecast_evaluation_chart(forecast.metrics)],
            json.loads(forecast.metrics.to_json(orient="records", date_format="iso")))


def optional_tracking(function):
    @wraps(function)
    def protected(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except Exception:
            return TrackingResult("failed", error_code="tracking_preparation_failed")
    return protected


@optional_tracking
def track_legacy_evaluation(forecast, anomaly, *, enabled=False, tracking_uri=None):
    if not enabled:
        return TrackingResult("disabled")
    from src.evaluation_data import anomaly_benchmark
    from src.anomaly_detection import TransactionFeatures
    from src.visualizations import anomaly_confusion_chart, anomaly_score_chart
    benchmark = anomaly_benchmark()
    params = dict(seed=42, method="legacy_auto", threshold=0.5, n_estimators=200,
                  features=",".join(TransactionFeatures().get_feature_names_out()),
                  train_sha256=dataset_fingerprint(benchmark.train), test_sha256=dataset_fingerprint(benchmark.test))
    metrics = {key: anomaly.metrics[key] for key in ("precision", "recall", "f1", "false_positive_rate")}
    return _record([_forecast_entry(forecast), ("legacy_anomalies", params, metrics,
                   [anomaly_confusion_chart(anomaly.metrics), anomaly_score_chart(anomaly.scored, .5)],
                   {key: anomaly.metrics[key] for key in (*metrics, "confusion_matrix")})], enabled, tracking_uri)


@optional_tracking
def track_candidate_evaluation(selection, metrics, predictions, forecast, *, enabled=False, tracking_uri=None):
    if not enabled:
        return TrackingResult("disabled")
    from src.anomaly_experiments import PARTITIONS, anomaly_partition
    from src.anomaly_detection import TransactionFeatures
    from src.anomaly_features import LOG_SCALE_FLOOR, RobustAmountFeatures
    from src.visualizations import anomaly_confusion_chart, anomaly_score_chart
    fingerprints = {name + "_sha256": dataset_fingerprint(anomaly_partition(name).data)
                    for name in ("train", "calibration", "final")}
    entries = [_forecast_entry(forecast)]
    for row in metrics.to_dict("records"):
        method = row["method"]
        params = dict(seed=42, method=method, threshold=row["threshold"],
                      selected_method=selection.method, selection_fingerprint=selection.fingerprint,
                      feature_configuration=",".join(TransactionFeatures().get_feature_names_out()
                          if method.startswith("legacy") else RobustAmountFeatures().get_feature_names_out()),
                      recurring_context=method.startswith("context"), log_scale_floor=LOG_SCALE_FLOOR,
                      n_estimators=200 if method.endswith("forest") or method.startswith("legacy") else 0,
                      target_calibration_rate=.05, partition_protocol=json.dumps(PARTITIONS, sort_keys=True),
                      **fingerprints)
        scored = predictions.loc[predictions["method"] == method]
        values = {name: row[name] for name in ("precision", "recall", "f1", "false_positive_rate")}
        entries.append(("candidate_" + method, params, values,
                        [anomaly_confusion_chart(row), anomaly_score_chart(scored, row["threshold"])],
                        {**values, "confusion_matrix": row["confusion_matrix"]}))
    return _record(entries, enabled, tracking_uri)


def tracking_record(result):
    return asdict(result)
