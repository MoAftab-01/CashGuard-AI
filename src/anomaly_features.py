"""Training-only robust amount comparisons and existing recurring-payment context."""

from statistics import median

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin

from src.analytics_utils import transaction_snapshot
from src.forecasting import _group_key, _recurring_patterns

LOG_SCALE_FLOOR = 0.15


def _statistics(values):
    absolute = np.asarray([abs(int(value)) for value in values], dtype=float)
    logs = np.log1p(absolute)
    center = float(np.median(logs))
    return (float(median(absolute)), center, max(1.4826 * float(np.median(np.abs(logs - center))), LOG_SCALE_FLOOR), len(values))


class RobustAmountFeatures(TransformerMixin, BaseEstimator):
    """Absolute robust log deviation; no raw amount, direction or weekday axes.

    Direction selects a reference population, rather than acting as a rarity signal.
    Recurrence changes the reference only on supported due dates, never exempts rows.
    """

    def __init__(self, use_recurring=False):
        self.use_recurring = use_recurring

    def fit(self, X, y=None):
        known, cutoff = transaction_snapshot(X)
        groups, directions = {}, {}
        for row in known.itertuples(index=False):
            direction = int(np.sign(row.amount_cents))
            groups.setdefault((row.category, direction), []).append(int(row.amount_cents))
            directions.setdefault(direction, []).append(int(row.amount_cents))
        self.categories_ = {key: _statistics(values) for key, values in groups.items() if len(values) >= 3}
        self.directions_ = {key: _statistics(values) for key, values in directions.items()}
        self.global_ = _statistics(known["amount_cents"].tolist())
        patterns, _ = _recurring_patterns(known, cutoff)
        self.patterns_ = {pattern.key: pattern for pattern in patterns}
        self.training_end_ = cutoff
        return self

    def _expected_pattern(self, row):
        pattern = self.patterns_.get(_group_key(row))
        if pattern is None:
            return None
        try:
            due = pattern.next_date(pattern.last_date)
            while due < row["date"] and (row["date"] - due).days > 2:
                due = pattern.next_date(due)
            return pattern if abs((row["date"] - due).days) <= 2 else None
        except (OverflowError, ValueError):
            return None

    def describe(self, X):
        rows = []
        for _, row in X.iterrows():
            direction = int(np.sign(row["amount_cents"]))
            key = (row["category"], direction)
            if key in self.categories_:
                stats, scope = self.categories_[key], "Category and direction"
            elif direction in self.directions_:
                stats, scope = self.directions_[direction], "Direction"
            else:
                stats, scope = self.global_, "All training transactions"
            reference, center, scale, count = stats
            pattern = self._expected_pattern(row)
            if self.use_recurring and pattern is not None:
                reference = abs(pattern.amount_cents)
                center = float(np.log1p(reference))
                scale = LOG_SCALE_FLOOR
                count, scope = pattern.occurrences, "Recurring payment"
            absolute = abs(int(row["amount_cents"]))
            rows.append(dict(reference_cents=reference, reference_scope=scope, reference_count=count,
                             amount_ratio=absolute / max(reference, 1),
                             robust_deviation=abs(float(np.log1p(absolute)) - center) / scale,
                             recurring_expected=pattern is not None,
                             recurring_reference_cents=abs(pattern.amount_cents) if pattern else np.nan))
        return pd.DataFrame(rows, columns=["reference_cents", "reference_scope", "reference_count", "amount_ratio",
                                           "robust_deviation", "recurring_expected", "recurring_reference_cents"])

    def transform(self, X):
        return self.describe(X)[["robust_deviation"]].to_numpy(dtype=float)

    def get_feature_names_out(self, input_features=None):
        return np.asarray(["absolute_robust_log_amount_deviation"])
