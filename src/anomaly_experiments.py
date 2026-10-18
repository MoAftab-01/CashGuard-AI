"""Predeclared chronological candidate selection; final data is not an input."""

import csv
import hashlib
import io
import json
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

import numpy as np
import pandas as pd

from src.calibrated_anomalies import CANDIDATES, ReviewDetector
from src.analytics_utils import transaction_snapshot
from src.data_processing import validate_csv
from src.evaluation import classification_metrics

PROTOCOL_ID = "phase6-chronological-v1"
PARTITIONS = {"train": (0, 120, 1729), "calibration": (120, 60, 2718), "final": (180, 60, 31415)}


@dataclass(frozen=True)
class LabeledPartition:
    data: pd.DataFrame
    labels: pd.DataFrame


def anomaly_partition(name):
    """Generate one requested partition; callers need not open the final partition."""
    if name not in PARTITIONS:
        raise ValueError("Choose train, calibration or final")
    start_offset, days, seed = PARTITIONS[name]
    rng = np.random.default_rng(seed)
    start = date(2025, 1, 1) + timedelta(days=start_offset)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["date", "description", "amount", "category", "transaction_id"])
    labels = []
    salary_months = sorted({(start + timedelta(days=i)).month for i in range(days)
                            if (start + timedelta(days=i)).day == 1})

    def append(day, description, cents, category, injected=False, injection_type="background"):
        identity = f"{name}-{len(labels):05d}"
        writer.writerow([day, description, Decimal(int(cents)) / 100, category, identity])
        labels.append(dict(transaction_id=identity, is_injected=bool(injected), injection_type=injection_type))

    for offset in range(days):
        day = start + timedelta(days=offset)
        injection = name != "train" and (offset + 1) % 5 == 0
        injection_index = (offset + 1) // 5 - 1
        for slot, (category, typical) in enumerate((("Groceries", -2400), ("Transport", -800),
                                                    ("Shopping", -6500), ("Income", 16000))):
            cents = round(typical * rng.lognormal(0, .3))
            if slot == 1 and offset % 19 == 0:
                cents = 0
            is_injected = injection and slot == injection_index % 4
            multiplier = (2, 4, 12)[injection_index % 3] if is_injected else 1
            append(day, f"Fictional {category}", cents * multiplier, category,
                   is_injected, f"amount_x{multiplier}" if is_injected else "background")
        if day.day == 1:
            injected_salary = name != "train" and day.month == salary_months[1]
            append(day, "Fictional salary", 420000 * (3 if injected_salary else 1), "Income",
                   injected_salary, "recurring_amount_x3" if injected_salary else "background_recurring")
        if day.day == 3:
            append(day, "Fictional rent", -140000, "Housing", injection_type="background_recurring")
        if day.day == 15:
            append(day, "Fictional subscription", -4999, "Subscriptions", injection_type="background_recurring")
        if name != "train" and offset == 20:
            append(day, "Fictional annual insurance", -180000, "Insurance", injection_type="background_irregular")
    imported = validate_csv(output.getvalue())
    if imported.has_errors:
        raise RuntimeError("Synthetic phase 6 partition failed validation")
    # Canonical date sorting can move same-date rows; align labels by identity.
    ground_truth = imported.data[["transaction_id"]].merge(pd.DataFrame(labels), on="transaction_id", validate="one_to_one")
    return LabeledPartition(imported.data, ground_truth)


def aligned_labels(data, labels):
    if not {"transaction_id", "is_injected"} <= set(labels.columns):
        raise ValueError("Separate ground truth needs transaction_id and is_injected")
    for frame in (data, labels):
        if "transaction_id" not in frame:
            raise ValueError("Evaluation needs explicit transaction identities")
        if frame["transaction_id"].isna().any() or frame["transaction_id"].duplicated().any():
            raise ValueError("Evaluation identities must be unique and nonmissing")
    if set(data["transaction_id"]) != set(labels["transaction_id"]):
        raise ValueError("Labels must match evaluation identities exactly")
    joined = data[["transaction_id"]].merge(labels, on="transaction_id", validate="one_to_one")
    if any(not isinstance(value, (bool, np.bool_)) for value in joined["is_injected"]):
        raise ValueError("Ground-truth labels must be boolean")
    return joined


def score_metrics(scored, labels):
    joined = aligned_labels(scored, labels)
    return classification_metrics(joined["is_injected"].to_numpy(dtype=bool), scored["is_anomaly"].to_numpy(dtype=bool))


