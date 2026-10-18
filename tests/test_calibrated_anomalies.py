from copy import deepcopy
from dataclasses import replace
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from src.anomaly_detection import InsufficientHistoryError
from src.anomaly_experiments import anomaly_partition
from src.anomaly_features import RobustAmountFeatures
from src.calibrated_anomalies import ReviewDetector, detect_calibrated_anomalies, severity_level
from src.dashboard_service import dashboard_anomalies
from src.data_processing import empty_transactions
from src.explainability import anomaly_comparisons
from src.forecasting import forecast_cash_flow
from src.risk_engine import assess_risk


@pytest.fixture(scope="module")
def partitions():
    return anomaly_partition("train"), anomaly_partition("calibration")


def fitted(partitions, method="context_stat"):
    train, calibration = partitions
    return ReviewDetector(method).fit(train.data).calibrate(calibration.data, background_mask=~calibration.labels.is_injected.to_numpy(dtype=bool))


def test_known_log_amount_normalization_and_zero_reference(transactions):
    train = transactions([(date(2026, 1, 1) + timedelta(days=i), "Stable", -1000, "Groceries") for i in range(40)] +
                         [(date(2026, 1, 1) + timedelta(days=i), "Zero", 0, "Other") for i in range(40)])
    features = RobustAmountFeatures().fit(train)
    target = transactions([(date(2026, 4, 1), "Stable", -10000, "Groceries"), (date(2026, 4, 1), "Zero", 0, "Other")])
    values = features.describe(target)
    assert values.iloc[0].robust_deviation == pytest.approx(np.log(10001 / 1001) / .15)
    assert values.iloc[0].reference_cents == 1000 and values.iloc[0].amount_ratio == 10
    assert values.iloc[1].robust_deviation == 0 and values.iloc[1].reference_cents == 0
    assert np.isfinite(features.transform(target)).all()


def test_calibration_quantile_strict_boundary_and_severity(partitions, transactions, monkeypatch):
    train, calibration = partitions
    detector = ReviewDetector("context_stat").fit(train.data)
    reference = calibration.data.iloc[:40].copy()
    # Distinct dates spanning enough time, independent of the benchmark distribution.
    reference["date"] = [date(2025, 5, 1) + timedelta(days=i) for i in range(40)]
    monkeypatch.setattr(detector, "_score_raw", lambda data: pd.DataFrame({"anomaly_score": np.arange(len(data), dtype=float)}))
    detector.calibrate(reference)
    assert detector.threshold_ == 38  # 95th percentile with higher order statistic.
    target = transactions([(date(2025, 7, 1), "A", -1000, "Other"),
                           (date(2025, 7, 1), "B", -1000, "Other"), (date(2025, 7, 1), "C", -1000, "Other")])
    monkeypatch.setattr(detector, "_score_raw", lambda data: data.assign(anomaly_score=[38., 40., 40.], amount_ratio=[4., 2., 4.], explanation="Known threshold probe"))
    scored = detector.score(target)
    assert scored.is_anomaly.tolist() == [False, True, True]
    assert scored.severity.tolist() == ["Informational", "Review recommended", "High priority"]
    assert (scored.calibrated_percentile <= 100).all()


@pytest.mark.parametrize("flagged,rank,ratio,expected", [(False, 100, 99, "Informational"),
    (True, 98.99, 3, "Review recommended"), (True, 99, 2.99, "Review recommended"), (True, 99, 3, "High priority")])
def test_severity_boundaries(flagged, rank, ratio, expected):
    assert severity_level(flagged, rank, ratio) == expected


def test_recurring_context_assesses_large_payments_without_exemptions(partitions, transactions):
    train, _ = partitions
    detector = fitted(partitions)
    target = transactions([(date(2025, 7, 1), "Fictional salary", 420000, "Income"),
                           (date(2025, 7, 1), "Fictional salary", 1260000, "Income"),
                           (date(2025, 7, 4), "Fictional salary", 420000, "Income")])
    scored = detector.score(target)
    assert scored.recurring_expected.tolist() == [True, True, False]
    assert scored.is_anomaly.tolist() == [False, True, True]
    assert scored.iloc[1].severity == "High priority"
    assert scored.iloc[0].reference_scope == "Recurring payment"
    assert scored.iloc[1].reference_count == 4
    comparisons = anomaly_comparisons(train.data, scored.iloc[1])
    assert len(comparisons) == 3 and comparisons.description.eq("Fictional salary").all()
    assert comparisons.amount_cents.eq(420000).all()
    assert comparisons.date.max() <= scored.iloc[1].training_end


