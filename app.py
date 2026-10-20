"""CashGuard AI dashboard. Run: python -m streamlit run app.py."""

import hashlib
import logging
from dataclasses import asdict
from uuid import uuid4

import pandas as pd
import streamlit as st

from config import SAMPLE_DATA_PATH
from src import data_processing
from src.dashboard_service import (ANOMALY_ENGINES, DashboardInputError, build_dashboard, dashboard_anomalies, display_transactions,
                                    require_ready_import, session_value)
from src.metrics import money_to_cents
from src.api_client import ApiClientError
from src.dashboard_backend import DashboardBackend
from src.settings import Settings
from src.ui import pages
from src.ui.components import apply_style, page_header
from src.ui.navigation import initialize, navigate, sidebar_navigation, explore_navigation
from src.ui.model_evaluation import render_model_evaluation

PAGES = ["Overview", "Transactions", "Cash Flow Forecast", "Anomaly Detection", "Risk Analysis",
         "Scenario Simulator", "AI Insights", "Model Evaluation", "Data quality"]
WALKTHROUGH = {
    "Overview": "Start with estimated cash, income and expenses. The opening balance is an explicit assumption, not a bank connection.",
    "Cash Flow Forecast": "Explore the next 30 days and change the minimum cash threshold. Read the assumptions before relying on a projection.",
    "Anomaly Detection": "Inspect coverage and explanations. This fictional history may have no alerts; zero alerts does not mean zero risk.",
    "Scenario Simulator": "Try a hypothetical emergency or income reduction. Compare the projected minimum cash with the unchanged baseline.",
    "AI Insights": "Check the configured model status, then request explanations if available. Deterministic mode intentionally makes no model call.",
    "Model Evaluation": "Review the synthetic benchmark and its limitations. Injected amount changes are not confirmed fraud labels.",
}


def _navigate(page):
    navigate(page)


def _begin_walkthrough():
    _start_demo()
    st.session_state["cashguard_walkthrough"] = True


def _end_walkthrough():
    st.session_state["cashguard_walkthrough"] = False


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
    navigate("Overview")
    for key in ("cashguard_private_cache", "cashguard_latest_scenario", "cashguard_scenario_controls", "cashguard_ai_report"):
        st.session_state.pop(key, None)


