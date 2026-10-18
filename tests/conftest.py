"""Financial fixtures shared by the Phase 2 contract tests."""

import csv
import io
from datetime import date, timedelta
from decimal import Decimal

import pytest

from src.data_processing import validate_csv


@pytest.fixture
def transactions():
    def build(rows):
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["date", "description", "amount", "category", "transaction_id"])
        for index, (day, description, cents, category) in enumerate(rows):
            writer.writerow([day.isoformat(), description, Decimal(cents) / 100, category, f"TEST-{index}"])
        result = validate_csv(buffer.getvalue())
        assert not result.has_errors, result.issues
        return result.data
    return build


@pytest.fixture
def regular_history(transactions):
    rows = []
    for offset in range(120):
        day = date(2026, 1, 1) + timedelta(days=offset)
        rows.append((day, "Daily spending", -1000, "Other"))
        if day.day == 1:
            rows.append((day, "Salary", 300000, "Income"))
        if day.day == 3:
            rows.append((day, "Rent", -100000, "Housing"))
    return transactions(rows)


@pytest.fixture(scope="session")
def demo_dashboard():
    """Read-only integration fixture; application caches remain session-local."""
    from config import SAMPLE_DATA_PATH
    from src.dashboard_service import build_dashboard
    imported = validate_csv(SAMPLE_DATA_PATH)
    return imported, build_dashboard(imported, "2500.00")


@pytest.fixture
def financial_context(demo_dashboard):
    from src.financial_context import build_financial_context
    return build_financial_context(demo_dashboard[1])


@pytest.fixture
def valid_ai_payload():
    return {
        "financial_health": {"explanation": "Historical activity supports the estimated cash position; keep a buffer for scheduled costs.",
                             "evidence_ids": ["estimated_balance", "historical_income"], "status": "supported"},
        "cash_flow_risk": {"explanation": "Projected balances are estimates; review the timing of recurring payments.",
                           "evidence_ids": ["forecast_minimum", "threshold_breaches"], "status": "supported"},
        "spending_insights": {"explanation": "Review unusual expenses against earlier spending; model coverage remains limited.",
                              "evidence_ids": ["anomaly_unusual", "anomaly_scored"], "status": "supported"},
        "scenario_interpretation": {"explanation": "No scenario is configured, so its effects are unavailable.",
                                    "evidence_ids": ["scenario_status"], "status": "insufficient_evidence"},
        "suggested_steps": {"explanation": "Review recurring commitments and preserve a cash buffer; reassess when inputs change.",
                            "evidence_ids": ["data_sufficiency"], "status": "supported"},
    }