def test_training_statistics_and_threshold_never_learn_from_scored_peers(partitions, transactions):
    detector = fitted(partitions, "context_forest")
    before = deepcopy(detector.features_.categories_)
    threshold, references = detector.threshold_, detector.calibration_scores_.copy()
    target = transactions([(date(2025, 7, 1), "Fictional Groceries", -2500, "Groceries")])
    peer = transactions([(date(2025, 7, 1), "Extreme peer", -99999999999, "Groceries")])
    single = detector.score(target).iloc[0]
    batch = detector.score(pd.concat([target, peer])).iloc[0]
    assert single.anomaly_score == batch.anomaly_score and single.severity == batch.severity
    assert detector.features_.categories_ == before and detector.threshold_ == threshold
    np.testing.assert_array_equal(detector.calibration_scores_, references)


def test_calibration_cutoff_excludes_in_sample_and_same_day(partitions, transactions):
    detector = fitted(partitions)
    row = transactions([(detector.calibration_end_, "Same day", -1000, "Groceries")])
    with pytest.raises(ValueError, match="strictly after calibration_end"):
        detector.score(row)
    with pytest.raises(ValueError, match="training_end"):
        ReviewDetector().fit(partitions[0].data).calibrate(partitions[0].data)


def test_sparse_history_is_unscored_and_failed_recalibration_invalidates_threshold(partitions):
    empty = empty_transactions()
    result = detect_calibrated_anomalies(empty, as_of=date(2026, 1, 1))
    assert result.data.empty and result.scored_count == 0
    sparse = detect_calibrated_anomalies(partitions[0].data.head(1))
    assert sparse.scored_count == 0 and sparse.data.severity.eq("Not scored").all()
    assert sparse.data.calibrated_percentile.isna().all()
    assert any("Insufficient" in warning for warning in sparse.warnings)
    detector = fitted(partitions)
    with pytest.raises(InsufficientHistoryError):
        detector.calibrate(partitions[1].data.head(1))
    with pytest.raises(RuntimeError, match="calibrate"):
        detector.score(partitions[1].data.tail(1))
    with pytest.raises(InsufficientHistoryError):
        detector.fit(empty)
    assert detector.features_ is None


def test_walk_forward_ignores_future_and_preserves_financial_rows(partitions, transactions):
    train, calibration = partitions
    data = pd.concat([train.data, calibration.data], ignore_index=True)
    cutoff = data.date.max()
    first = detect_calibrated_anomalies(data)
    future = transactions([(cutoff + timedelta(days=1), "Future extreme", -99999999999, "New Category")])
    second = detect_calibrated_anomalies(pd.concat([data, future], ignore_index=True))
    columns = ["date", "amount_cents", "anomaly_score", "decision_threshold", "calibrated_percentile", "severity", "training_end", "calibration_end"]
    pd.testing.assert_frame_equal(first.data[columns], second.data.loc[second.data.date <= cutoff, columns].reset_index(drop=True))
    direct = detect_calibrated_anomalies(pd.concat([data, future], ignore_index=True), as_of=cutoff)
    pd.testing.assert_frame_equal(first.data, direct.data)
    assert first.scored_count > 0
    scored = first.data.loc[first.data.is_anomaly.notna()]
    assert (scored.training_end < scored.calibration_end).all()
    assert (scored.calibration_end < scored.date).all()
    assert first.data.amount_cents.sum() == data.amount_cents.sum()


def test_risk_rejects_future_calibration_provenance(partitions):
    data = pd.concat([partitions[0].data, partitions[1].data], ignore_index=True)
    report = detect_calibrated_anomalies(data)
    forecast = forecast_cash_flow(data, 2500)
    assess_risk(data, forecast, anomalies=report)
    bad = report.data.copy()
    mask = bad.is_anomaly.notna()
    bad.loc[mask, "calibration_end"] = bad.loc[mask, "date"]
    with pytest.raises(ValueError, match="calibration"):
        assess_risk(data, forecast, anomalies=replace(report, data=bad))


@pytest.mark.parametrize("kwargs", [{"method": "unknown"}, {"target_rate": 0}, {"target_rate": .5},
                                     {"target_rate": True}, {"target_rate": float("nan")}, {"random_state": True}])
def test_invalid_review_configuration(kwargs):
    with pytest.raises(ValueError):
        ReviewDetector(**kwargs)


def test_dashboard_engine_choice_is_explicit_and_legacy_remains_available(partitions):
    data = pd.concat([partitions[0].data, partitions[1].data], ignore_index=True)
    selected = dashboard_anomalies(data)
    legacy = dashboard_anomalies(data, engine="Legacy Isolation Forest")
    forest = dashboard_anomalies(data, engine="Calibrated Isolation Forest")
    assert "severity" in selected.data and "severity" in forest.data
    assert "severity" not in legacy.data
    assert selected.scored_count < legacy.scored_count  # Additional honest calibration warmup.
    with pytest.raises(ValueError, match="supported"):
        dashboard_anomalies(data, engine="unknown")
