"""UI-independent orchestration and presentation contracts for the dashboard.

No Streamlit import or module-level user cache. Financial calculations are
delegated to the Phase 1/2 engines; derived comparisons use their actual outputs.
"""

from __future__ import annotations

from collections.abc import Callable, MutableMapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import TypeVar

import pandas as pd

from config import TRANSACTION_COLUMNS
from src import anomaly_detection, forecasting, metrics, risk_engine
from src.analytics_utils import transaction_snapshot
from src.data_processing import ImportResult
from src.scenario_simulator import ScenarioResult

T = TypeVar("T")


class DashboardInputError(ValueError):
    """An actionable import/configuration problem suitable for display."""


def require_ready_import(imported: ImportResult, *, reviewed_duplicates: bool = False) -> None:
    if imported.has_errors:
        raise DashboardInputError("Import has errors. Correct the source CSV and upload again. Financial summaries are blocked to avoid incomplete totals.")
    if imported.data.empty:
        raise DashboardInputError("No transactions are available. Upload a nonempty CSV or select the synthetic demo.")
    unresolved = any(issue.field == "duplicate" and "kept" in issue.message.lower() for issue in imported.issues)
    if unresolved and not reviewed_duplicates:
        raise DashboardInputError("Possible duplicate transactions need review. Remove identical rows without IDs, or confirm they are separate transactions before calculating totals.")


@dataclass(frozen=True)
class DashboardBundle:
    data: pd.DataFrame
    metrics: metrics.FinancialMetrics
    forecast: forecasting.ForecastResult
    anomalies: anomaly_detection.AnomalyResult
    risk: risk_engine.RiskResult
    balance_history: pd.DataFrame
    monthly: pd.DataFrame
    spending: pd.DataFrame


def build_dashboard(imported: ImportResult, opening_balance: str | Decimal | int, *,
                    as_of: date | None = None, cash_threshold: str | Decimal | int = "500.00",
                    include_irregular_income: bool = False, reviewed_duplicates: bool = False,
                    anomalies: anomaly_detection.AnomalyResult | None = None) -> DashboardBundle:
    """One consistent cutoff for KPIs, forecast, anomalies and risk components."""
    require_ready_import(imported, reviewed_duplicates=reviewed_duplicates)
    if isinstance(opening_balance, str) and not opening_balance.strip():
        raise DashboardInputError("Enter an opening balance before the first imported transaction. Enter 0 explicitly for a zero starting balance.")
    try:
        metrics.money_to_cents(opening_balance)
        metrics.money_to_cents(cash_threshold)
        data, cutoff = transaction_snapshot(imported.data, as_of)
        if data.empty:
            raise DashboardInputError("No transactions fall on or before the analysis date. Choose a later date.")
        forecast = forecasting.forecast_cash_flow(imported.data, opening_balance, as_of=cutoff,
                                                  cash_threshold=cash_threshold,
                                                  include_irregular_income=include_irregular_income)
        if anomalies is None:
            anomalies = anomaly_detection.detect_anomalies(imported.data, as_of=cutoff)
        if anomalies.as_of != cutoff:
            raise DashboardInputError("The anomaly report uses a different analysis date. Recalculate the current dataset.")
        # Reused reports must describe exactly this dataset, not a stale upload.
        columns = ["date", "description", "category", "amount_cents"]
        if not anomalies.data[columns].reset_index(drop=True).equals(data[columns].reset_index(drop=True)):
            raise DashboardInputError("The anomaly report belongs to different transactions. Recalculate the current dataset.")
        risk = risk_engine.assess_risk(data, forecast, anomalies=anomalies)
        return DashboardBundle(data, metrics.calculate_metrics(data, opening_balance), forecast, anomalies,
                               risk, metrics.balance_history(data, opening_balance),
                               metrics.monthly_summary(data), metrics.category_expenses(data))
    except DashboardInputError:
        raise
    except (ValueError, OverflowError) as exc:
        raise DashboardInputError(f"Check the opening balance, cash threshold and analysis date: {exc}") from exc


def session_value(state: MutableMapping, namespace: str, key: tuple, compute: Callable[[], T]) -> T:
    """Keep one current entry per namespace in caller-owned session state.

    The caller supplies a content fingerprint and all computation parameters.
    Errors are never cached. Replacing an entry releases its previous value.
    """
    cache = state.setdefault("cashguard_private_cache", {})
    entry = cache.get(namespace)
    if entry is None or entry[0] != key:
        value = compute()
        cache[namespace] = (key, value)
    return cache[namespace][1]


ANOMALY_ENGINES = ("Calibrated amount review", "Calibrated Isolation Forest", "Legacy Isolation Forest")


def dashboard_anomalies(data, *, as_of=None, engine=ANOMALY_ENGINES[0]):
    """Explicit UI choice, preserving legacy engine/API behavior for existing callers."""
    from src.calibrated_anomalies import detect_calibrated_anomalies
    if engine == "Legacy Isolation Forest":
        return anomaly_detection.detect_anomalies(data, as_of=as_of)
    if engine not in ANOMALY_ENGINES:
        raise DashboardInputError("Choose a supported anomaly review engine")
    return detect_calibrated_anomalies(data, as_of=as_of,
                                      method="context_forest" if engine == "Calibrated Isolation Forest" else "context_stat")


