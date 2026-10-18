"""Reproduce Phase 5 results on fictional data only; no uploads or downloads."""

import argparse
import json
import os
import platform
import statistics
import sys
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from time import perf_counter

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import SAMPLE_DATA_PATH
from src.anomaly_detection import detect_anomalies
from src.dashboard_service import build_dashboard
from src.data_processing import validate_csv
from src.evaluation import evaluate_anomalies, evaluate_forecasts
from src.evaluation_data import anomaly_benchmark, synthetic_csv
from src.forecasting import forecast_cash_flow
from src.insight_workflow import generate_report
from src.llm_service import OllamaService, OllamaSettings
from src.visualizations import anomaly_confusion_chart, anomaly_score_chart, forecast_evaluation_chart


def records(frame):
    return json.loads(frame.to_json(orient="records", date_format="iso"))


def measure_performance(*, sizes=(250, 1000, 5000), repeats=3):
    """Cold engine calls, warm Python process; no disk I/O or rendering included."""
    if isinstance(repeats, bool) or not isinstance(repeats, int) or not 1 <= repeats <= 10:
        raise ValueError("repeats must be between 1 and 10")
    results = []
    for size in sizes:
        raw = synthetic_csv(size)
        samples = {name: [] for name in ("csv_processing", "forecast", "anomaly_detection", "dashboard_preparation")}
        for _ in range(repeats):
            start = perf_counter()
            imported = validate_csv(raw)
            samples["csv_processing"].append(perf_counter() - start)
            if imported.has_errors:
                raise RuntimeError("Benchmark CSV did not validate")
            start = perf_counter()
            forecast_cash_flow(imported.data, "2500.00")
            samples["forecast"].append(perf_counter() - start)
            start = perf_counter()
            detect_anomalies(imported.data)
            samples["anomaly_detection"].append(perf_counter() - start)
            start = perf_counter()
            # Fresh prep includes its OWN anomaly computation; no prior-result reuse.
            build_dashboard(imported, "2500.00")
            samples["dashboard_preparation"].append(perf_counter() - start)
        results.append(dict(rows=size, calendar_days=180, csv_bytes=len(raw), repeats=repeats,
                            seconds=samples, median_seconds={name: statistics.median(values) for name, values in samples.items()}))
    return results


def local_llm_smoke(bundle, model):
    """Separate, explicit real-model check. Never pull a missing model."""
    with OllamaService(OllamaSettings(model=model)) as service:
        status = service.check_availability()
        result = dict(model=service.settings.model, ready=status.ready, code=status.code,
                      mocked=False, inference_requested=False, response_seconds=None)
        if status.ready:
            start = perf_counter()
            report = generate_report(bundle, service)
            result.update(inference_requested=True, response_seconds=perf_counter() - start,
                          source=report.source, error_code=report.error_code,
                          validated_sections=list(type(report.insights).model_fields) if report.insights else [])
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("reports/phase5"))
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--skip-performance", action="store_true")
    parser.add_argument("--check-local-llm", action="store_true", help="If installed, request real local inference using fictional demo evidence")
    parser.add_argument("--llm-model", default="gemma3:4b")
    parser.add_argument("--track-mlflow", action="store_true", help="Explicitly log synthetic aggregates to optional local MLflow")
    parser.add_argument("--tracking-uri", default=None, help="Local SQLite URI or loopback MLflow server")
    args = parser.parse_args()
    if not 1 <= args.repeats <= 10:
        parser.error("--repeats must be between 1 and 10")
    imported = validate_csv(SAMPLE_DATA_PATH)
    if imported.has_errors:
        parser.error("Bundled demo failed validation")
    forecast = evaluate_forecasts(imported.data, "2500.00")
    benchmark = anomaly_benchmark()
    anomaly = evaluate_anomalies(benchmark.train, benchmark.test, benchmark.labels)
    report = dict(measured_at_utc=datetime.now(timezone.utc).isoformat(),
                  machine=dict(os=platform.platform(), processor=platform.processor(), logical_cpus=os.cpu_count(),
                               python=platform.python_version(), architecture=platform.machine(),
                               packages={package: version(package) for package in ("pandas", "numpy", "scikit-learn", "streamlit", "plotly", "pydantic", "pytest", "requests")}),
                  source="Bundled fictional demo, opening balance 2500.00 illustrative currency units",
                  forecast=dict(metrics=records(forecast.metrics), folds=records(forecast.folds), warnings=forecast.warnings),
                  anomaly=dict(metrics=anomaly.metrics, metadata=anomaly.metadata, warnings=anomaly.warnings,
                               false_positive_by_category=records(anomaly.scored.loc[~anomaly.scored["is_injected"]]
                                   .groupby("category")["is_anomaly"].agg(["count", "sum", "mean"]).reset_index()
                                   .rename(columns={"count": "background_rows", "sum": "false_positives", "mean": "false_positive_rate"}))),
                  performance=[] if args.skip_performance else measure_performance(repeats=args.repeats),
                  local_llm=dict(inference_requested=False, reason="Real-model check not requested"))
    if args.check_local_llm:
        report["local_llm"] = local_llm_smoke(build_dashboard(imported, "2500.00"), args.llm_model)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "results.json").write_text(json.dumps(report, default=str, allow_nan=False, indent=2), encoding="utf-8")
    forecast.predictions.to_csv(args.output_dir / "forecast_predictions.csv", index=False)
    forecast.folds.to_csv(args.output_dir / "forecast_folds.csv", index=False)
    anomaly.scored[["transaction_id", "date", "category", "amount_cents", "anomaly_score", "is_anomaly", "is_injected"]].to_csv(args.output_dir / "anomaly_holdout.csv", index=False)
    figures = [forecast_evaluation_chart(forecast.metrics), anomaly_confusion_chart(anomaly.metrics),
               anomaly_score_chart(anomaly.scored, anomaly.metadata["score_threshold"])]
    html = "<!doctype html><html lang='en'><meta charset='utf-8'><title>CashGuard synthetic evaluation</title>"
    html += "<body style='font-family:system-ui;max-width:1200px;margin:30px auto;background:white;color:#0f172a'>"
    html += "<h1>CashGuard AI: synthetic evaluation</h1><p>Measured fictional-data results; no real-world accuracy or fraud validation. "
    html += "Errors pool all forecast lead days per origin. See results.json and the technical report for methods, counts and limitations.</p>"
    for index, figure in enumerate(figures):
        figure.update_layout(font_color="#0f172a")
        html += figure.to_html(full_html=False, include_plotlyjs=True if index == 0 else False)
    html += "</body></html>"
    (args.output_dir / "evaluation.html").write_text(html, encoding="utf-8")
    if args.track_mlflow:
        from src.experiment_tracking import track_legacy_evaluation, tracking_record
        tracking = tracking_record(track_legacy_evaluation(forecast, anomaly, enabled=True, tracking_uri=args.tracking_uri))
        (args.output_dir / "tracking.json").write_text(json.dumps(tracking, indent=2), encoding="utf-8")
        print("Optional MLflow status: " + tracking["status"])
    print(json.dumps(dict(output_dir=str(args.output_dir), forecast_metrics=report["forecast"]["metrics"],
                          anomaly_metrics=anomaly.metrics,
                          performance=[dict(rows=row["rows"], **row["median_seconds"]) for row in report["performance"]],
                          local_llm=report["local_llm"]), default=str, allow_nan=False, indent=2))


if __name__ == "__main__":
    main()
