"""Deterministic recurring-payment and residual-spending cash-flow baseline.

All monetary outputs are integer cents. Data after as_of is never used. These
are estimates, not guaranteed outcomes or verified account balances.
"""

from __future__ import annotations

import calendar
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from numbers import Integral
from statistics import median

import numpy as np
import pandas as pd

from src.analytics_utils import calendar_days, positive_integer, round_cents, transaction_snapshot
from src.metrics import money_to_cents

logger = logging.getLogger(__name__)
DAILY_COLUMNS = ["date", "inflow_cents", "outflow_cents", "net_cents", "balance_cents", "below_threshold"]
PREDICTION_COLUMNS = ["cutoff", "date", "predicted_net_cents", "actual_net_cents", "predicted_balance_cents", "actual_balance_cents"]


@dataclass(frozen=True)
class ForecastEvent:
    event_id: str
    date: date
    amount_cents: int
    kind: str
    description: str


@dataclass(frozen=True)
class RecurringPattern:
    key: tuple[str, ...]
    cadence: str
    amount_cents: int
    last_date: date
    occurrences: int
    day_of_month: int | None = None
    interval_days: int | None = None

    def next_date(self, previous: date) -> date:
        if self.cadence == "monthly":
            year = previous.year + (previous.month == 12)
            month = previous.month % 12 + 1
            return date(year, month, min(self.day_of_month, calendar.monthrange(year, month)[1]))
        return previous + timedelta(days=self.interval_days)


@dataclass(frozen=True)
class ForecastResult:
    as_of: date
    horizon_days: int
    current_balance_cents: int
    cash_threshold_cents: int
    history_days: int
    history_rows: int
    daily: pd.DataFrame
    events: tuple[ForecastEvent, ...]
    recurring_patterns: tuple[RecurringPattern, ...]
    assumptions: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def shortage_dates(self) -> tuple[date, ...]:
        return tuple(self.daily.loc[self.daily["below_threshold"], "date"])


def project_events(as_of: date, horizon_days: int, current_balance_cents: int,
                   cash_threshold_cents: int, events: tuple[ForecastEvent, ...]) -> pd.DataFrame:
    """Aggregate a forecast ledger; used by both baseline and scenario projections."""
    horizon_days = positive_integer(horizon_days, "horizon_days", 365)
    if type(as_of) is not date:
        raise ValueError("as_of must be a datetime.date")
    monetary_values = [current_balance_cents, cash_threshold_cents, *(event.amount_cents for event in events)]
    if any(isinstance(value, bool) or not isinstance(value, Integral) for value in monetary_values):
        raise ValueError("Forecast ledger amounts and balances must be integer cents")
    if any(type(event.date) is not date or not isinstance(event.event_id, str) or not event.event_id.strip() for event in events):
        raise ValueError("Forecast events require calendar dates and nonblank text IDs")
    dates = calendar_days(as_of, horizon_days + 1)[1:]
    flows = {day: [0, 0] for day in dates}
    if len({event.event_id for event in events}) != len(events):
        raise ValueError("Forecast event IDs must be unique")
    for event in events:
        if event.date not in flows:
            raise ValueError("Forecast event falls outside projection horizon")
        amount = int(event.amount_cents)
        flows[event.date][0 if amount >= 0 else 1] += abs(amount)
    balance = int(current_balance_cents)
    rows = []
    for day, (income, expenses) in flows.items():
        balance += income - expenses
        rows.append((day, income, expenses, income - expenses, balance, balance < cash_threshold_cents))
    return pd.DataFrame(rows, columns=DAILY_COLUMNS)


def _group_key(row: pd.Series) -> tuple[str, ...]:
    # Keep account, description and merchant to avoid conflating unrelated payments.
    return tuple(str(row.get(field) or "").strip().casefold()
                 for field in ("account", "description", "merchant", "category")) + (str(np.sign(row["amount_cents"])),)


