"""Normalize once per request; all financial calculations remain in src engines."""

import csv
import io
from dataclasses import asdict
from contextlib import nullcontext

import pandas as pd

from api.schemas import responses as out
from config import TRANSACTION_COLUMNS
from src.analytics_utils import transaction_snapshot
from src.dashboard_service import (build_dashboard, compare_scenario, dashboard_anomalies,
                                   require_ready_import)
from src.data_processing import validate_csv
from src.forecasting import forecast_cash_flow
from src.insight_workflow import generate_report
from src.metrics import calculate_metrics
from src.risk_engine import assess_risk
from src.scenario_simulator import simulate_scenario


def import_transactions(request):
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=TRANSACTION_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for transaction in request.transactions:
        writer.writerow(transaction.model_dump(mode="json"))
    return validate_csv(stream.getvalue(), remove_ambiguous_duplicates=request.remove_ambiguous_duplicates)


def forecast_response(result, currency):
    return out.ForecastResponse(currency=currency, as_of=result.as_of, horizon_days=result.horizon_days,
                                current_balance_cents=result.current_balance_cents,
                                cash_threshold_cents=result.cash_threshold_cents,
                                history_days=result.history_days, history_rows=result.history_rows,
                                daily=result.daily.to_dict("records"),
                                events=[asdict(item) for item in result.events],
                                shortage_dates=result.shortage_dates, assumptions=result.assumptions,
                                warnings=result.warnings)


class AnalyticsService:
    """Stateless and request-scoped; never retain user histories or trained pipelines."""

    def __init__(self, metrics=None):
        self.metrics = metrics

    def measure(self, operation):
        return self.metrics.measure(operation) if self.metrics is not None else nullcontext()

    def validate(self, request):
        imported = import_transactions(request)
        ready = not imported.has_errors
        try:
            require_ready_import(imported, reviewed_duplicates=request.reviewed_duplicates)
        except ValueError:
            ready = False
        transactions = [{name: row[name] for name in TRANSACTION_COLUMNS}
                        for row in imported.data.to_dict("records")]
        return out.ValidationResponse(valid=not imported.has_errors, analytics_ready=ready,
                                      input_rows=imported.input_rows, duplicates_removed=imported.duplicates_removed,
                                      issues=[asdict(issue) for issue in imported.issues], transactions=transactions)

    def import_csv(self, request):
        from src.dashboard_wire import ImportWire
        return ImportWire.pack(validate_csv(request.csv_text,
                              remove_ambiguous_duplicates=request.remove_ambiguous_duplicates))

    def dashboard(self, request):
        from src.dashboard_wire import DashboardWire
        imported, _, cutoff = self.history(request)
        anomaly = self.anomalies(request)
        result = build_dashboard(imported, request.opening_balance, as_of=cutoff,
                                 cash_threshold=request.cash_threshold,
                                 include_irregular_income=request.include_irregular_income,
                                 reviewed_duplicates=request.reviewed_duplicates, anomalies=anomaly)
        return DashboardWire.pack(result)

    def scenario_wire(self, request):
        from src.dashboard_wire import ScenarioWire
        return ScenarioWire.pack(simulate_scenario(self.forecast(request), request.scenario))

    def history(self, request):
        imported = import_transactions(request)
        require_ready_import(imported, reviewed_duplicates=request.reviewed_duplicates)
        data, cutoff = transaction_snapshot(imported.data, request.as_of)
        if data.empty:
            raise ValueError("No history at cutoff")
        return imported, data, cutoff

    def summary(self, request):
        _, data, cutoff = self.history(request)
        return out.SummaryResponse(currency=request.currency, as_of=cutoff,
                                   metrics=asdict(calculate_metrics(data, request.opening_balance)),
                                   warnings=["Reconstructed estimates, not verified bank balances. Currency is a label only."])

    def forecast(self, request, history=None):
        _, data, cutoff = history or self.history(request)
        with self.measure("forecast"):
            return forecast_cash_flow(data, request.opening_balance, as_of=cutoff,
                                      horizon_days=request.horizon_days, cash_threshold=request.cash_threshold,
                                      include_irregular_income=request.include_irregular_income)

    def forecast_output(self, request):
        return forecast_response(self.forecast(request), request.currency)

    def anomalies(self, request, history=None):
        _, data, cutoff = history or self.history(request)
        with self.measure("anomaly"):
            return dashboard_anomalies(data, as_of=cutoff, engine=request.anomaly_engine)

    def anomaly_output(self, request):
        result = self.anomalies(request)
        columns = out.AnomalyRow.model_fields
        rows = []
        for record in result.data.to_dict("records"):
            rows.append({name: None if pd.isna(record.get(name)) else record[name] for name in columns})
        return out.AnomalyResponse(currency=request.currency, as_of=result.as_of, engine=request.anomaly_engine,
                                   scored_count=result.scored_count, anomaly_count=result.anomaly_count,
                                   unscored_count=len(result.data) - result.scored_count,
                                   transactions=rows, warnings=[*result.warnings,
                                     "Zero alerts does not establish zero risk. Flags are not confirmed fraud."])

    def risk(self, request):
        history = self.history(request)
        forecast = self.forecast(request, history)
        anomaly = self.anomalies(request, history)
        risk = assess_risk(history[1], forecast, anomalies=anomaly)
        return out.RiskResponse(currency=request.currency, as_of=forecast.as_of,
                               **asdict(risk), shortage_dates=forecast.shortage_dates)

    def scenario(self, request):
        baseline = self.forecast(request)
        scenario = simulate_scenario(baseline, request.scenario)
        return out.ScenarioResponse(baseline=forecast_response(baseline, request.currency),
                                    simulated=forecast_response(scenario.forecast, request.currency),
                                    comparison=asdict(compare_scenario(scenario)),
                                    deferred_events=[asdict(event) for event in scenario.deferred_events])

    def insights(self, request, llm):
        imported, _, cutoff = self.history(request)
        anomaly = self.anomalies(request)
        bundle = build_dashboard(imported, request.opening_balance, as_of=cutoff,
                                 cash_threshold=request.cash_threshold,
                                 include_irregular_income=request.include_irregular_income,
                                 reviewed_duplicates=request.reviewed_duplicates, anomalies=anomaly)
        scenario = simulate_scenario(bundle.forecast, request.scenario) if request.scenario else None
        report = generate_report(bundle, llm, request.currency, scenario=scenario)
        return out.InsightsResponse(**asdict(report))
