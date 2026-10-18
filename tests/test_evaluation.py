from datetime import date

import numpy as np
import pandas as pd
import pytest

from src.anomaly_detection import AnomalyDetector
from src.data_processing import empty_transactions
from src.evaluation import classification_metrics, evaluate_anomalies, evaluate_forecasts
from src.evaluation_data import anomaly_benchmark


def test_matched_origins_baseline_and_currency_errors(regular_history):
    result = evaluate_forecasts(regular_history, 100, horizons=(7, 14, 30))
    assert len(result.metrics) == 12
    for horizon, frame in result.predictions.groupby("horizon_days"):
        model, naive = [frame.loc[frame["method"] == name].reset_index(drop=True)
                        for name in ("Recurring + residual", "Last balance (zero net)")]
        pd.testing.assert_frame_equal(model[["cutoff", "date", "actual_net_cents", "actual_balance_cents"]],
                                      naive[["cutoff", "date", "actual_net_cents", "actual_balance_cents"]])
        assert (naive["predicted_net_cents"] == 0).all()
        assert (naive.groupby("cutoff")["predicted_balance_cents"].nunique() == 1).all()
        assert len(model) == horizon * result.folds.loc[result.folds["horizon_days"] == horizon].shape[0]
        for method, observations in frame.groupby("method"):
            for target in ("net", "balance"):
                row = result.metrics.loc[(result.metrics["horizon_days"] == horizon) &
                                         (result.metrics["method"] == method) & (result.metrics["target"] == target)].iloc[0]
                errors = (observations[f"predicted_{target}_cents"] - observations[f"actual_{target}_cents"]) / 100
                assert row.mae == pytest.approx(np.abs(errors).mean())
                assert row.rmse == pytest.approx(np.sqrt(np.mean(errors**2)))
                assert row.bias == pytest.approx(errors.mean())
                assert row.observation_count == len(observations)
    assert result.metrics.loc[result.metrics["method"] == "Recurring + residual", "mae"].eq(0).all()


def test_holdout_cannot_change_either_prediction_method(regular_history):
    cutoff = date(2026, 3, 31)
    changed = regular_history.copy()
    changed.loc[changed["date"] > cutoff, "amount_cents"] *= 100
    a = evaluate_forecasts(regular_history, horizons=(30,))
    b = evaluate_forecasts(changed, horizons=(30,))
    columns = ["date", "cutoff", "method", "predicted_net_cents", "predicted_balance_cents"]
    pd.testing.assert_frame_equal(a.predictions[columns], b.predictions[columns])
    assert a.metrics["mae"].sum() != b.metrics["mae"].sum()
    assert (a.folds["train_end"] < a.folds["test_start"]).all()


def test_evaluation_respects_asof_and_missing_metrics(regular_history):
    cutoff = date(2026, 3, 31)
    a = evaluate_forecasts(regular_history, as_of=cutoff, min_history_days=60)
    b = evaluate_forecasts(regular_history.loc[regular_history["date"] <= cutoff], min_history_days=60)
    pd.testing.assert_frame_equal(a.predictions, b.predictions)
    empty = evaluate_forecasts(empty_transactions(), as_of=cutoff)
    assert empty.predictions.empty and empty.metrics["mae"].isna().all()
    assert empty.metrics["observation_count"].eq(0).all()
    assert any("Insufficient" in warning for warning in empty.warnings)


@pytest.mark.parametrize("kwargs", [{"horizons": ()}, {"horizons": (7, 7)}, {"horizons": (True,)},
                                    {"horizons": (366,)}, {"include_irregular_income": "yes"}])
def test_evaluation_validates_controls_even_without_folds(kwargs):
    with pytest.raises(ValueError):
        evaluate_forecasts(empty_transactions(), as_of=date(2026, 1, 1), **kwargs)


def test_binary_metrics_known_confusion_and_undefined_denominators():
    result = classification_metrics([True, True, False, False, False], [True, False, True, False, False])
    assert result["confusion_matrix"] == [[2, 1], [1, 1]]
    assert result["precision"] == result["recall"] == result["f1"] == .5
    assert result["false_positive_rate"] == pytest.approx(1 / 3)
    none = classification_metrics(np.array([], dtype=bool), np.array([], dtype=bool))
    assert none["precision"] is none["recall"] is none["f1"] is none["false_positive_rate"] is None
    assert classification_metrics([False], [False])["precision"] is None
    assert classification_metrics([True], [False])["f1"] == 0
    with pytest.raises(ValueError):
        classification_metrics([1], [True])


def test_synthetic_labels_are_separate_and_scores_use_frozen_training():
    benchmark = anomaly_benchmark()
    repeat = anomaly_benchmark()
    pd.testing.assert_frame_equal(benchmark.test, repeat.test)
    assert "is_injected" not in benchmark.train and "is_injected" not in benchmark.test
    assert benchmark.labels["is_injected"].sum() == 12
    result = evaluate_anomalies(benchmark.train, benchmark.test, benchmark.labels)
    assert result.metrics["test_rows"] == 240
    assert sum(map(sum, result.metrics["confusion_matrix"])) == 240
    assert result.metadata["train_end"] < result.metadata["test_start"]
    assert result.metadata["score_threshold"] == .5
    direct = AnomalyDetector().fit(benchmark.train).score(benchmark.test)
    np.testing.assert_allclose(result.scored["anomaly_score"], direct["anomaly_score"])
    # Changing labels must change only evaluation, never model scores or flags.
    flipped = benchmark.labels.assign(is_injected=~benchmark.labels["is_injected"])
    second = evaluate_anomalies(benchmark.train, benchmark.test, flipped)
    pd.testing.assert_frame_equal(result.scored[["anomaly_score", "is_anomaly", "reference_cents"]],
                                  second.scored[["anomaly_score", "is_anomaly", "reference_cents"]])
    assert result.metrics != second.metrics
    # Labels added as extraneous columns are explicitly discarded before fitting.
    third = evaluate_anomalies(benchmark.train.assign(is_injected=True), benchmark.test.assign(is_injected=False), benchmark.labels)
    np.testing.assert_array_equal(third.scored["anomaly_score"], result.scored["anomaly_score"])


@pytest.mark.parametrize("problem", ["overlap", "labels_missing", "labels_duplicate", "test_duplicate", "not_boolean"])
def test_anomaly_evaluation_rejects_invalid_split_or_ground_truth(problem):
    b = anomaly_benchmark()
    train, test, labels = b.train.copy(), b.test.copy(), b.labels.copy()
    if problem == "overlap":
        test.loc[0, "date"] = train["date"].max()
    elif problem == "labels_missing":
        labels = labels.iloc[:-1]
    elif problem == "labels_duplicate":
        labels = pd.concat([labels, labels.iloc[:1]])
    elif problem == "test_duplicate":
        test.loc[1, "transaction_id"] = test.loc[0, "transaction_id"]
    else:
        labels["is_injected"] = "true"
    with pytest.raises(ValueError):
        evaluate_anomalies(train, test, labels)


def test_insufficient_anomaly_evaluation_does_not_invent_scores():
    b = anomaly_benchmark()
    result = evaluate_anomalies(b.train.iloc[:1], b.test, b.labels)
    assert not result.metrics and result.scored.empty
    assert any("Insufficient" in warning for warning in result.warnings)