@dataclass(frozen=True)
class CandidateSelection:
    method: str
    threshold: float
    fingerprint: str
    calibration_metrics: pd.DataFrame
    detectors: dict[str, ReviewDetector]
    training_ids: frozenset
    calibration_ids: frozenset


def select_candidates(train, calibration, labels):
    """The final test is deliberately absent from this signature.

    Calibration both selects thresholds and ranks candidate families; its scores
    are selection evidence, not an unbiased performance estimate.
    """
    canonical = []
    for frame in (train, calibration):
        if "transaction_id" not in frame or frame["transaction_id"].isna().any() or frame["transaction_id"].duplicated().any():
            raise ValueError("Training and calibration require unique transaction identities")
        known, _ = transaction_snapshot(frame)
        canonical.append(known.sort_values(["date", "transaction_id"], kind="stable").reset_index(drop=True))
    train, calibration = canonical
    if set(train["transaction_id"]) & set(calibration["transaction_id"]):
        raise ValueError("Training/calibration identities must be disjoint")
    joined = aligned_labels(calibration, labels)
    background = ~joined["is_injected"].to_numpy(dtype=bool)
    detectors, rows = {}, []
    for method in CANDIDATES:
        detector = ReviewDetector(method).fit(train).calibrate(calibration, background_mask=background)
        # Rank on calibration only. Public score() intentionally forbids this window.
        raw = detector._score_raw(calibration)
        predicted = raw["anomaly_score"].to_numpy(dtype=float) > detector.threshold_
        metrics = classification_metrics(~background, predicted)
        rows.append(dict(method=method, threshold=detector.threshold_, **metrics))
        detectors[method] = detector
    # Exact ties prefer the simpler statistical family, then recurring context.
    simplicity = {name: rank for rank, name in enumerate(("context_stat", "amount_stat", "context_forest", "amount_forest", "legacy_calibrated", "legacy_auto"))}
    eligible = [row for row in rows if row["false_positive_rate"] is not None and row["false_positive_rate"] <= .05]
    if not eligible:
        raise ValueError("No candidate satisfies the predeclared calibration false-positive budget")
    best = max(eligible, key=lambda row: (row["f1"] if row["f1"] is not None else -1,
                                         row["precision"] if row["precision"] is not None else -1,
                                         row["recall"] if row["recall"] is not None else -1, -simplicity[row["method"]]))
    evidence = dict(protocol=PROTOCOL_ID, selected=best["method"], threshold=best["threshold"],
                    train=pd.util.hash_pandas_object(train, index=True).astype(str).tolist(),
                    calibration=pd.util.hash_pandas_object(calibration, index=True).astype(str).tolist(),
                    labels=joined["is_injected"].tolist())
    fingerprint = hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest()
    return CandidateSelection(best["method"], best["threshold"], fingerprint, pd.DataFrame(rows), detectors,
                              frozenset(train["transaction_id"]), frozenset(calibration["transaction_id"]))


def evaluate_selected_candidates(selection, final_data, labels):
    """Score all frozen candidates on matched examples; no fit or selection here."""
    aligned_labels(final_data, labels)
    if set(final_data["transaction_id"]) & (selection.training_ids | selection.calibration_ids):
        raise ValueError("Final identities must be disjoint from training and calibration")
    rows, predictions = [], []
    for method, detector in selection.detectors.items():
        scored = detector.score(final_data)
        joined = scored.merge(labels, on="transaction_id", validate="one_to_one")
        metrics = score_metrics(scored, labels)
        normal_recurring = joined.loc[joined["injection_type"] == "background_recurring"]
        rows.append(dict(method=method, threshold=detector.threshold_, selected=method == selection.method, **metrics,
                         background_recurring_rows=len(normal_recurring),
                         background_recurring_flags=int(normal_recurring["is_anomaly"].sum())))
        predictions.append(joined.assign(method=method))
    return pd.DataFrame(rows), pd.concat(predictions, ignore_index=True)


def run_candidate_benchmark():
    """Selection precedes first access to the final partition, including in the UI."""
    train, calibration = anomaly_partition("train"), anomaly_partition("calibration")
    selection = select_candidates(train.data, calibration.data, calibration.labels)
    final = anomaly_partition("final")
    metrics, predictions = evaluate_selected_candidates(selection, final.data, final.labels)
    return selection, metrics, predictions
