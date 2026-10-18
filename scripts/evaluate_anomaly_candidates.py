"""Freeze calibration selection before opening a separate final test partition."""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import SAMPLE_DATA_PATH
from src.anomaly_detection import AnomalyDetector, detect_anomalies
from src.anomaly_experiments import PARTITIONS, PROTOCOL_ID, anomaly_partition, evaluate_selected_candidates, select_candidates
from src.data_processing import validate_csv
from src.evaluation import evaluate_anomalies, evaluate_forecasts
from src.evaluation_data import anomaly_benchmark
from src.visualizations import anomaly_confusion_chart, anomaly_score_chart


def records(frame):
    return json.loads(frame.to_json(orient="records", date_format="iso"))


def diagnose_phase5():
    benchmark = anomaly_benchmark()
    result = evaluate_anomalies(benchmark.train, benchmark.test, benchmark.labels)
    detector = AnomalyDetector().fit(benchmark.train)
    features = detector.pipeline_.named_steps["features"]
    train_features = features.transform(benchmark.train)
    raw_forest = IsolationForest(n_estimators=200, contamination="auto", random_state=42, n_jobs=1).fit(train_features)
    score_difference = np.abs(raw_forest.score_samples(train_features) - detector.pipeline_.score_samples(benchmark.train))
    distributions = {}
    for name, frame in (("train", benchmark.train), ("test_background", benchmark.test.loc[~benchmark.labels["is_injected"]])):
        values = pd.DataFrame(features.transform(frame), columns=features.get_feature_names_out())
        scores = -detector.pipeline_.score_samples(frame)
        summary = pd.DataFrame(dict(category=frame["category"].to_numpy(), score=scores, flagged=scores > .5))
        grouped = summary.groupby("category").agg(rows=("score", "size"), mean_score=("score", "mean"),
                                                  min_score=("score", "min"), max_score=("score", "max"), flagged=("flagged", "sum"))
        distributions[name] = dict(feature_means=values.mean().to_dict(),
                                   feature_std=values.std(ddof=0).to_dict(), by_category=records(grouped.reset_index()))
    sample = validate_csv(SAMPLE_DATA_PATH).data
    live = detect_anomalies(sample).data
    scheduled = live.loc[live["description"].str.contains("salary|rent|subscription", case=False, regex=True)]
    scheduled = scheduled.loc[scheduled["is_anomaly"].notna()]
    return dict(metrics=result.metrics, distributions=distributions,
                max_training_score_difference_without_scaler=float(score_difference.max()),
                score_direction_matches_sklearn=bool(np.array_equal(result.scored["is_anomaly"].to_numpy(dtype=bool),
                                                                     detector.pipeline_.predict(benchmark.test) == -1)),
                recurring_demo_review=records(scheduled[["date", "description", "category", "amount_cents", "is_anomaly", "anomaly_score"]]))


def final_evaluation(selection):
    # First access to this new holdout occurs only after the caller freezes selection.
    final = anomaly_partition("final")
    return evaluate_selected_candidates(selection, final.data, final.labels)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--calibration-only", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=Path("reports/phase6"))
    parser.add_argument("--track-mlflow", action="store_true", help="Log only allowlisted synthetic aggregates")
    parser.add_argument("--tracking-uri", default=None)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    train, calibration = anomaly_partition("train"), anomaly_partition("calibration")
    selection = select_candidates(train.data, calibration.data, calibration.labels)
    manifest = dict(protocol=PROTOCOL_ID, method=selection.method, threshold=selection.threshold,
                    fingerprint=selection.fingerprint, calibration_metrics=records(selection.calibration_metrics),
                    partitions=PARTITIONS, train_rows=len(train.data), calibration_rows=len(calibration.data),
                    train_end=str(train.data["date"].max()), calibration_end=str(calibration.data["date"].max()))
    frozen_path = args.output_dir / "selection.json"
    if args.calibration_only:
        if frozen_path.exists() and json.loads(frozen_path.read_text())["fingerprint"] != selection.fingerprint:
            parser.error("Selection differs from the frozen manifest. Do not retune against an opened final holdout.")
        frozen_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(selection.calibration_metrics[["method", "threshold", "precision", "recall", "f1", "false_positive_rate"]].to_string(index=False))
        print(f"Frozen selection: {selection.method}; fingerprint={selection.fingerprint}")
        return
    if not frozen_path.exists():
        parser.error("Run --calibration-only first to save selection before final evaluation")
    if json.loads(frozen_path.read_text())["fingerprint"] != selection.fingerprint:
        parser.error("Current calibration does not match the frozen selection; final evaluation blocked")
    metrics, predictions = final_evaluation(selection)
    forecast = evaluate_forecasts(validate_csv(SAMPLE_DATA_PATH).data, "2500.00")
    report = dict(measured_at_utc=datetime.now(timezone.utc).isoformat(), protocol=manifest,
                  phase5_reproduced=diagnose_phase5(), final_metrics=records(metrics),
                  forecast_metrics=records(forecast.metrics),
                  warnings=["Calibration selects candidates; only the separate final holdout estimates their performance.",
                            "Synthetic injection labels are not fraud labels. No real-world accuracy or guaranteed live FPR."])
    (args.output_dir / "results.json").write_text(json.dumps(report, allow_nan=False, indent=2), encoding="utf-8")
    predictions.to_csv(args.output_dir / "final_predictions.csv", index=False)
    for name, partition in (("train", train), ("calibration", calibration)):
        partition.data.to_csv(args.output_dir / f"{name}_transactions.csv", index=False)
        partition.labels.to_csv(args.output_dir / f"{name}_labels.csv", index=False)
    html = "<!doctype html><html lang='en'><meta charset='utf-8'><title>Phase 6 anomaly comparison</title><body style='font-family:system-ui;max-width:1200px;margin:auto;color:#10213a;background:white'><h1>Chronological synthetic final holdout</h1><p>Selection was frozen on calibration before this holdout was opened. Scores are not probabilities.</p>"
    first = True
    for row in metrics.to_dict("records"):
        html += f"<h2>{row['method']}{' (selected)' if row['selected'] else ''}</h2>"
        figure = anomaly_confusion_chart(row)
        figure.update_layout(font_color="#10213a")
        html += figure.to_html(full_html=False, include_plotlyjs=first)
        first = False
    selected = predictions.loc[predictions["method"] == selection.method]
    figure = anomaly_score_chart(selected, selection.threshold)
    figure.update_layout(font_color="#10213a")
    html += figure.to_html(full_html=False, include_plotlyjs=False) + "</body></html>"
    (args.output_dir / "evaluation.html").write_text(html, encoding="utf-8")
    if args.track_mlflow:
        from src.experiment_tracking import track_candidate_evaluation, tracking_record
        tracking = tracking_record(track_candidate_evaluation(selection, metrics, predictions, forecast,
                                   enabled=True, tracking_uri=args.tracking_uri))
        (args.output_dir / "tracking.json").write_text(json.dumps(tracking, indent=2), encoding="utf-8")
        print("Optional MLflow status: " + tracking["status"])
    print(metrics[["method", "precision", "recall", "f1", "false_positive_rate", "confusion_matrix"]].to_string(index=False))


if __name__ == "__main__":
    main()
