"""Chronological Isolation Forest novelty scoring; unusual never means proven fraud."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from numbers import Real
from statistics import median

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.ensemble import IsolationForest
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import RobustScaler

from src.analytics_utils import positive_integer, transaction_snapshot

logger = logging.getLogger(__name__)


class InsufficientHistoryError(ValueError):
    """The sample is too small for the configured anomaly training policy."""


class TransactionFeatures(TransformerMixin, BaseEstimator):
    """Learn reference medians and weekday frequencies ONLY during fit."""

    def fit(self, X: pd.DataFrame, y: object = None) -> TransactionFeatures:
        self.category_medians_: dict[tuple[str, int], float] = {}
        self.direction_medians_: dict[int, float] = {}
        self.weekday_counts_: dict[tuple[int, int], int] = {}
        self.direction_counts_: dict[int, int] = {}
        self.category_counts_: dict[tuple[str, int], int] = {}
        groups: dict[tuple[str, int], list[int]] = {}
        directions: dict[int, list[int]] = {}
        for row in X.itertuples(index=False):
            direction = int(np.sign(row.amount_cents))
            absolute = abs(int(row.amount_cents))
            groups.setdefault((row.category, direction), []).append(absolute)
            directions.setdefault(direction, []).append(absolute)
            key = (row.date.weekday(), direction)
            self.weekday_counts_[key] = self.weekday_counts_.get(key, 0) + 1
        self.category_medians_ = {key: max(float(median(values)), 1.0)
                                  for key, values in groups.items() if len(values) >= 3}
        self.category_counts_ = {key: len(values) for key, values in groups.items()}
        self.training_count_ = len(X)
        self.direction_medians_ = {key: max(float(median(values)), 1.0) for key, values in directions.items()}
        self.direction_counts_ = {key: len(values) for key, values in directions.items()}
        self.global_median_ = max(float(median(abs(int(value)) for value in X["amount_cents"])), 1.0)
        self.n_features_in_ = len(X.columns)
        return self

    def reference_amount(self, category: str, direction: int) -> float:
        return self.category_medians_.get((category, direction),
                                          self.direction_medians_.get(direction, self.global_median_))

    def transform(self, X: pd.DataFrame) -> np.ndarray:
        rows = []
        for row in X.itertuples(index=False):
            direction = int(np.sign(row.amount_cents))
            absolute = abs(int(row.amount_cents))
            reference = self.reference_amount(row.category, direction)
            weekday = row.date.weekday()
            probability = (self.weekday_counts_.get((weekday, direction), 0) + 1) / (self.direction_counts_.get(direction, 0) + 7)
            rows.append([np.log1p(absolute / 100), direction, np.log1p(absolute / reference),
                         np.sin(2 * np.pi * weekday / 7), np.cos(2 * np.pi * weekday / 7),
                         -np.log(probability)])
        return np.asarray(rows, dtype=float).reshape(-1, 6)

    def get_feature_names_out(self, input_features: object = None) -> np.ndarray:
        return np.asarray(["log_absolute_amount", "direction", "log_relative_amount",
                           "weekday_sin", "weekday_cos", "weekday_rarity"])


def _unscored(data: pd.DataFrame) -> pd.DataFrame:
    result = data.copy()
    result["anomaly_score"] = np.nan
    result["is_anomaly"] = pd.array([pd.NA] * len(result), dtype="boolean")
    result["explanation"] = "Insufficient prior training history; no model score"
    result["training_end"] = pd.Series([None] * len(result), dtype=object)
    result["reference_cents"] = np.nan
    result["amount_ratio"] = np.nan
    result["reference_count"] = pd.Series([None] * len(result), dtype=object)
    result["reference_scope"] = pd.Series([None] * len(result), dtype=object)
    return result


class AnomalyDetector:
    """Fit history explicitly, then score strictly later calendar dates.

    Minima default to 30 records spanning 30 days. The convenience function below
    leaves warmup rows unscored, rather than pretending they were assessed normal.
    """

    def __init__(self, *, min_training_rows: int = 30, min_history_days: int = 30,
                 contamination: float | str = "auto", random_state: int = 42) -> None:
        self.min_training_rows = positive_integer(min_training_rows, "min_training_rows", 100_000)
        if self.min_training_rows < 10:
            raise ValueError("min_training_rows must be at least 10")
        self.min_history_days = positive_integer(min_history_days, "min_history_days")
        if contamination != "auto" and (isinstance(contamination, bool) or not isinstance(contamination, Real)
                                         or not 0 < contamination <= 0.5):
            raise ValueError("contamination must be 'auto' or in (0, 0.5]")
        if isinstance(random_state, bool) or not isinstance(random_state, int) or not 0 <= random_state < 2**32:
            raise ValueError("random_state must be an integer in [0, 2**32)")
        self.contamination = contamination
        self.random_state = random_state
        self.pipeline_: Pipeline | None = None
        self.training_end_: date | None = None

    def fit(self, data: pd.DataFrame, *, as_of: date | None = None) -> AnomalyDetector:
        self.pipeline_ = None
        self.training_end_ = None
        known, _ = transaction_snapshot(data, as_of)
        span = (max(known["date"]) - min(known["date"])).days + 1 if len(known) else 0
        if len(known) < self.min_training_rows or span < self.min_history_days:
            raise InsufficientHistoryError("Need sufficient prior rows and calendar history before Isolation Forest training")
        pipeline = Pipeline([
            ("features", TransactionFeatures()),
            ("scaler", RobustScaler()),
            ("forest", IsolationForest(n_estimators=200, contamination=self.contamination,
                                       random_state=self.random_state, n_jobs=1)),
        ])
        pipeline.fit(known)
        self.pipeline_ = pipeline
        # Even if fit(as_of=...) is later than the final record, no same-day scoring.
        self.training_end_ = max(known["date"])
        return self

    def score(self, data: pd.DataFrame) -> pd.DataFrame:
        if self.pipeline_ is None:
            raise RuntimeError("Fit the detector on sufficient prior history before scoring")
        if data.empty:
            return _unscored(data)
        known, _ = transaction_snapshot(data)
        if min(known["date"]) <= self.training_end_:
            raise ValueError("Scoring dates must be strictly after training_end; same-day or in-sample scoring is prohibited")
        result = _unscored(known)
        # Higher scores are more unusual; they are NOT calibrated probabilities.
        raw_scores = self.pipeline_.score_samples(known)
        result["anomaly_score"] = -raw_scores
        # sklearn predict flags decision_function < 0; avoid scoring the forest twice.
        result["is_anomaly"] = pd.array(raw_scores < self.pipeline_.named_steps["forest"].offset_, dtype="boolean")
        features = self.pipeline_.named_steps["features"]
        explanations = []
        references = []
        for row in known.itertuples(index=False):
            direction = int(np.sign(row.amount_cents))
            reference = features.reference_amount(row.category, direction)
            ratio = abs(int(row.amount_cents)) / reference
            category_reference = (row.category, direction) in features.category_medians_
            scope = "Category and direction" if category_reference else "Direction" if direction in features.direction_medians_ else "All training transactions"
            count = (features.category_counts_[(row.category, direction)] if category_reference
                     else features.direction_counts_.get(direction, features.training_count_))
            references.append((reference, ratio, count, scope))
            reasons = []
            if not category_reference:
                reasons.append("Fewer than 3 prior category/direction examples; comparison uses a broader historical median")
            if ratio >= 3:
                reasons.append(f"Amount is {ratio:.1f}x the prior reference median ({reference / 100:.2f} currency units; {scope.lower()}, {count} training examples)")
            if features.weekday_counts_.get((row.date.weekday(), direction), 0) == 0:
                reasons.append("No prior examples of this direction on this weekday")
            if not reasons:
                reasons.append(f"Amount is {ratio:.1f}x the prior reference median; the model evaluates the combined amount, direction and weekday features")
            explanations.append("; ".join(reasons))
        result["explanation"] = explanations
        for index, column in enumerate(("reference_cents", "amount_ratio", "reference_count", "reference_scope")):
            result[column] = [reference[index] for reference in references]
        result["training_end"] = self.training_end_
        return result


@dataclass(frozen=True)
class AnomalyResult:
    data: pd.DataFrame
    as_of: date
    warnings: tuple[str, ...]

    @property
    def scored_count(self) -> int:
        return int(self.data["is_anomaly"].notna().sum())

    @property
    def anomaly_count(self) -> int:
        return int(self.data["is_anomaly"].fillna(False).sum())


def detect_anomalies(data: pd.DataFrame, *, as_of: date | None = None,
                     min_training_rows: int = 30, min_history_days: int = 30,
                     refit_every_days: int = 30, contamination: float | str = "auto",
                     random_state: int = 42) -> AnomalyResult:
    """Walk forward by calendar date, refitting periodically on strictly prior rows.

    Rows on a scoring date are all scored by the same frozen model. They cannot
    affect each other's category references or scores. Future rows never influence
    warmup, fit statistics, scaling, model thresholds or explanations.
    """
    positive_integer(refit_every_days, "refit_every_days")
    detector = AnomalyDetector(min_training_rows=min_training_rows, min_history_days=min_history_days,
                               contamination=contamination, random_state=random_state)
    known, cutoff = transaction_snapshot(data, as_of)
    result = _unscored(known)
    last_fit_day: date | None = None
    days = sorted(known["date"].unique())
    position = 0
    while position < len(days):
        day = days[position]
        if last_fit_day is None or (day - last_fit_day).days >= refit_every_days:
            prior = known.loc[known["date"] < day]
            if prior.empty:
                position += 1
                continue
            try:
                detector.fit(prior)
            except InsufficientHistoryError:
                position += 1
                continue
            last_fit_day = day
        # Score the whole frozen-model interval once, without fitting on its rows.
        # Difference comparisons avoid overflowing date.max for large intervals.
        end_position = position + 1
        while end_position < len(days) and (days[end_position] - last_fit_day).days < refit_every_days:
            end_position += 1
        group = known.loc[(known["date"] >= day) & (known["date"] <= days[end_position - 1])]
        scored = detector.score(group)
        columns = ["anomaly_score", "is_anomaly", "explanation", "training_end",
                   "reference_cents", "amount_ratio", "reference_count", "reference_scope"]
        # score() resets its index; assign positionally to preserve duplicate dates.
        for column in columns:
            result.loc[group.index, column] = scored[column].to_numpy()
        position = end_position
    warnings = ["Unusual transactions are not confirmed fraud. Scores are relative model scores, not fraud probabilities.",
                "Feature comparisons explain historical differences, not causal feature attribution. No labeled fraud accuracy is available."]
    count = int(result["is_anomaly"].notna().sum())
    if count < len(result):
        warnings.append("Warmup transactions lack sufficient prior history and remain unscored; anomaly rates use only scored rows.")
    if not count:
        warnings.append("Insufficient prior history: no transactions could be scored.")
    logger.info("Anomaly analysis: rows=%d scored=%d", len(result), count)
    return AnomalyResult(result, cutoff, tuple(warnings))
