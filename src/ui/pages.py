"""Dashboard pages. These render engine outputs and delegate all scenario calculations."""

from __future__ import annotations

from decimal import Decimal

import pandas as pd
import streamlit as st
from pydantic import ValidationError

from src.anomaly_detection import AnomalyResult
from src.dashboard_service import (DashboardBundle, compare_scenario,
                                    display_transactions, export_transactions, filter_transactions,
                                    format_cents, session_value)
from src.data_processing import ImportResult
from src.explainability import anomaly_comparisons, ranked_risk_factors, threshold_breaches
from src.scenario_simulator import ScenarioConfig, simulate_scenario
from src.ui.components import chart, overview_metrics, risk_status, warnings_panel
from src.ui.ai_insights import render_ai_insights
from src.visualizations import (anomaly_timeline, forecast_comparison, monthly_comparison,
                                risk_contributions, spending_distribution)


def render_overview(bundle: DashboardBundle, currency: str) -> None:
    overview_metrics(bundle, currency)
    left, right = st.columns([1, 1])
    with left, st.container(border=True):
        st.subheader("Risk at a glance")
        risk_status(bundle.risk)
    with right, st.container(border=True):
        st.subheader("30-day outlook")
        forecast = bundle.forecast
        st.write(f"Projected closing cash: **{format_cents(int(forecast.daily.iloc[-1]['balance_cents']), currency)}**")
        st.write(f"Minimum projected cash: **{format_cents(int(forecast.daily['balance_cents'].min()), currency)}**")
        st.caption(f"{len(forecast.shortage_dates)} days below your minimum threshold. Projections are estimates.")
    left, right = st.columns([1.2, 1])
    with left:
        chart(monthly_comparison(bundle.data), "overview_monthly")
    with right:
        chart(spending_distribution(bundle.data), "overview_categories")
    st.caption(f"Charts use {currency}. Observed transactions only; partial months are not extrapolated.")
    st.subheader("Recent financial activity")
    st.dataframe(display_transactions(bundle.data.sort_values("date", ascending=False, kind="stable").head(10)),
                 hide_index=True, width="stretch")


def render_transactions(imported: ImportResult, dataset_key: str) -> None:
    data = imported.data
    st.caption("Filters affect this table and its download. Overview, forecasts and risk use all transactions through the sidebar analysis date.")
    left, right = st.columns([1.2, 1])
    with left:
        dates = st.date_input("Transaction date range", (data["date"].min(), data["date"].max()),
                              min_value=data["date"].min(), max_value=data["date"].max(),
                              key=f"transaction_dates_{dataset_key}", persist_state="session")
        selected = st.multiselect("Category filter", sorted(data["category"].unique()), key=f"transaction_categories_{dataset_key}", persist_state="session")
    with right:
        search = st.text_input("Search description", placeholder="Search any part of a description", key="transaction_search", persist_state="session")
        direction = st.selectbox("Direction", ["All", "Income", "Expenses"], key="transaction_direction", persist_state="session")
    if len(dates) != 2:
        st.info("Choose both a start date and an end date to filter transactions.")
        return
    shown = filter_transactions(data, start_date=dates[0], end_date=dates[1], categories=selected,
                                search=search, direction=direction)
    st.subheader(f"Transactions · {len(shown):,}")
    if shown.empty:
        st.info("No transactions match these filters. Widen the date range or clear a filter.")
    st.dataframe(display_transactions(shown.sort_values("date", ascending=False, kind="stable")), hide_index=True, width="stretch")
    st.download_button("Download filtered CSV", export_transactions(shown), file_name="cashguard_filtered_transactions.csv",
                        mime="text/csv", disabled=shown.empty, on_click="ignore")
    st.caption("Amounts retain two-decimal precision. Spreadsheet formulas in text fields are exported as plain text.")


def render_forecast(bundle: DashboardBundle, currency: str) -> None:
    forecast = bundle.forecast
    columns = st.columns(3)
    columns[0].metric("Estimated balance at cutoff", format_cents(forecast.current_balance_cents, currency))
    columns[1].metric("Projected closing balance", format_cents(int(forecast.daily.iloc[-1]["balance_cents"]), currency))
    columns[2].metric("Days below threshold", len(forecast.shortage_dates))
    chart(forecast_comparison(bundle.balance_history, forecast, currency=currency), "cash_forecast")
    st.caption("Historical balances and projections are estimates. The dashed line is the 30-day baseline; the dotted line is your minimum cash threshold.")
    _show_breaches(forecast, currency)
    warnings_panel(forecast.warnings)
    with st.expander("Forecast assumptions and supporting patterns"):
        for assumption in forecast.assumptions:
            st.write(f"• {assumption}")
        if forecast.recurring_patterns:
            rows = [{"Description": pattern.key[1], "Cadence": pattern.cadence,
                     "Projected amount": format_cents(pattern.amount_cents, currency),
                     "Evidence count": pattern.occurrences, "Last observed": pattern.last_date}
                    for pattern in forecast.recurring_patterns]
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        else:
            st.info("No recurring patterns have enough supporting evidence. The forecast uses the documented residual baseline.")
    with st.expander("Daily projection"):
        st.dataframe(_projection_table(forecast.daily), hide_index=True, width="stretch")


