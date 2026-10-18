"""Chronological calibration and review severity, separate from the legacy API."""

from datetime import date, timedelta
from numbers import Real

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from src.analytics_utils import positive_integer, transaction_snapshot
from src.anomaly_detection import AnomalyDetector, AnomalyResult, InsufficientHistoryError, _unscored
from src.anomaly_features import RobustAmountFeatures

CANDIDATES = ("legacy_auto", "legacy_calibrated", "amount_forest", "context_forest", "amount_stat", "context_stat")
SEVERITIES = ("Informational", "Review recommended", "High priority")
TRANSACTION_FIELDS = ("date", "description", "amount_cents", "category", "transaction_id", "account", "merchant", "amount", "source_row")
POLICY_VERSION = "chronological-amount-v1"
# Frozen from the calibration-only run in reports/phase6/selection.json, before
# generating the final partition. The live family is fixed; its threshold uses
# strictly prior unlabeled reference data, never evaluation labels.
DEFAULT_REVIEW_METHOD = "context_stat"


def severity_level(flagged, percentile, ratio):
    """Percentile is an empirical background rank, never a fraud probability."""
    if not flagged:
        return "Informational"
    return "High priority" if percentile >= 99 and ratio >= 3 else "Review recommended"


def _snapshot(data):
    known, cutoff = transaction_snapshot(data)
    return known[[field for field in TRANSACTION_FIELDS if field in known]].copy(), cutoff


def _review_unscored(data):
    result = _unscored(data)
    for column in ("decision_threshold", "calibrated_percentile", "robust_deviation"):
        result[column] = np.nan
    result["severity"] = "Not scored"
    result["recurring_expected"] = pd.array([pd.NA] * len(result), dtype="boolean")
    result["recurring_reference_cents"] = np.nan
    result["calibration_end"] = pd.Series([None] * len(result), dtype=object)
    result["calibration_rows"] = pd.Series([None] * len(result), dtype=object)
    return result


class ReviewDetector:
    """Fit past features, calibrate on a later reference window, score still later.

    Labeled experiments can supply a separate background mask. Without labels all
    calibration rows form a reference population, not confirmed normal transactions.
    """

    def __init__(self, method="context_stat", *, target_rate=.05, random_state=42):
        if method not in CANDIDATES:
            raise ValueError("Choose a supported anomaly candidate")
        if isinstance(target_rate, bool) or not isinstance(target_rate, Real) or not 0 < target_rate < .5:
            raise ValueError("target_rate must be a finite rate between zero and one half")
        # Reuse existing seed/configuration validation.
        AnomalyDetector(random_state=random_state)
        self.method, self.target_rate, self.random_state = method, float(target_rate), random_state
        self._reset()

    def _reset(self):
        self.features_ = self.legacy_ = self.forest_ = None
        self.training_end_ = self.calibration_end_ = self.threshold_ = None
        self.calibration_scores_ = None

    def fit(self, data):
        self._reset()
        if data.empty:
            raise InsufficientHistoryError("Need at least 30 training rows spanning 30 days")
        known, cutoff = _snapshot(data)
        span = (cutoff - min(known["date"])).days + 1
        if len(known) < 30 or span < 30:
            raise InsufficientHistoryError("Need at least 30 training rows spanning 30 days")
        features = RobustAmountFeatures(use_recurring=self.method.startswith("context")).fit(known)
        if self.method.startswith("legacy"):
            self.legacy_ = AnomalyDetector(random_state=self.random_state).fit(known)
        elif self.method.endswith("forest"):
            self.forest_ = IsolationForest(n_estimators=200, contamination="auto", random_state=self.random_state, n_jobs=1)
            self.forest_.fit(features.transform(known))
        self.features_, self.training_end_ = features, cutoff
        return self

    def _score_raw(self, data):
        if self.features_ is None:
            raise RuntimeError("Fit the detector before scoring")
        if data.empty:
            return _review_unscored(data)
        known, _ = _snapshot(data)
        if min(known["date"]) <= self.training_end_:
            raise ValueError("Scoring dates must be strictly after training_end")
        comparisons = self.features_.describe(known)
        if self.legacy_ is not None:
            result = self.legacy_.score(known)
            # Keep legacy reference values and score explanations for honest ablation.
            for column in ("robust_deviation", "recurring_expected", "recurring_reference_cents"):
                result[column] = comparisons[column].to_numpy()
        else:
            result = _review_unscored(known)
            for column in comparisons:
                result[column] = comparisons[column].to_numpy()
            values = comparisons[["robust_deviation"]].to_numpy(dtype=float)
            scores = -self.forest_.score_samples(values) if self.forest_ is not None else values[:, 0]
            result["anomaly_score"] = scores
            result["explanation"] = [
                f"Amount is {row.amount_ratio:.2f}x the prior reference median "
                f"({row.reference_cents / 100:.3f} currency units; {row.reference_scope.lower()}, "
                f"{row.reference_count} training examples). Robust log amount deviation: {row.robust_deviation:.2f}. "
                + ("Expected recurring date matched; the amount is still assessed." if row.recurring_expected else "No supported recurring due date matched.")
                + (" Sparse category history; a broader reference is used." if row.reference_scope in {"Direction", "All training transactions"} else "")
                for row in comparisons.itertuples(index=False)]
        result["training_end"] = self.training_end_
        return result

    def calibrate(self, calibration, *, background_mask=None):
        # Failed recalibration must not leave a usable stale threshold.
        self.threshold_ = self.calibration_end_ = self.calibration_scores_ = None
        if calibration.empty:
            raise InsufficientHistoryError("Calibration needs at least 30 reference rows spanning 14 days")
        known, cutoff = _snapshot(calibration)
        # Preserve alignment by ID/date order: callers supply sorted canonical data.
        if background_mask is None:
            background = np.ones(len(known), dtype=bool)
        else:
            background = np.asarray(background_mask)
            if background.dtype.kind != "b" or background.shape != (len(calibration),):
                raise ValueError("Use a separate boolean background mask matching calibration rows")
            # Sorting inside snapshot must not silently detach ground truth.
            mask_frame = calibration[["date"]].copy()
            mask_frame["background"] = background
            background = mask_frame.sort_values("date", kind="stable")["background"].to_numpy(dtype=bool)
        normal = known.loc[background]
        span = (max(normal["date"]) - min(normal["date"])).days + 1 if len(normal) else 0
        if len(normal) < 30 or span < 14:
            raise InsufficientHistoryError("Calibration needs at least 30 reference rows spanning 14 days")
        scores = self._score_raw(known)["anomaly_score"].to_numpy(dtype=float)[background]
        threshold = (0.5 if self.method == "legacy_auto"
                     else float(np.quantile(scores, 1 - self.target_rate, method="higher")))
        if self.method.endswith("stat"):
            threshold = max(3.5, threshold)
        self.threshold_, self.calibration_end_ = threshold, cutoff
        self.calibration_scores_ = np.sort(scores.copy())
        return self

    def score(self, data):
        if self.threshold_ is None:
            raise RuntimeError("Fit and calibrate the detector before scoring")
        if data.empty:
            return _review_unscored(data)
        known, _ = _snapshot(data)
        if min(known["date"]) <= self.calibration_end_:
            raise ValueError("Scoring dates must be strictly after calibration_end")
        result = self._score_raw(known)
        scores = result["anomaly_score"].to_numpy(dtype=float)
        percentiles = 100 * np.searchsorted(self.calibration_scores_, scores, side="right") / len(self.calibration_scores_)
        flags = scores > self.threshold_
        result["is_anomaly"] = pd.array(flags, dtype="boolean")
        result["decision_threshold"] = self.threshold_
        result["calibrated_percentile"] = percentiles
        result["severity"] = [severity_level(flag, percentile, ratio)
                              for flag, percentile, ratio in zip(flags, percentiles, result["amount_ratio"])]
        result["calibration_end"] = self.calibration_end_
        result["calibration_rows"] = len(self.calibration_scores_)
        result["explanation"] += (f" Decision threshold: {self.threshold_:.4f}, strict greater-than; "
                                  f"calibrated on {len(self.calibration_scores_)} prior reference rows through {self.calibration_end_}. "
                                  "Calibration rank is not a probability. Unusual activity is not confirmed fraud.")
        return result


