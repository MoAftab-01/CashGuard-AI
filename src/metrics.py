"""Exact descriptive analytics; callers must pass successfully validated data."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

import pandas as pd

CENT = Decimal("0.01")


def money_to_cents(value: Decimal | str | int | float) -> int:
    """Reject nonfinite values, excess precision and unbounded opening balances."""
    try:
        amount = Decimal(str(value))
        if (isinstance(value, bool) or not amount.is_finite() or abs(amount) >= Decimal("10000000000")
                or amount != amount.quantize(CENT)):
            raise ValueError("Enter a finite balance with at most two decimal places and magnitude below 10 billion")
        return int(amount * 100)
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("Enter a valid numeric opening balance") from exc


@dataclass(frozen=True)
class FinancialMetrics:
    transaction_count: int
    total_income: Decimal
    total_expenses: Decimal
    net_cash_flow: Decimal
    opening_balance: Decimal
    estimated_balance: Decimal
    start_date: date | None
    end_date: date | None


def calculate_metrics(data: pd.DataFrame, opening_balance: Decimal | str | int | float) -> FinancialMetrics:
    """Opening balance is immediately BEFORE the earliest imported transaction."""
    opening = money_to_cents(opening_balance)
    cents = [int(value) for value in data["amount_cents"]]
    income = sum(value for value in cents if value > 0)
    expenses = -sum(value for value in cents if value < 0)
    return FinancialMetrics(
        len(data), Decimal(income) / 100, Decimal(expenses) / 100,
        Decimal(income - expenses) / 100, Decimal(opening) / 100,
        Decimal(opening + income - expenses) / 100,
        min(data["date"]) if len(data) else None,
        max(data["date"]) if len(data) else None,
    )


def monthly_summary(data: pd.DataFrame) -> pd.DataFrame:
    """Observed months only; income/expense totals are positive, net is signed."""
    if data.empty:
        return pd.DataFrame(columns=["month", "income", "expenses", "net"])
    frame = data[["date", "amount_cents"]].copy()
    frame["month"] = frame["date"].map(lambda value: value.strftime("%Y-%m"))
    frame["income"] = frame["amount_cents"].clip(lower=0)
    frame["expenses"] = -frame["amount_cents"].clip(upper=0)
    grouped = frame.groupby("month")[["income", "expenses"]].sum()
    grouped["net"] = grouped["income"] - grouped["expenses"]
    return (grouped / 100).reset_index()


def category_expenses(data: pd.DataFrame) -> pd.DataFrame:
    expenses = data.loc[data["amount_cents"] < 0]
    totals = -expenses.groupby("category")["amount_cents"].sum() / 100
    return totals.rename("expenses").sort_values(ascending=False).reset_index()


def balance_history(data: pd.DataFrame, opening_balance: Decimal | str | int | float) -> pd.DataFrame:
    """End-of-observed-day estimates; no fabricated intraday ordering."""
    opening = money_to_cents(opening_balance)
    if data.empty:
        return pd.DataFrame(columns=["date", "estimated_balance"])
    daily = data.groupby("date", sort=True)["amount_cents"].sum()
    return ((daily.cumsum() + opening) / 100).rename("estimated_balance").reset_index()