def render_anomalies(result: AnomalyResult, currency: str, dataset_key: str) -> None:
    left, middle, right = st.columns(3)
    left.metric("Flagged unusual", result.anomaly_count)
    middle.metric("Transactions scored", result.scored_count)
    right.metric("Warmup / unscored", len(result.data) - result.scored_count)
    st.info("Unusual transactions are not confirmed fraud. Higher scores indicate more unusual activity within the selected engine; score ranges differ by engine. Calibration percentiles are ranks, not probabilities.")
    if result.anomaly_count == 0:
        st.caption("No alerts were produced under this review policy. Zero alerts does not mean zero financial risk; unscored history, calibration and model limitations still matter.")
    if result.scored_count < len(result.data):
        st.warning("Some transactions lack sufficient earlier history and remain unscored. They have not been assessed as normal.")
    chart(anomaly_timeline(result.data, currency), "anomaly_timeline")
    left, right = st.columns(2)
    with left:
        status = st.selectbox("Review status", ["Flagged unusual", "All scored", "Not flagged", "Unscored", "All transactions"], key="anomaly_status", persist_state="session")
        categories = st.multiselect("Review categories", sorted(result.data["category"].unique()), key=f"anomaly_categories_{dataset_key}", persist_state="session")
    with right:
        search = st.text_input("Review description", key="anomaly_search", persist_state="session")
        minimum = st.number_input("Minimum absolute amount", min_value=0.0, value=0.0, step=10.0, key="anomaly_minimum", persist_state="session")
    shown = filter_transactions(result.data, categories=categories, search=search)
    flags = shown["is_anomaly"]
    if status == "Flagged unusual":
        shown = shown.loc[flags.fillna(False)]
    elif status == "All scored":
        shown = shown.loc[flags.notna()]
    elif status == "Not flagged":
        shown = shown.loc[flags.eq(False).fillna(False)]
    elif status == "Unscored":
        shown = shown.loc[flags.isna()]
    shown = shown.loc[shown["amount_cents"].abs() >= Decimal(str(minimum)) * 100]
    if "severity" in shown:
        severity = st.multiselect("Review severity", ["Informational", "Review recommended", "High priority", "Not scored"], key="anomaly_severity", persist_state="session")
        recurring = st.selectbox("Recurring context", ["All contexts", "Expected recurring date", "No supported recurring date"], key="anomaly_recurring", persist_state="session")
        if severity:
            shown = shown.loc[shown["severity"].isin(severity)]
        if recurring != "All contexts":
            expected = shown["recurring_expected"]
            shown = shown.loc[expected.eq(recurring == "Expected recurring date").fillna(False)]
        st.caption("Informational: no alert. Review recommended: score exceeds its calibrated threshold. "
                   "High priority: alert plus calibration rank at least 99% and amount/reference at least 3. "
                   "Unscored rows remain unassessed. Recurring payments still receive amount checks.")
    columns = ["date", "description", "amount", "category", "anomaly_score", "is_anomaly", "explanation", "training_end"]
    if "severity" in shown:
        columns += ["severity", "calibrated_percentile", "decision_threshold", "recurring_expected", "calibration_end"]
    st.subheader(f"Investigation queue · {len(shown)}")
    if shown.empty:
        st.info("No transactions match this review. Try another status or clear the filters.")
    st.dataframe(display_transactions(shown)[columns], hide_index=True, width="stretch",
                 column_config={"anomaly_score": st.column_config.NumberColumn("Anomaly score", format="%.4f"),
                                "explanation": st.column_config.TextColumn("Historical feature comparison", width="large")})
    assessed = shown.loc[shown["is_anomaly"].notna()]
    if not assessed.empty:
        with st.expander("Compare a reviewed transaction with its training history"):
            selected = st.selectbox("Transaction to compare", assessed.index.tolist(),
                                    format_func=lambda index: f"{assessed.loc[index, 'date']} | {assessed.loc[index, 'description']}",
                                    key=f"anomaly_comparison_{dataset_key}")
            row = assessed.loc[selected]
            st.write(f"Reference: {row['reference_scope']} | {row['reference_count']} training examples | "
                     f"Median: {currency} {Decimal(str(row['reference_cents'])) / 100:,.3f} | Amount / median: {row['amount_ratio']:.2f}")
            comparisons = anomaly_comparisons(result.data, row)
            st.dataframe(display_transactions(comparisons)[["date", "description", "category", "amount"]],
                         hide_index=True, width="stretch")
            st.caption("Nearest historical absolute amounts from the reference population, strictly before the scored date. "
                       "The median uses the full training population. These comparisons explain differences, not exact model attribution.")
    warnings_panel(result.warnings, "Model coverage and limitations")


