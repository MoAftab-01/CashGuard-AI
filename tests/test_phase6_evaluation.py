import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src import anomaly_experiments as experiments
from src.anomaly_experiments import anomaly_partition, evaluate_selected_candidates, select_candidates
from src.calibrated_anomalies import DEFAULT_REVIEW_METHOD
from src.evaluation import evaluate_forecasts


@pytest.fixture(scope="module")
def selected():
    train, calibration = anomaly_partition("train"), anomaly_partition("calibration")
    selection = select_candidates(train.data, calibration.data, calibration.labels)
    return train, calibration, selection


def test_partitions_are_chronological_and_labels_separate(selected):
    train, calibration, selection = selected
    final = anomaly_partition("final")
    assert train.data.date.max() < calibration.data.date.min() < final.data.date.min()
    assert calibration.data.date.max() < final.data.date.min()
    assert set(train.data.transaction_id).isdisjoint(final.data.transaction_id)
    assert selection.method == DEFAULT_REVIEW_METHOD
    for partition in (train, calibration, final):
        assert "is_injected" not in partition.data and "injection_type" not in partition.data
        assert partition.data.transaction_id.tolist() == partition.labels.transaction_id.tolist()
    assert final.labels.is_injected.sum() == 13
    manifest = json.loads(Path("reports/phase6/selection.json").read_text())
    assert selection.fingerprint == manifest["fingerprint"] and selection.threshold == manifest["threshold"]


def test_calibration_selection_runs_before_final_factory_access(monkeypatch, selected):
    order = []
    original_partition, original_select = experiments.anomaly_partition, experiments.select_candidates
    def partition(name):
        if name == "final":
            assert order[-1] == "selection_frozen"
        order.append(name)
        return original_partition(name)
    def select(*args):
        value = original_select(*args)
        order.append("selection_frozen")
        return value
    monkeypatch.setattr(experiments, "anomaly_partition", partition)
    monkeypatch.setattr(experiments, "select_candidates", select)
    experiments.run_candidate_benchmark()
    assert order == ["train", "calibration", "selection_frozen", "final"]


def test_final_labels_change_metrics_but_cannot_change_fitted_models(selected, monkeypatch):
    _, _, selection = selected
    final = anomaly_partition("final")
    for detector in selection.detectors.values():
        monkeypatch.setattr(detector, "fit", lambda *_: pytest.fail("No fitting is allowed during final evaluation"))
        monkeypatch.setattr(detector, "calibrate", lambda *_: pytest.fail("No calibration is allowed during final evaluation"))
    before = {name: (detector.threshold_, detector.training_end_, detector.calibration_end_)
              for name, detector in selection.detectors.items()}
    first, a = evaluate_selected_candidates(selection, final.data, final.labels)
    second, b = evaluate_selected_candidates(selection, final.data, final.labels.assign(is_injected=~final.labels.is_injected))
    columns = ["transaction_id", "method", "anomaly_score", "decision_threshold", "is_anomaly", "severity"]
    pd.testing.assert_frame_equal(a[columns], b[columns])
    assert not first["precision"].equals(second["precision"])
    assert before == {name: (detector.threshold_, detector.training_end_, detector.calibration_end_)
                      for name, detector in selection.detectors.items()}
    for method, frame in a.groupby("method"):
        assert frame.transaction_id.tolist() == final.data.transaction_id.tolist()
        assert frame.date.min() > selection.detectors[method].calibration_end_


def test_selection_uses_labels_by_identity_not_input_order(selected):
    train, calibration, selection = selected
    shuffled = select_candidates(train.data, calibration.data, calibration.labels.sample(frac=1, random_state=7))
    assert shuffled.method == selection.method and shuffled.fingerprint == selection.fingerprint
    pd.testing.assert_frame_equal(shuffled.calibration_metrics, selection.calibration_metrics)


def test_transaction_row_order_cannot_detach_calibration_labels(selected):
    train, calibration, selection = selected
    shuffled = select_candidates(train.data.sample(frac=1, random_state=11),
                                 calibration.data.sample(frac=1, random_state=12), calibration.labels)
    assert shuffled.fingerprint == selection.fingerprint
    pd.testing.assert_frame_equal(shuffled.calibration_metrics, selection.calibration_metrics)


@pytest.mark.parametrize("problem", ["duplicate_labels", "missing_labels", "string_labels", "reused_id", "earlier_final"])
def test_bad_holdouts_are_rejected(selected, problem):
    train, _, selection = selected
    final = anomaly_partition("final")
    data, labels = final.data.copy(), final.labels.copy()
    if problem == "duplicate_labels":
        labels = pd.concat([labels, labels.iloc[:1]])
    elif problem == "missing_labels":
        labels = labels.iloc[:-1]
    elif problem == "string_labels":
        labels["is_injected"] = "false"
    elif problem == "reused_id":
        data.loc[0, "transaction_id"] = labels.loc[0, "transaction_id"] = train.data.iloc[0].transaction_id
    else:
        data.loc[0, "date"] = selection.detectors[selection.method].calibration_end_
    with pytest.raises(ValueError):
        evaluate_selected_candidates(selection, data, labels)


def test_forecast_opening_shift_preserves_errors_and_naive_origins(demo_dashboard):
    data = demo_dashboard[0].data
    base = evaluate_forecasts(data, "2500.00")
    shifted = evaluate_forecasts(data, "2600.00")
    pd.testing.assert_frame_equal(base.metrics, shifted.metrics)
    for column in ("predicted_balance_cents", "actual_balance_cents"):
        assert (shifted.predictions[column] - base.predictions[column]).eq(10000).all()
    for origin, frame in base.predictions.groupby("cutoff"):
        naive = frame.loc[frame.method == "Last balance (zero net)"]
        expected = 250000 + sum(int(cents) for cents in data.loc[data.date <= origin, "amount_cents"])
        assert naive.predicted_balance_cents.eq(expected).all()
        assert naive.predicted_net_cents.eq(0).all()


def test_forecast_heldout_amount_mutation_does_not_change_first_origin(demo_dashboard):
    data = demo_dashboard[0].data
    origin = date(2026, 3, 31)
    original = evaluate_forecasts(data, 2500)
    changed = data.copy()
    changed.loc[changed.date > origin, "amount_cents"] *= 100
    mutated = evaluate_forecasts(changed, 2500)
    columns = ["cutoff", "date", "method", "horizon_days", "predicted_balance_cents", "predicted_net_cents"]
    pd.testing.assert_frame_equal(original.predictions.loc[original.predictions.cutoff == origin, columns].reset_index(drop=True),
                                  mutated.predictions.loc[mutated.predictions.cutoff == origin, columns].reset_index(drop=True))


def test_forecast_current_results_match_phase5_artifact(demo_dashboard):
    saved = json.loads(Path("reports/phase5/results.json").read_text())["forecast"]["metrics"]
    actual = evaluate_forecasts(demo_dashboard[0].data, "2500.00").metrics
    for row, current in zip(saved, actual.to_dict("records")):
        assert (row["horizon_days"], row["method"], row["target"], row["observation_count"]) == (
            current["horizon_days"], current["method"], current["target"], current["observation_count"])
        for metric in ("mae", "rmse", "bias"):
            assert current[metric] == pytest.approx(row[metric], abs=1e-8)