def _recurring_patterns(history: pd.DataFrame, as_of: date) -> tuple[list[RecurringPattern], set[int]]:
    groups: dict[tuple[str, ...], list[int]] = {}
    for index, row in history.iterrows():
        if row["amount_cents"]:
            groups.setdefault(_group_key(row), []).append(index)
    patterns = []
    recurring_rows: set[int] = set()
    for key, indices in sorted(groups.items()):
        group = history.loc[indices].sort_values("date")
        dates = group["date"].tolist()
        if len(dates) < 3 or len(set(dates)) != len(dates):
            continue
        amounts = [int(value) for value in group["amount_cents"]]
        typical = round_cents(Decimal(str(median(amounts))))
        if max(abs(value - typical) for value in amounts) > abs(typical) * 0.35:
            continue
        months = [day.year * 12 + day.month for day in dates]
        month_steps = np.diff(months)
        anchor = max(day.day for day in dates)
        monthly = all(step == 1 for step in month_steps) and all(
            abs(day.day - min(anchor, calendar.monthrange(day.year, day.month)[1])) <= 2 for day in dates)
        gaps = [(right - left).days for left, right in zip(dates, dates[1:])]
        interval = next((days for days in (7, 14) if all(abs(gap - days) <= 1 for gap in gaps)), None)
        if not monthly and interval is None:
            continue
        pattern = RecurringPattern(key, "monthly" if monthly else "weekly" if interval == 7 else "biweekly",
                                   typical, dates[-1], len(dates), anchor if monthly else None,
                                   None if monthly else interval)
        # A missed expected date is evidence the old schedule may no longer hold.
        try:
            next_due = pattern.next_date(pattern.last_date)
        except (ValueError, OverflowError):
            continue
        if next_due <= as_of:
            continue
        patterns.append(pattern)
        recurring_rows.update(indices)
    return patterns, recurring_rows


def forecast_cash_flow(
    data: pd.DataFrame,
    opening_balance: Decimal | str | int | float,
    *,
    as_of: date | None = None,
    horizon_days: int = 30,
    cash_threshold: Decimal | str | int | float = 0,
    lookback_days: int = 180,
    include_irregular_income: bool = False,
) -> ForecastResult:
    """Project from an inclusive cutoff; opening balance precedes ALL imported history.

    The balance uses all known transactions, while recurring/residual estimation
    uses at most lookback_days. Calendar days without records are assumed complete
    zero-flow days. Exclude later rows even when supplied in the same DataFrame.
    """
    positive_integer(horizon_days, "horizon_days", 365)
    positive_integer(lookback_days, "lookback_days")
    if not isinstance(include_irregular_income, bool):
        raise ValueError("include_irregular_income must be boolean")
    known, cutoff = transaction_snapshot(data, as_of)
    calendar_days(cutoff, horizon_days + 1)  # Validate range before detecting schedules.
    current = money_to_cents(opening_balance) + sum(int(value) for value in known["amount_cents"])
    threshold = money_to_cents(cash_threshold)
    window_start = cutoff - timedelta(days=min(lookback_days - 1, (cutoff - date.min).days))
    history = known.loc[known["date"] >= window_start].reset_index(drop=True)
    history_days = (cutoff - min(history["date"])).days + 1 if not history.empty else 0
    warnings = ["Projections are estimates, not guaranteed outcomes. Missing records cannot be distinguished from zero-activity days."]
    if history_days < 30 or len(history) < 10:
        warnings.append("Insufficient history: fewer than 30 calendar days or 10 transactions; baseline reliability is limited.")
    if known.empty:
        warnings.append("No history at or before the cutoff; the projection is a constant opening balance.")
    elif (cutoff - max(known["date"])).days > 7:
        warnings.append("History is stale relative to the cutoff; confirm the export includes recent zero-activity days.")
    patterns, recurring_rows = _recurring_patterns(history, cutoff)
    residual = history.drop(index=list(recurring_rows))
    expense_total = -sum(int(value) for value in residual["amount_cents"] if value < 0)
    income_total = sum(int(value) for value in residual["amount_cents"] if value > 0)
    if income_total and not include_irregular_income:
        warnings.append("Unscheduled/irregular income is excluded; do not treat it as a guaranteed payment.")
    events = []
    end = cutoff + timedelta(days=horizon_days)
    for index, pattern in enumerate(patterns):
        due = pattern.next_date(pattern.last_date)
        while due <= end:
            events.append(ForecastEvent(f"recurring-{index}-{due.isoformat()}", due,
                                        pattern.amount_cents, "recurring", pattern.key[1]))
            if due == end:
                break
            try:
                due = pattern.next_date(due)
            except (ValueError, OverflowError):
                break
    for name, total, sign in (("spending", expense_total, -1),
                               ("income", income_total if include_irregular_income else 0, 1)):
        previous = 0
        for offset, day in enumerate(calendar_days(cutoff, horizon_days + 1)[1:], 1):
            cumulative = round_cents(Decimal(total) * offset / max(history_days, 1))
            amount = cumulative - previous
            previous = cumulative
            if amount:
                events.append(ForecastEvent(f"baseline-{name}-{day.isoformat()}", day,
                                            amount * sign, "baseline", f"Historical daily residual {name}"))
    ordered_events = tuple(sorted(events, key=lambda event: (event.date, event.event_id)))
    assumptions = (
        "Opening balance precedes the earliest imported transaction; the current balance uses only rows through as_of.",
        f"Estimation window: {history_days} calendar days, {len(history)} rows, maximum lookback {lookback_days} days.",
        "Recurring groups require at least 3 distinct dates, consecutive monthly or approximately 7/14-day intervals, and amounts within 35% of their median.",
        "Monthly schedules use the largest observed day-of-month anchor, clamped to month end; overdue schedules are not renewed.",
        "Recognized recurring rows are removed from residual totals to avoid double counting. Residual spending is averaged over all calendar days.",
        "Fractional daily cents are allocated by rounding cumulative expected totals half up, then differencing.",
        "Irregular income is averaged as an uncertain baseline." if include_irregular_income else "Irregular income is excluded by default.",
        "No seasonality, inflation, confidence intervals or completeness verification is modeled.",
    )
    daily = project_events(cutoff, horizon_days, current, threshold, ordered_events)
    logger.info("Forecast: history_rows=%d patterns=%d horizon=%d", len(history), len(patterns), horizon_days)
    return ForecastResult(cutoff, horizon_days, current, threshold, history_days, len(history), daily,
                          ordered_events, tuple(patterns), assumptions, tuple(warnings))