def render_risk(bundle: DashboardBundle, currency: str) -> None:
    risk_status(bundle.risk)
    factors = {factor.name: factor for factor in bundle.risk.factors}
    left, middle, right = st.columns(3)
    buffer = factors["low_cash_buffer"].observed_value
    ratio = factors["expense_to_income"].observed_value
    left.metric("Current cash buffer", f"{buffer:.1f} days" if buffer is not None else "Unavailable")
    middle.metric("Expense-to-income ratio", f"{ratio:.1%}" if ratio is not None else "Unavailable")
    right.metric("Forecast threshold breaches", len(bundle.forecast.shortage_dates))
    st.caption("Buffer and expense/income comparisons use the risk engine's historical window. Missing denominators are shown as unavailable.")
    chart(risk_contributions(bundle.risk), "risk_contributions")
    st.subheader("Strongest risk contributions first")
    for factor in ranked_risk_factors(bundle.risk):
        with st.container(border=True):
            st.markdown(f"**{factor.name.replace('_', ' ').title()} · {factor.points}/{factor.max_points} points**")
            if not factor.evaluated:
                st.warning("Not assessed. A zero contribution does not establish normal activity.")
            st.write(factor.explanation)
    _show_breaches(bundle.forecast, currency)
    warnings_panel(bundle.risk.warnings)


def render_scenarios(bundle: DashboardBundle, currency: str, baseline_key: tuple) -> None:
    baseline = bundle.forecast
    # Widget state is cleaned when a page is hidden; preserve the user's scenario
    # separately so navigating to Insights and back does not reset their inputs.
    saved = st.session_state.get("cashguard_scenario_controls", {})
    first_date, last_date = baseline.daily.iloc[0]["date"], baseline.daily.iloc[-1]["date"]
    saved_date = saved.get("emergency_date", first_date)
    if not first_date <= saved_date <= last_date:
        saved_date = first_date
    left, right = st.columns(2)
    with left:
        income = st.slider("Income reduction (%)", 0, 100, saved.get("income", 0), 5, key="scenario_income")
        expenses = st.slider("Expense increase (%)", 0, 200, saved.get("expenses", 0), 5, key="scenario_expenses")
        emergency = st.text_input("Emergency expense", value=saved.get("emergency", "0.00"), key="scenario_emergency")
        emergency_date = st.date_input("Emergency date", saved_date,
                                       min_value=first_date, max_value=last_date,
                                       key=f"emergency_date_{baseline.as_of}")
    with right:
        payments = {event.event_id: event for event in baseline.events if event.kind == "recurring" and event.amount_cents > 0}
        payment_options = [None, *payments]
        saved_payment = saved.get("payment") if saved.get("payment") in payments else None
        selected = st.selectbox("Expected payment to delay", payment_options, index=payment_options.index(saved_payment),
                                 format_func=lambda key: "No payment delay" if key is None else f"{payments[key].date} · {payments[key].description} · {format_cents(payments[key].amount_cents, currency)}",
                                 key=f"scenario_payment_{baseline_key[0]}_{baseline.as_of}", disabled=not payments)
        delay = st.number_input("Payment delay (days)", min_value=0, max_value=365, value=saved.get("delay", 0), step=1,
                                 key="scenario_delay", disabled=selected is None)
        if not payments:
            st.info("No supported recurring inflow is projected. Payment delay is unavailable until a recurring payment has enough evidence.")
        st.caption("Income and expense changes apply to future baseline events. The emergency uses the exact amount entered. Historical balances stay fixed.")
    st.session_state["cashguard_scenario_controls"] = {"income": income, "expenses": expenses,
                                                       "emergency": emergency, "emergency_date": emergency_date,
                                                       "payment": selected, "delay": int(delay)}
    try:
        config = ScenarioConfig(income_decrease_pct=income, expense_increase_pct=expenses,
                                 emergency_expense=emergency, emergency_date=emergency_date,
                                 delayed_event_id=selected if delay > 0 else None,
                                 delay_days=int(delay) if selected is not None else 0)
        result = session_value(st.session_state, "scenario", (baseline_key, config.model_dump_json()),
                                lambda: simulate_scenario(baseline, config))
    except (ValidationError, ValueError) as exc:
        st.session_state.pop("cashguard_latest_scenario", None)
        message = "; ".join(item["msg"] for item in exc.errors(include_input=False)) if isinstance(exc, ValidationError) else str(exc)
        st.error(f"Check the scenario inputs: {message}")
        return
    st.session_state["cashguard_latest_scenario"] = (baseline_key, result)
    comparison = compare_scenario(result)
    columns = st.columns(4)
    columns[0].metric("Baseline minimum cash", format_cents(comparison.baseline_minimum_cents, currency))
    columns[1].metric("Scenario minimum cash", format_cents(comparison.scenario_minimum_cents, currency),
                       delta=f"{Decimal(comparison.scenario_minimum_cents - comparison.baseline_minimum_cents) / 100:,.2f} {currency}")
    columns[2].metric("Closing balance change", format_cents(comparison.closing_change_cents, currency))
    columns[3].metric("Scenario breach days", len(result.forecast.shortage_dates),
                       delta=len(comparison.additional_breach_dates) - len(comparison.resolved_breach_dates), delta_color="inverse")
    chart(forecast_comparison(bundle.balance_history, baseline, scenario=result.forecast, currency=currency), "scenario_comparison")
    st.caption("Scenario values are hypothetical. The minimum cash threshold is the same in both projections.")
    st.write(f"Additional below-threshold dates: {len(comparison.additional_breach_dates)} · Resolved dates: {len(comparison.resolved_breach_dates)}")
    if comparison.additional_breach_dates:
        st.dataframe(pd.DataFrame({"New threshold breach date": comparison.additional_breach_dates}), hide_index=True, width="stretch")
    if result.deferred_events:
        st.warning("A delayed payment moves beyond the 30-day horizon. It is excluded from projected inflows and retained below.")
        st.dataframe(pd.DataFrame({"Payment": event.description, "Deferred date": event.date,
                                   "Amount": format_cents(event.amount_cents, currency)} for event in result.deferred_events), hide_index=True, width="stretch")
    warnings_panel(result.forecast.warnings, "Scenario assumptions and limitations")