def main() -> None:
    st.set_page_config(page_title="CashGuard AI | Financial Analytics", page_icon="◈", layout="wide")
    apply_style()
    try:
        settings = Settings.from_environment()
    except ValueError:
        st.error("Application configuration is invalid. Check the configured backend settings.")
        return
    profile = (settings.deployment_profile, settings.public_demo, settings.execution_mode, settings.api_url,
               hashlib.sha256(settings.api_token.get_secret_value().encode()).hexdigest() if settings.api_token else None)
    if st.session_state.get("cashguard_runtime_profile", profile) != profile:
        st.session_state.clear()
    st.session_state["cashguard_runtime_profile"] = profile
    session_id = st.session_state.setdefault("cashguard_session_id", uuid4().hex)
    st.session_state.setdefault("cashguard_private_cache", {})
    backend = DashboardBackend(settings, session_id=session_id) if settings.execution_mode == "api" else None
    st.session_state.setdefault("cash_threshold", "500.00")
    initialize()
    with st.sidebar:
        st.title("CashGuard AI")
        st.caption("Make room for what comes next.")
        page = sidebar_navigation()
        st.divider()
        if settings.public_demo:
            source = "Synthetic demo"
            st.caption("Public synthetic demo · Real financial CSV uploads are disabled.")
        else:
            source = st.radio("Data source", ["Synthetic demo", "Upload CSV"], key="data_source")
        if source == "Synthetic demo":
            st.button("Start demo", key="start_demo", on_click=_start_demo, width="stretch")
            st.caption("Fictional opening cash: 2,500.00. Cash floor: 500.00.")
        uploaded = st.file_uploader("Transaction CSV", type=["csv"], key="transaction_upload",
                                    max_upload_size=max(1, settings.max_request_bytes // (1024 * 1024)) if backend else 10) if source == "Upload CSV" else None
        if source == "Upload CSV" and backend:
            st.caption("API mode accepts at most 2,000 transactions within its encoded request-size limit. Use direct local mode for larger private histories.")
        with st.expander("Cash settings", expanded=source == "Upload CSV"):
            currency = st.selectbox("Currency label (no conversion)", ["USD", "INR", "EUR", "GBP"], key="currency")
            opening = st.text_input("Opening balance", placeholder="e.g. 2500.00", key="opening_balance")
            st.caption("Cash immediately before the first transaction. Enter 0 explicitly to start at zero. This is your assumption, not a bank balance.")
            threshold = st.text_input("Minimum cash threshold", key="cash_threshold",
                                      help="Your cash floor: projections below this amount need attention.")
            remove_duplicates = st.checkbox("Remove identical rows without IDs", value=False, key="remove_duplicates",
                                             help="Identical purchases may be legitimate. Review repeated rows before removing them.")
        with st.expander("Review method"):
            anomaly_engine = st.selectbox("Anomaly review engine", ANOMALY_ENGINES, key="anomaly_engine",
                                           help="Advanced: change the review policy. All existing calibrated and legacy engines remain available.")
        if st.button("Clear session data", key="clear_session"):
            st.session_state.clear()
            st.query_params.clear()
            st.rerun()
        if source == "Synthetic demo":
            with st.expander("Guided synthetic walkthrough"):
                st.button("Start guided walkthrough", key="guided_start", on_click=_begin_walkthrough, width="stretch")
                for index, target in enumerate(WALKTHROUGH, 1):
                    st.button(f"{index}. {target}", key=f"guided_{index}", on_click=_navigate, args=(target,), width="stretch")
                st.caption("These controls navigate the existing pages. They do not connect to a bank or create model output.")
        st.caption("Synthetic only · No bank connection" if settings.public_demo else "No bank connection")
        st.caption("Display: switch Light / Dark in the app Settings menu.")
        with st.expander("About estimates and local AI"):
            st.write("CashGuard is a local budgeting research tool, not a bank, financial advisor or fraud detection service.")
            st.write("Balances are reconstructed estimates. Currency selection changes labels only. Use one currency per file.")
            st.write("API mode uses the configured backend provider. Its status and any hosted processing are disclosed on AI Insights; only minimized aggregates reach inference."
                     if backend else "Raw transactions stay in your session. Clicking Generate AI Insights sends only aggregate evidence to local Ollama; no cloud model is used.")

    page_header(page)
    explore_navigation(page)
    if source == "Upload CSV":
        st.session_state["cashguard_walkthrough"] = False
    if st.session_state.get("cashguard_walkthrough"):
        st.info(WALKTHROUGH.get(page, "Use the sidebar to explore the synthetic workspace."))
        st.button("Exit walkthrough", key="guided_exit", on_click=_end_walkthrough)
    if source == "Synthetic demo" and not opening.strip() and page == "Overview":
        with st.container(border=True):
            st.header("Explore cash flow with fictional transactions")
            st.write("Load the sample, inspect a conditional forecast and test an emergency expense. No financial upload or bank account is needed.")
            st.button("Launch synthetic walkthrough", key="landing_demo", on_click=_begin_walkthrough, type="primary")
            st.caption("The sample uses explicitly assumed opening cash. This research prototype does not provide financial advice or fraud decisions.")
        st.warning("Enter an opening balance in Cash settings, or select Start demo to use fictional cash.")
        return
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
    _select_source((source, fingerprint, settings.execution_mode, settings.api_url))
    import_key = (fingerprint, remove_duplicates, settings.execution_mode, settings.api_url)
    try:
        with st.spinner("Validating transaction history…"):
            imported = session_value(st.session_state, "import", import_key,
                                      lambda: backend.import_csv(raw, remove_duplicates) if backend else
                                      data_processing.validate_csv(raw, remove_ambiguous_duplicates=remove_duplicates))
    except ApiClientError as exc:
        st.error(str(exc))
        st.info("No partial results are displayed. Retry when the configured API is available.")
        return
    if source != "Synthetic demo":
        st.caption("Private session · No CSV is saved to a financial database. Verify opening cash and currency when replacing a file.")
    if imported.issues:
        with st.expander(f"Validation report · {len(imported.issues)} finding(s)", expanded=imported.has_errors or page == "Data quality"):
            st.dataframe(pd.DataFrame(asdict(issue) for issue in imported.issues), hide_index=True, width="stretch")
    if imported.has_errors:
        st.error("Import has errors. Correct the source CSV and upload again. Financial summaries are blocked to avoid incomplete totals.")
        if not imported.data.empty:
            st.header("Valid rows for review only")
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
    with st.sidebar.expander("Analysis settings"):
        as_of = st.date_input("Analysis date", last, min_value=first, max_value=last,
                                  key=f"analysis_date_{dataset_key}",
                                  help="Metrics and analytics include transactions through this date. It is not necessarily today's bank balance.")
        irregular = st.checkbox("Include averaged irregular income", value=False, key="irregular_income",
                                     help="Adds an uncertain historical income baseline. It does not create a scheduled client payment.")
    st.caption(f"{'Sample data' if source == 'Synthetic demo' else 'Your data'} · {currency} · Through {as_of:%d %b %Y} · Balances are estimates, not verified bank balances.")
    with st.expander("Data and assumptions"):
        st.write(f"{imported.input_rows:,} input rows · {len(imported.data):,} valid rows · {imported.duplicates_removed:,} duplicates removed.")
        st.write(f"History: {first} to {last}. Analysis includes transactions through {as_of}. Currency labels do not convert amounts.")
        st.write(f"Opening cash applies immediately before {first}. The cash floor is your minimum cash threshold.")
        st.caption("Fictional transactions, not a bank connection." if source == "Synthetic demo" else
                   "API mode sends validated transactions to the configured backend; inference receives minimized aggregates." if backend else
                   "Direct local mode keeps transactions in this session. Optional local inference receives minimized aggregates.")
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
        if settings.public_demo:
            from src.ui.model_evaluation import render_public_evaluation
            render_public_evaluation()
        else:
            render_model_evaluation(imported, opening, as_of, irregular, import_key, source)
        return
    if page == "Anomaly Detection":
        try:
            with st.spinner("Comparing transactions with strictly earlier history…"):
                result = session_value(st.session_state, "anomalies", anomaly_key,
                                        lambda: backend.anomalies(imported, as_of=as_of, engine=anomaly_engine, currency=currency, reviewed=reviewed)
                                        if backend else dashboard_anomalies(imported.data, as_of=as_of, engine=anomaly_engine))
        except ApiClientError as exc:
            st.error(str(exc))
            return
        pages.render_anomalies(result, currency, dataset_key)
        return
    if not opening.strip():
        st.header("Get started with your cash-flow workspace")
        st.write("1. Choose Synthetic demo or upload a transaction CSV in the sidebar.\n"
                 "2. Enter the cash balance immediately before the earliest transaction, or click Start demo for a clearly fictional starting point.\n"
                 "3. Explore the forecast, review indicators and try a scenario. Local AI is optional.")
        st.caption("On a narrow screen, open the sidebar using the menu button at the top left. Transactions, Anomaly Detection and Model Evaluation can be explored before entering an opening balance.")
        st.warning("Enter an opening balance in the sidebar to calculate estimated balances. Enter 0 if you intentionally want a zero starting point.")
        st.header("Imported transaction preview")
        st.dataframe(display_transactions(imported.data.head(20)), hide_index=True, width="stretch")
        return
    try:
        opening_cents, threshold_cents = money_to_cents(opening), money_to_cents(threshold)
        baseline_key = (*import_key, as_of, opening_cents, threshold_cents, irregular, reviewed, anomaly_engine, "phase6-v1")
        with st.spinner("Calculating financial analytics…"):
            if backend and page in {"Overview", "Cash Flow Forecast", "Risk Analysis", "Scenario Simulator", "AI Insights"}:
                payload = backend.payload(imported, opening, as_of=as_of, threshold=threshold,
                                          irregular=irregular, reviewed=reviewed, engine=anomaly_engine, currency=currency)
                bundle = session_value(st.session_state, "dashboard_api", baseline_key,
                                       lambda: backend.dashboard(payload))
            else:
                anomaly = session_value(st.session_state, "anomalies", anomaly_key,
                                     lambda: dashboard_anomalies(imported.data, as_of=as_of, engine=anomaly_engine))
                bundle = session_value(st.session_state, "dashboard", baseline_key,
                                    lambda: build_dashboard(imported, opening, as_of=as_of, cash_threshold=threshold,
                                                            include_irregular_income=irregular,
                                                            reviewed_duplicates=reviewed, anomalies=anomaly))
    except ApiClientError as exc:
        st.error(str(exc))
        st.info("No partial results are displayed. Retry when the configured API is available.")
        return
    except (ValueError, OverflowError) as exc:
        st.error(str(exc))
        return
    if page == "Overview":
        pages.render_overview(bundle, currency)
    elif page == "Cash Flow Forecast":
        pages.render_forecast(bundle, currency)
    elif page == "Risk Analysis":
        pages.render_risk(bundle, currency)
    elif page == "Scenario Simulator":
        if backend:
            pages.render_scenarios(bundle, currency, baseline_key, backend=backend, payload=payload)
        else:
            pages.render_scenarios(bundle, currency, baseline_key)
    elif page == "AI Insights":
        if backend:
            pages.render_insights(bundle, currency, baseline_key, backend=backend, payload=payload)
        else:
            pages.render_insights(bundle, currency, baseline_key)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    main()