def filter_transactions(data: pd.DataFrame, *, start_date: date | None = None,
                        end_date: date | None = None, categories: Sequence[str] = (),
                        search: str = "", direction: str = "All") -> pd.DataFrame:
    """Inclusive table filters; never used to reconstruct a different opening balance."""
    if start_date is not None and end_date is not None and start_date > end_date:
        raise DashboardInputError("Start date must be on or before end date.")
    if direction not in {"All", "Income", "Expenses"}:
        raise DashboardInputError("Choose All, Income or Expenses.")
    mask = pd.Series(True, index=data.index)
    if start_date is not None:
        mask &= data["date"] >= start_date
    if end_date is not None:
        mask &= data["date"] <= end_date
    if categories:
        mask &= data["category"].isin(categories)
    if search.strip():
        mask &= data["description"].str.contains(search.strip(), case=False, regex=False, na=False)
    if direction != "All":
        mask &= data["amount_cents"] > 0 if direction == "Income" else data["amount_cents"] < 0
    return data.loc[mask].copy()


def display_transactions(data: pd.DataFrame) -> pd.DataFrame:
    frame = data.drop(columns=["amount_cents"], errors="ignore").copy()
    if "amount" in frame:
        frame["amount"] = frame["amount"].map(lambda value: f"{value:.2f}")
    return frame


def export_transactions(data: pd.DataFrame) -> bytes:
    """Export canonical CSV fields, exact money, and spreadsheet-safe text cells."""
    frame = display_transactions(data)
    frame = frame[[column for column in TRANSACTION_COLUMNS if column in frame]]
    for column in set(frame.columns) - {"date", "amount"}:
        frame[column] = frame[column].map(_spreadsheet_text)
    return frame.to_csv(index=False, lineterminator="\n").encode("utf-8-sig")


def _spreadsheet_text(value: object) -> object:
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def format_money(value: Decimal | int | str, currency: str = "USD") -> str:
    return f"{currency} {Decimal(value):,.2f}"


def format_cents(value: int, currency: str = "USD") -> str:
    return format_money(Decimal(int(value)) / 100, currency)


@dataclass(frozen=True)
class ScenarioComparison:
    baseline_minimum_cents: int
    scenario_minimum_cents: int
    closing_change_cents: int
    additional_breach_dates: tuple[date, ...]
    resolved_breach_dates: tuple[date, ...]


def compare_scenario(result: ScenarioResult) -> ScenarioComparison:
    baseline_dates = set(result.baseline.shortage_dates)
    scenario_dates = set(result.forecast.shortage_dates)
    return ScenarioComparison(int(result.baseline.daily["balance_cents"].min()),
                              int(result.forecast.daily["balance_cents"].min()),
                              result.closing_balance_change_cents,
                              tuple(sorted(scenario_dates - baseline_dates)),
                              tuple(sorted(baseline_dates - scenario_dates)))


def financial_summaries(bundle: DashboardBundle, currency: str = "USD", *,
                        scenario: ScenarioResult | None = None) -> list[tuple[str, str]]:
    """Fixed templates grounded exclusively in current engine outputs; no LLM calls."""
    m, f, a, r = bundle.metrics, bundle.forecast, bundle.anomalies, bundle.risk
    summaries = [
        ("Historical cash flow", f"Income is {format_money(m.total_income, currency)}, expenses are {format_money(m.total_expenses, currency)}, and net cash flow is {format_money(m.net_cash_flow, currency)} for {m.start_date} through {m.end_date}."),
        ("Estimated cash position", f"The reconstructed balance is {format_money(m.estimated_balance, currency)} as of {f.as_of}, using your opening balance of {format_money(m.opening_balance, currency)}. This is not a verified bank balance."),
        ("30-day projection", f"Projected closing cash is {format_cents(int(f.daily.iloc[-1]['balance_cents']), currency)}. The minimum projected daily balance is {format_cents(int(f.daily['balance_cents'].min()), currency)}. Projections are estimates."),
        ("Minimum cash threshold", f"There are {len(f.shortage_dates)} projected dates below {format_cents(f.cash_threshold_cents, currency)}." + (f" The first is {f.shortage_dates[0]}." if f.shortage_dates else " No threshold breach is projected under the current assumptions.")),
        ("Unusual activity", f"{a.anomaly_count} transactions are flagged unusual among {a.scored_count} scored transactions; {len(a.data) - a.scored_count} remain unscored. These flags are not confirmed fraud."),
        ("Financial risk indicator", f"The heuristic indicator is {r.level}" + (f" ({r.score}/100)" if r.score is not None else " (no score available)") + f". Data sufficiency: {r.data_sufficiency}. This is not a credit score or validated rating."),
    ]
    if scenario is not None:
        summaries.append(("Scenario outcome", f"The configured scenario changes projected closing cash by {format_cents(scenario.closing_balance_change_cents, currency)} and produces {len(scenario.forecast.shortage_dates)} threshold-breach dates. This is a hypothetical outcome."))
    return summaries
