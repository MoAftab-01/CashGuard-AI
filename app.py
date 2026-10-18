"""CashGuard AI dashboard. Run: python -m streamlit run app.py."""

import hashlib
import logging
from dataclasses import asdict

import pandas as pd
import streamlit as st

from config import SAMPLE_DATA_PATH
from src import data_processing
from src.dashboard_service import (ANOMALY_ENGINES, DashboardInputError, build_dashboard, dashboard_anomalies, display_transactions,
                                    require_ready_import, session_value)
from src.metrics import money_to_cents
from src.ui import pages
from src.ui.components import apply_style, page_header
from src.ui.model_evaluation import render_model_evaluation

PAGES = ["Overview", "Transactions", "Cash Flow Forecast", "Anomaly Detection", "Risk Analysis",
         "Scenario Simulator", "AI Insights", "Model Evaluation", "Data quality"]


@st.cache_data(max_entries=2, show_spinner=False)
def _public_demo_bytes(modified_ns: int) -> bytes:
    """The ONLY shared cache contains the bundled fictional CSV, never uploads."""
    return SAMPLE_DATA_PATH.read_bytes()


def _select_source(identity: tuple) -> None:
    if st.session_state.get("cashguard_source") != identity:
        st.session_state.pop("cashguard_private_cache", None)
        st.session_state.pop("cashguard_latest_scenario", None)
        st.session_state.pop("cashguard_scenario_controls", None)
        st.session_state.pop("cashguard_ai_report", None)
        # Keep filters across navigation, but release filters from a replaced file.
        fixed = {"transaction_search", "transaction_direction", "anomaly_status", "anomaly_search",
                 "anomaly_minimum", "anomaly_severity", "anomaly_recurring"}
        prefixes = ("transaction_dates_", "transaction_categories_", "anomaly_categories_", "anomaly_comparison_")
        for key in list(st.session_state):
            if key in fixed or key.startswith(prefixes):
                st.session_state.pop(key, None)
        st.session_state["cashguard_source"] = identity


def _start_demo() -> None:
    """Explicit fictional starting assumption; never infer an uploaded bank balance."""
    st.session_state.update(opening_balance="2500.00", cash_threshold="500.00", currency="USD",
                            irregular_income=False, anomaly_engine=ANOMALY_ENGINES[0], navigation="Overview")
    for key in ("cashguard_private_cache", "cashguard_latest_scenario", "cashguard_scenario_controls", "cashguard_ai_report"):
        st.session_state.pop(key, None)