def detect_calibrated_anomalies(data, *, as_of=None, method=DEFAULT_REVIEW_METHOD, calibration_days=60, refit_every_days=30):
    """Live walk forward with an unlabeled, strictly prior calibration window.

    Candidate family is fixed by offline selection, never chosen on user data labels.
    Do not interpret target quantiles as a guaranteed future false-positive rate.
    """
    positive_integer(calibration_days, "calibration_days")
    positive_integer(refit_every_days, "refit_every_days")
    ReviewDetector(method)  # Validate even with empty history.
    known, cutoff = transaction_snapshot(data, as_of)
    result = _review_unscored(known)
    days = sorted(known["date"].unique())
    position = 0
    while position < len(days):
        day = days[position]
        calibration_start = day - timedelta(days=min(calibration_days, (day - date.min).days))
        train = known.loc[known["date"] < calibration_start]
        calibration = known.loc[(known["date"] >= calibration_start) & (known["date"] < day)]
        if train.empty or calibration.empty:
            position += 1
            continue
        detector = ReviewDetector(method)
        try:
            detector.fit(train).calibrate(calibration)
        except InsufficientHistoryError:
            position += 1
            continue
        end = position + 1
        while end < len(days) and (days[end] - day).days < refit_every_days:
            end += 1
        group = known.loc[(known["date"] >= day) & (known["date"] <= days[end - 1])]
        scored = detector.score(group)
        for column in scored.columns:
            if column not in known.columns:
                result.loc[group.index, column] = scored[column].to_numpy()
        position = end
    count = int(result["is_anomaly"].notna().sum())
    warnings = ["Calibrated amount review is an experimental budgeting aid; unusual transactions are not confirmed fraud.",
                "Live calibration uses unlabeled recent history; contamination or drift can change thresholds and recall. No live false-positive guarantee.",
                "Amount-only review does not detect weekday-only or semantic anomalies. Recurring context never exempts amounts.",
                "Severity uses empirical score rank plus an amount ratio, not fraud probability or exact attribution."]
    if count < len(result):
        warnings.append("Warmup transactions lack sufficient prior training/calibration history and remain unscored, not assessed normal.")
    if not count:
        warnings.append("Insufficient history: need 30 training rows/30 days and 30 later calibration rows/14 days before review.")
    return AnomalyResult(result, cutoff, tuple(warnings))