@dataclass(frozen=True)
class BacktestResult:
    predictions: pd.DataFrame
    folds: pd.DataFrame
    metrics: dict[str, float | None]
    warnings: tuple[str, ...]


def rolling_backtest(data: pd.DataFrame, opening_balance: Decimal | str | int | float = 0, *,
                     as_of: date | None = None, horizon_days: int = 30,
                     min_history_days: int = 90, step_days: int = 30,
                     lookback_days: int = 180, include_irregular_income: bool = False) -> BacktestResult:
    """Expanding chronological folds; only fully observed forecast horizons are scored.

    MAE/RMSE are in currency units for daily net flow and reconstructed balance.
    Each (origin, forecast date) is one observation, including overlapping horizons
    if step_days < horizon_days. No labels influence fitted forecast parameters.
    """
    for value, name in ((horizon_days, "horizon_days"), (min_history_days, "min_history_days"),
                        (step_days, "step_days"), (lookback_days, "lookback_days")):
        positive_integer(value, name, 365 if name == "horizon_days" else 3660)
    if not isinstance(include_irregular_income, bool):
        raise ValueError("include_irregular_income must be boolean")
    known, end = transaction_snapshot(data, as_of)
    money_to_cents(opening_balance)
    predictions = []
    fold_rows = []
    metrics: dict[str, float | None] = dict.fromkeys(["net_mae", "net_rmse", "balance_mae", "balance_rmse"])
    warnings = ["Backtests assume complete records on every calendar day; results on synthetic data do not establish real-world accuracy."]
    if step_days < horizon_days:
        warnings.append("Overlapping horizons: metrics weight each origin/date pair, not each unique calendar date.")
    if not known.empty:
        start = min(known["date"])
        available = (end - start).days + 1
        actual_daily = known.groupby("date")["amount_cents"].sum().to_dict()
        for offset in range(min_history_days - 1, available - horizon_days, step_days):
            cutoff = start + timedelta(days=offset)
            forecast = forecast_cash_flow(known, opening_balance, as_of=cutoff,
                                          horizon_days=horizon_days, lookback_days=lookback_days,
                                          include_irregular_income=include_irregular_income)
            actual_balance = forecast.current_balance_cents
            fold_predictions = []
            for row in forecast.daily.itertuples(index=False):
                actual_net = int(actual_daily.get(row.date, 0))
                actual_balance += actual_net
                fold_predictions.append((cutoff, row.date, row.net_cents, actual_net, row.balance_cents, actual_balance))
            frame = pd.DataFrame(fold_predictions, columns=PREDICTION_COLUMNS)
            predictions.extend(fold_predictions)
            fold_rows.append({"cutoff": cutoff, "train_rows": forecast.history_rows,
                              "train_end": cutoff, "test_start": cutoff + timedelta(days=1),
                              "test_end": cutoff + timedelta(days=horizon_days), **_errors(frame)})
    frame = pd.DataFrame(predictions, columns=PREDICTION_COLUMNS)
    if not frame.empty:
        metrics = _errors(frame)
    else:
        warnings.append("Insufficient history for a complete backtest fold; metrics are unavailable.")
    return BacktestResult(frame, pd.DataFrame(fold_rows), metrics, tuple(warnings))


def _errors(frame: pd.DataFrame) -> dict[str, float]:
    metrics = {}
    for name in ("net", "balance"):
        errors = (frame[f"predicted_{name}_cents"].to_numpy(dtype=float)
                  - frame[f"actual_{name}_cents"].to_numpy(dtype=float)) / 100
        metrics[f"{name}_mae"] = float(np.mean(np.abs(errors)))
        metrics[f"{name}_rmse"] = float(np.sqrt(np.mean(errors**2)))
    return metrics