def main() -> None:
    st.set_page_config(page_title="CashGuard AI | Financial Analytics", page_icon="◈", layout="wide")
    apply_style()
    st.session_state.setdefault("cash_threshold", "500.00")
    with st.sidebar:
        st.title("CashGuard AI")
        st.caption("FINANCIAL RISK & CASH FLOW")
        page = st.radio("Navigation", PAGES, key="navigation")
        st.divider()
        st.subheader("Data workspace")
        source = st.radio("Data source", ["Synthetic demo", "Upload CSV"], key="data_source")
        if source == "Synthetic demo":
            st.button("Start demo", key="start_demo", on_click=_start_demo, width="stretch")
            st.caption("Sets fictional opening cash to 2,500.00 and the minimum threshold to 500.00. No bank balance is assumed.")
        uploaded = st.file_uploader("Transaction CSV", type=["csv"], key="transaction_upload") if source == "Upload CSV" else None
        currency = st.selectbox("Currency label (no conversion)", ["USD", "INR", "EUR", "GBP"], key="currency")
        opening = st.text_input("Opening balance", placeholder="e.g. 2500.00", key="opening_balance")
        st.caption("Immediately before the first imported transaction. Enter 0 explicitly for a zero starting point. Use a single currency.")
        threshold = st.text_input("Minimum cash threshold", key="cash_threshold")
        remove_duplicates = st.checkbox("Remove identical rows without IDs", value=False, key="remove_duplicates",
                                         help="Identical purchases may be legitimate. Review repeated rows before removing them.")
        anomaly_engine = st.selectbox("Anomaly review engine", ANOMALY_ENGINES, key="anomaly_engine",
                                       help="Calibrated amount review uses the interpretable family selected on separate synthetic calibration data. Legacy scores remain available.")
        if st.button("Clear session data", key="clear_session"):
            st.session_state.clear()
            st.rerun()
        st.caption("Local processing · No bank connection")
        st.caption("Display: switch Light / Dark in the app Settings menu.")
        with st.expander("About estimates and local AI"):
            st.write("CashGuard is a local budgeting research tool, not a bank, financial advisor or fraud detection service.")
            st.write("Balances are reconstructed estimates. Currency selection changes labels only. Use one currency per file.")
            st.write("Raw transactions stay in your session. Clicking Generate AI Insights sends only aggregate evidence to local Ollama; no cloud model is used.")

    page_header(page)
    if source == "Upload CSV" and uploaded is None:
        _select_source((source, None))
        st.info("Upload a UTF-8 CSV with date, description, amount and category columns using the sidebar.")
        st.code("date,description,amount,category\n2026-01-01,Salary,4200.00,Income\n2026-01-03,Rent,-1400.00,Housing", language="csv")
        st.caption("Dates must use YYYY-MM-DD. Positive amounts are income; negative amounts are expenses. Optional: transaction_id, account, merchant.")
        st.download_button("Download CSV template", b"date,description,amount,category,transaction_id\n2026-01-01,Fictional income,1000.00,Income,EXAMPLE-1\n2026-01-03,Fictional expense,-125.50,Other,EXAMPLE-2\n",
                            file_name="cashguard_example.csv", mime="text/csv", on_click="ignore")
        st.caption("Use UTF-8, signed amounts with up to two decimals, and no currency symbols or thousands separators. Any invalid row blocks totals until corrected.")
        return
    try:
        raw = uploaded.getvalue() if uploaded is not None else _public_demo_bytes(SAMPLE_DATA_PATH.stat().st_mtime_ns)
    except OSError:
        st.error("Sample CSV is missing or unreadable. Run: python scripts/generate_sample_data.py")
        return
    fingerprint = hashlib.sha256(raw).hexdigest()
    _select_source((source, fingerprint))
    import_key = (fingerprint, remove_duplicates)
    imported = session_value(st.session_state, "import", import_key,
                              lambda: data_processing.validate_csv(raw, remove_ambiguous_duplicates=remove_duplicates))
    if source == "Synthetic demo":
        st.caption("SYNTHETIC DEMO · Fictional financial activity in illustrative currency units. No conversion is applied.")
    else:
        st.caption("PRIVATE SESSION · Raw transactions stay in this session's memory and are not saved to a database. Only aggregate evidence is sent to local Ollama when you explicitly generate AI insights. When replacing a file, verify the opening balance and currency again.")
    st.caption(f"{imported.input_rows:,} input rows · {len(imported.data):,} valid preview rows · {imported.duplicates_removed:,} duplicates removed")
    if imported.issues:
        with st.expander(f"Validation report · {len(imported.issues)} finding(s)", expanded=imported.has_errors or page == "Data quality"):
            st.dataframe(pd.DataFrame(asdict(issue) for issue in imported.issues), hide_index=True, width="stretch")
    if imported.has_errors:
        st.error("Import has errors. Correct the source CSV and upload again. Financial summaries are blocked to avoid incomplete totals.")
        if not imported.data.empty:
            st.subheader("Valid rows for review only")
            st.dataframe(display_transactions(imported.data), hide_index=True, width="stretch")
        return
    if imported.data.empty:
        st.info("No transactions are available. Upload a nonempty CSV or select the synthetic demo.")
        return
    ambiguous = any(issue.field == "duplicate" and "kept" in issue.message.lower() for issue in imported.issues)
    reviewed = False
    if ambiguous:
        st.warning("Possible duplicate rows were retained for review. Analytics will wait for a duplicate decision in the sidebar.")
        reviewed = st.sidebar.checkbox("I reviewed repeated rows; keep them as separate transactions", value=False,
                                        key=f"reviewed_duplicates_{fingerprint}")
    elif imported.issues:
        st.warning("Review the validation report before relying on these estimates.")
    dataset_key = fingerprint[:16]
    first, last = imported.data["date"].min(), imported.data["date"].max()
    as_of = st.sidebar.date_input("Analysis date", last, min_value=first, max_value=last,
                                  key=f"analysis_date_{dataset_key}",
                                  help="Metrics and analytics include transactions through this date. It is not necessarily today's bank balance.")
    irregular = st.sidebar.checkbox("Include averaged irregular income", value=False, key="irregular_income",
                                     help="Adds an uncertain historical income baseline. It does not create a scheduled client payment.")
    st.caption(f"Imported history: {first} → {last} · Analytics cutoff: {as_of} · Currency: {currency}")
    if page == "Transactions":
        pages.render_transactions(imported, dataset_key)
        return
    if page == "Data quality":
        pages.render_quality(imported)
        return
    try:
        require_ready_import(imported, reviewed_duplicates=reviewed)
    except DashboardInputError as exc:
        st.warning(str(exc))
        return
    anomaly_key = (*import_key, as_of, anomaly_engine, "phase6-v1")
    if page == "Model Evaluation":
        render_model_evaluation(imported, opening, as_of, irregular, import_key, source)
        return
    if page == "Anomaly Detection":
        with st.spinner("Comparing transactions with strictly earlier history…"):
            result = session_value(st.session_state, "anomalies", anomaly_key,
                                    lambda: dashboard_anomalies(imported.data, as_of=as_of, engine=anomaly_engine))
        pages.render_anomalies(result, currency, dataset_key)
        return
    if not opening.strip():
        st.subheader("Get started with your cash-flow workspace")
        st.write("1. Choose Synthetic demo or upload a transaction CSV in the sidebar.\n"
                 "2. Enter the cash balance immediately before the earliest transaction, or click Start demo for a clearly fictional starting point.\n"
                 "3. Explore the forecast, review indicators and try a scenario. Local AI is optional.")
        st.caption("On a narrow screen, open the sidebar using the menu button at the top left. Transactions, Anomaly Detection and Model Evaluation can be explored before entering an opening balance.")
        st.warning("Enter an opening balance in the sidebar to calculate estimated balances. Enter 0 if you intentionally want a zero starting point.")
        st.subheader("Imported transaction preview")
        st.dataframe(display_transactions(imported.data.head(20)), hide_index=True, width="stretch")
        return
    try:
        opening_cents, threshold_cents = money_to_cents(opening), money_to_cents(threshold)
        baseline_key = (*import_key, as_of, opening_cents, threshold_cents, irregular, reviewed, anomaly_engine, "phase6-v1")
        with st.spinner("Calculating financial analytics…"):
            anomaly = session_value(st.session_state, "anomalies", anomaly_key,
                                     lambda: dashboard_anomalies(imported.data, as_of=as_of, engine=anomaly_engine))
            bundle = session_value(st.session_state, "dashboard", baseline_key,
                                    lambda: build_dashboard(imported, opening, as_of=as_of, cash_threshold=threshold,
                                                            include_irregular_income=irregular,
                                                            reviewed_duplicates=reviewed, anomalies=anomaly))
    except (ValueError, OverflowError) as exc:
        st.error(str(exc))
        return
    st.caption(f"Opening balance applies immediately before {first}. All balances are reconstructed estimates, not actual verified bank balances.")
    if page == "Overview":
        pages.render_overview(bundle, currency)
    elif page == "Cash Flow Forecast":
        pages.render_forecast(bundle, currency)
    elif page == "Risk Analysis":
        pages.render_risk(bundle, currency)
    elif page == "Scenario Simulator":
        pages.render_scenarios(bundle, currency, baseline_key)
    elif page == "AI Insights":
        pages.render_insights(bundle, currency, baseline_key)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    main()
