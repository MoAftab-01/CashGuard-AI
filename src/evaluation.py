"""Chronological, matched-window evaluation; never used to tune on test labels."""

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from src.analytics_utils import positive_integer
from src.anomaly_detection import AnomalyDetector, InsufficientHistoryError
from src.forecasting import rolling_backtest


@dataclass(frozen=True)
class ForecastEvaluation:
    metrics: pd.DataFrame
    predictions: pd.DataFrame
    folds: pd.DataFrame
    warnings: tuple[str, ...]


def evaluate_forecasts(data, opening_balance=0, *, as_of: date | None = None,
                       horizons=(7, 14, 30), min_history_days=90, step_days=30,
                       lookback_days=180, include_irregular_income=False) -> ForecastEvaluation:
    """Reuse engine rolling origins, with a constant last-known-balance baseline.

    Baseline daily net is zero. Bias = mean(prediction - actual). All errors are
    currency units, pooled over origin/date pairs, including every lead day.
    Horizons may have different eligible origins; methods within a horizon share
    exactly the same observations. Test data never selects forecast parameters.
    """
    horizons = tuple(horizons)
    if not horizons or len(set(horizons)) != len(horizons):
        raise ValueError("Choose at least one distinct forecast horizon")
    for horizon in horizons:
        positive_integer(horizon, "horizon_days", 365)
    metrics, predictions, folds, warnings = [], [], [], []
    for horizon in horizons:
        result = rolling_backtest(data, opening_balance, as_of=as_of, horizon_days=horizon,
                                  min_history_days=min_history_days, step_days=step_days,
                                  lookback_days=lookback_days, include_irregular_income=include_irregular_income)
        warnings.extend(result.warnings)
        fold_frame = result.folds.assign(horizon_days=horizon)
        folds.append(fold_frame)
        for method in ("Recurring + residual", "Last balance (zero net)"):
            frame = result.predictions.copy()
            if method == "Last balance (zero net)" and not frame.empty:
                origin_balances = frame.groupby("cutoff", sort=False).first()
                origin_balances = origin_balances["actual_balance_cents"] - origin_balances["actual_net_cents"]
                frame["predicted_balance_cents"] = frame["cutoff"].map(origin_balances)
                frame["predicted_net_cents"] = 0
            frame["method"], frame["horizon_days"] = method, horizon
            predictions.append(frame)
            for target in ("net", "balance"):
                errors = (frame[f"predicted_{target}_cents"].to_numpy(dtype=float)
                          - frame[f"actual_{target}_cents"].to_numpy(dtype=float)) / 100
                metrics.append(dict(horizon_days=horizon, method=method, target=target,
                                    fold_count=len(result.folds), observation_count=len(frame),
                                    test_start=frame["date"].min() if len(frame) else None,
                                    test_end=frame["date"].max() if len(frame) else None,
                                    mae=float(np.abs(errors).mean()) if len(errors) else None,
                                    rmse=float(np.sqrt(np.mean(errors**2))) if len(errors) else None,
                                    bias=float(errors.mean()) if len(errors) else None))
    return ForecastEvaluation(pd.DataFrame(metrics), pd.concat(predictions, ignore_index=True),
                              pd.concat(folds, ignore_index=True), tuple(dict.fromkeys(warnings)))


def classification_metrics(actual, predicted) -> dict:
    """Binary metrics with explicit unavailable denominators, never invented zeroes."""
    actual, predicted = np.asarray(actual), np.asarray(predicted)
    if actual.ndim != 1 or predicted.shape != actual.shape or actual.dtype.kind != "b" or predicted.dtype.kind != "b":
        raise ValueError("Use equally sized one-dimensional boolean labels and predictions")
    tp = int(np.sum(actual & predicted))
    fp = int(np.sum(~actual & predicted))
    fn = int(np.sum(actual & ~predicted))
    tn = int(np.sum(~actual & ~predicted))
    return dict(precision=tp / (tp + fp) if tp + fp else None,
                recall=tp / (tp + fn) if tp + fn else None,
                f1=2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
                false_positive_rate=fp / (fp + tn) if fp + tn else None,
                confusion_matrix=[[tn, fp], [fn, tp]], test_rows=len(actual), injected_count=tp + fn,
                predicted_unusual=tp + fp)


@dataclass(frozen=True)
class AnomalyEvaluation:
    scored: pd.DataFrame
    metrics: dict
    metadata: dict
    warnings: tuple[str, ...]


def evaluate_anomalies(train, test, labels, *, contamination="auto", random_state=42) -> AnomalyEvaluation:
    """One frozen chronological holdout. Labels join ONLY after score().

    Auto uses sklearn's fixed score threshold 0.5 (negative offset). Numeric
    contamination selects a training-score quantile. Neither uses holdout labels.
    This function reports synthetic injection detection, not fraud accuracy.
    """
    if not {"transaction_id", "is_injected"} <= set(labels.columns):
        raise ValueError("Separate labels need transaction_id and is_injected columns")
    for frame in (train, test, labels):
        if "transaction_id" not in frame or frame["transaction_id"].isna().any() or frame["transaction_id"].duplicated().any():
            raise ValueError("Evaluation requires unique, nonmissing transaction IDs")
    if set(train["transaction_id"]) & set(test["transaction_id"]):
        raise ValueError("Training and test identities must be disjoint")
    if set(labels["transaction_id"]) != set(test["transaction_id"]):
        raise ValueError("Labels must match the test transaction identities exactly")
    if any(not isinstance(value, (bool, np.bool_)) for value in labels["is_injected"]):
        raise ValueError("Ground-truth labels must be boolean")
    if not train.empty and not test.empty and max(train["date"]) >= min(test["date"]):
        raise ValueError("All test dates must be strictly after training dates")
    metadata = dict(train_rows=len(train), test_rows=len(test), random_state=random_state,
                    train_start=min(train["date"]) if len(train) else None,
                    train_end=max(train["date"]) if len(train) else None,
                    test_start=min(test["date"]) if len(test) else None,
                    test_end=max(test["date"]) if len(test) else None,
                    contamination=contamination, score_threshold=None)
    warnings = ("Synthetic injection detection only; labels are not confirmed fraud. No real-world accuracy is established.",
                "Threshold is fixed from training only; holdout labels never tune features, model or threshold.",
                "Scores are relative unusualness, not probabilities. Undefined metric denominators are unavailable.")
    if train.empty or test.empty:
        return AnomalyEvaluation(pd.DataFrame(), {}, metadata, (*warnings, "Insufficient training or test data; metrics unavailable."))
    # Whitelist transaction fields: external labels and other extras cannot enter fit.
    fields = ["date", "description", "amount_cents", "category", "transaction_id"]
    detector = AnomalyDetector(contamination=contamination, random_state=random_state)
    try:
        detector.fit(train[fields])
    except InsufficientHistoryError:
        return AnomalyEvaluation(pd.DataFrame(), {}, metadata, (*warnings, "Insufficient prior history; metrics unavailable."))
    scored = detector.score(test[fields])
    metadata["score_threshold"] = -float(detector.pipeline_.named_steps["forest"].offset_)
    scored = scored.merge(labels[["transaction_id", "is_injected"]], on="transaction_id", validate="one_to_one")
    metrics = classification_metrics(scored["is_injected"].to_numpy(dtype=bool), scored["is_anomaly"].to_numpy(dtype=bool))
    return AnomalyEvaluation(scored, metrics, metadata, warnings)
