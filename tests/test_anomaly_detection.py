from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from src.anomaly_detection import AnomalyDetector, InsufficientHistoryError, detect_anomalies
from src.data_processing import empty_transactions


@pytest.fixture
def anomaly_history(transactions):
    return transactions([(date(2026, 1, 1) + timedelta(days=i), f"Purchase {i}",
                          -(800 + (i % 9) * 50), "Groceries") for i in range(65)])


def test_features_and_scaler_are_fit_only_on_training_history(anomaly_history, transactions):
    train = anomaly_history.iloc[:45]
    detector = AnomalyDetector().fit(train)
    features = detector.pipeline_.named_steps["features"]
    scaler = detector.pipeline_.named_steps["scaler"]
    medians = features.category_medians_.copy()
    center = scaler.center_.copy()
    target = transactions([(date(2026, 3, 20), "Large", -10000000, "Groceries")])
    result = detector.score(target)
    assert features.category_medians_ == medians
    np.testing.assert_array_equal(scaler.center_, center)
    assert result.iloc[0]["training_end"] == train["date"].max()
    assert "prior reference median" in result.iloc[0]["explanation"]
    assert result.iloc[0]["is_anomaly"]
    assert np.isfinite(result["anomaly_score"]).all()


def test_fit_cutoff_ignores_future_rows(anomaly_history, transactions):
    cutoff = date(2026, 2, 15)
    target = transactions([(date(2026, 3, 10), "Target", -1100, "Groceries")])
    first = AnomalyDetector().fit(anomaly_history, as_of=cutoff)
    changed = anomaly_history.copy(deep=True)
    changed.loc[changed["date"] > cutoff, "amount_cents"] *= 10000
    second = AnomalyDetector().fit(changed, as_of=cutoff)
    np.testing.assert_array_equal(first.pipeline_.named_steps["scaler"].center_, second.pipeline_.named_steps["scaler"].center_)
    pd.testing.assert_frame_equal(first.score(target), second.score(target))


def test_walkforward_future_extreme_does_not_change_past_scores(anomaly_history, transactions):
    cutoff = anomaly_history["date"].max()
    future = transactions([(cutoff + timedelta(days=1), "Extreme future", -100000000, "New Category")])
    first = detect_anomalies(anomaly_history)
    second = detect_anomalies(pd.concat([anomaly_history, future], ignore_index=True))
    columns = ["date", "anomaly_score", "is_anomaly", "explanation", "training_end"]
    pd.testing.assert_frame_equal(first.data[columns], second.data.loc[second.data["date"] <= cutoff, columns].reset_index(drop=True))
    assert all(end < day for end, day in zip(first.data.loc[first.data["is_anomaly"].notna(), "training_end"], first.data.loc[first.data["is_anomaly"].notna(), "date"]))


def test_same_day_peer_cannot_change_score(anomaly_history, transactions):
    train = anomaly_history.iloc[:50]
    day = date(2026, 3, 20)
    target = transactions([(day, "Target", -1200, "Groceries")])
    peer = transactions([(day, "Same-day extreme", -99999999, "Groceries")])
    detector = AnomalyDetector().fit(train)
    single = detector.score(target).iloc[0]
    batch = detector.score(pd.concat([target, peer])).iloc[0]
    assert single["anomaly_score"] == batch["anomaly_score"]
    assert single["explanation"] == batch["explanation"]
    with pytest.raises(ValueError, match="strictly after"):
        detector.score(train.tail(1))


def test_warmup_is_unscored_and_empty_sparse_data_are_safe(anomaly_history):
    result = detect_anomalies(anomaly_history)
    assert result.data.iloc[:30]["is_anomaly"].isna().all()
    assert result.scored_count == 35
    assert result.data.iloc[:30]["anomaly_score"].isna().all()
    sparse = detect_anomalies(anomaly_history.head(10))
    assert sparse.scored_count == sparse.anomaly_count == 0
    empty = detect_anomalies(empty_transactions(), as_of=date(2026, 1, 1))
    assert empty.scored_count == 0 and empty.data.empty


def test_insufficient_history_is_checked_on_both_rows_and_days(anomaly_history):
    with pytest.raises(InsufficientHistoryError):
        AnomalyDetector().fit(anomaly_history.head(20))
    same_day = anomaly_history.copy()
    same_day["date"] = date(2026, 1, 1)
    with pytest.raises(InsufficientHistoryError):
        AnomalyDetector().fit(same_day)
    detector = AnomalyDetector().fit(anomaly_history)
    with pytest.raises(InsufficientHistoryError):
        detector.fit(anomaly_history.head(2))
    with pytest.raises(RuntimeError):
        detector.score(anomaly_history.tail(1))


def test_new_category_and_zero_amounts_have_finite_features(anomaly_history, transactions):
    detector = AnomalyDetector().fit(anomaly_history)
    target = transactions([(date(2026, 4, 1), "New income", 10000, "New Category"),
                           (date(2026, 4, 2), "Zero", 0, "Other")])
    result = detector.score(target)
    assert np.isfinite(result["anomaly_score"]).all()
    assert result["explanation"].str.contains("broader historical median").all()
    assert len(detector.pipeline_.named_steps["features"].get_feature_names_out()) == 6


def test_constant_training_and_fixed_seed_are_reproducible(anomaly_history, transactions):
    data = anomaly_history.copy()
    data["amount_cents"] = -1000
    before = data.copy(deep=True)
    one = detect_anomalies(data)
    two = detect_anomalies(data)
    pd.testing.assert_frame_equal(one.data, two.data)
    pd.testing.assert_frame_equal(data, before)
    assert np.isfinite(one.data["anomaly_score"].dropna()).all()
    detector = AnomalyDetector().fit(data)
    assert detector.score(empty_transactions()).empty


@pytest.mark.parametrize("kwargs", [{"min_training_rows": 9}, {"min_history_days": 0}, {"contamination": 0},
                                    {"contamination": 0.6}, {"contamination": "fraud"}, {"random_state": True},
                                    {"contamination": None}, {"contamination": float("nan")}])
def test_invalid_anomaly_configuration(kwargs):
    with pytest.raises(ValueError):
        AnomalyDetector(**kwargs)


def test_explicit_analysis_cutoff_drops_future_rows(anomaly_history):
    cutoff = date(2026, 2, 10)
    result = detect_anomalies(anomaly_history, as_of=cutoff)
    assert result.data["date"].max() == cutoff
    assert result.as_of == cutoff