def render_insights(bundle: DashboardBundle, currency: str, baseline_key: tuple) -> None:
    render_ai_insights(bundle, currency, baseline_key)


def render_quality(imported: ImportResult) -> None:
    if not imported.issues:
        st.success("All rows passed validation. No duplicate records were found.")
    st.write("Dates use YYYY-MM-DD. Positive amounts are income; negative amounts are expenses. Categories and surrounding whitespace are normalized; identifiers remain text.")
    st.write("Conflicting account/ID records block summaries. Repeated ID-less rows require a removal decision or explicit confirmation before analytics. Extra columns are ignored with a warning.")
    st.subheader("Imported transaction preview")
    st.dataframe(display_transactions(imported.data.head(20)), hide_index=True, width="stretch")


def _show_breaches(forecast, currency: str) -> None:
    if forecast.shortage_dates:
        st.warning(f"{len(forecast.shortage_dates)} projected dates fall below {format_cents(forecast.cash_threshold_cents, currency)}; the first is {forecast.shortage_dates[0]}.")
        breaches = threshold_breaches(forecast)
        for column in ("previous_balance_cents", "gap_to_threshold_cents"):
            breaches[column.removesuffix("_cents")] = breaches[column].map(lambda value: format_cents(int(value), currency))
        breaches = breaches.drop(columns=["previous_balance_cents", "gap_to_threshold_cents"])
        st.dataframe(_projection_table(breaches), hide_index=True, width="stretch")
        st.caption("Previous estimated cash + projected inflows - projected outflows = estimated closing cash. "
                   "A breach can persist on a day without an outflow. Gap is measured against your configured threshold, not necessarily zero.")
    else:
        st.success("No projected dates fall below the configured minimum cash threshold.")


def _projection_table(data: pd.DataFrame) -> pd.DataFrame:
    frame = data.copy()
    for column in ("inflow_cents", "outflow_cents", "net_cents", "balance_cents"):
        frame[column.removesuffix("_cents")] = frame[column].map(lambda value: f"{Decimal(int(value)) / 100:.2f}")
    return frame.drop(columns=["inflow_cents", "outflow_cents", "net_cents", "balance_cents"])
