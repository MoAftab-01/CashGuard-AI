"""Shared native Streamlit components and static, theme-compatible styling."""

from decimal import Decimal

import streamlit as st

from src.dashboard_service import DashboardBundle, format_money
from src.risk_engine import RiskResult
from src.ui.navigation import VIEWS
from src.ui.chart_data import chart_alternative, table_values

PAGE_DESCRIPTIONS = {
    "Overview": "Your cash today. A clearer view of the month ahead.",
    "Transactions": "Validate, investigate and export the activity behind your analysis.",
    "Cash Flow Forecast": "A transparent 30-day outlook built from recurring payments and historical spending.",
    "Anomaly Detection": "Investigate unusual activity with comparisons to earlier transactions.",
    "Risk Analysis": "Understand each contribution to your financial risk indicator.",
    "Scenario Simulator": "Explore how changes in income, costs and payment timing affect your cash.",
    "AI Insights": "Ask about your cash. Every answer starts with your calculated financial evidence.",
    "Model Evaluation": "Measure chronological forecast errors and labeled synthetic anomaly detection.",
    "Data quality": "Review import findings before relying on financial totals.",
}


def apply_style() -> None:
    # Static CSS only. User descriptions and financial data never enter HTML.
    st.markdown("""<style>
    .block-container {max-width:1280px; padding-top:2.25rem; padding-bottom:2rem;}
    h1 {letter-spacing:-0.035em; font-weight:650; font-size:2rem; line-height:1.2;}
    h2, h3 {letter-spacing:-0.02em;}
    h2 {font-size:1.35rem;} h3 {font-size:1.1rem;}
    [data-testid="stMetric"] {background:var(--secondary-background-color, rgba(128,148,170,.06));
      border:1px solid rgba(128,148,170,.18); border-radius:.75rem;
      padding:.85rem 1rem; min-height:100px;}
    [data-testid="stMetricValue"] {font-variant-numeric:tabular-nums;
      font-size:clamp(1.2rem,1.7vw,1.55rem); line-height:1.35; white-space:normal;}
    [data-testid="stMetricValue"] > div {white-space:normal; overflow:visible;
      text-overflow:clip; overflow-wrap:anywhere;}
    [data-testid="stMetricLabel"] {height:auto;}
    [data-testid="stMetricLabel"] [data-testid="stMarkdownContainer"],
    [data-testid="stMetricLabel"] p, [data-testid="stMetricValue"] p {
      white-space:normal !important; overflow:visible; text-overflow:clip;
      overflow-wrap:anywhere;}
    [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] [data-testid="stMetric"]) {
      flex-wrap:wrap;}
    [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] [data-testid="stMetric"]) > [data-testid="stColumn"] {
      flex:1 1 14rem !important; min-width:min(100%,14rem) !important;}
    [data-testid="stSidebar"] h1 {font-size:1.35rem;}
    button[kind="primary"]:not(:disabled) {
      background-color:#0F766E; border-color:#0F766E; color:#FFFFFF;}
    [data-testid="stCaptionContainer"] {color:var(--text-color); opacity:.88;}
    /* Fixed foreground/surface pairs avoid theme-dependent low-contrast status text. */
    [data-testid="stAlertContainer"]:has([data-testid="stAlertContentSuccess"]) {
      background-color:#DCFCE7;}
    [data-testid="stAlertContentSuccess"], [data-testid="stAlertContentSuccess"] p {
      color:#166534;}
    [data-testid="stAlertContainer"]:has([data-testid="stAlertContentError"]) {
      background-color:#FEE2E2;}
    [data-testid="stAlertContentError"], [data-testid="stAlertContentError"] p {
      color:#991B1B;}
    [data-testid="stTable"] th, [data-testid="stTable"] th p {
      color:#334155; background-color:#E2E8F0;}
    [data-testid="stMetricDelta"]:has([data-testid="stMetricDeltaIcon-Up"]) {
      color:#166534; background-color:#DCFCE7;}
    [data-testid="stMetricDelta"]:has([data-testid="stMetricDeltaIcon-Down"]) {
      color:#991B1B; background-color:#FEE2E2;}
    button:focus-visible, input:focus-visible, textarea:focus-visible,
    [role="radio"]:focus-visible, [role="slider"]:focus-visible,
    summary:focus-visible, a:focus-visible {
      outline:3px solid #0F766E !important; outline-offset:3px !important;}
    @media (prefers-color-scheme:dark) {
      button:focus-visible, input:focus-visible, textarea:focus-visible,
      [role="radio"]:focus-visible, [role="slider"]:focus-visible,
      summary:focus-visible, a:focus-visible {outline-color:#5EEAD4 !important;}
    }
    @media (max-width:740px) {
      .block-container {padding-top:3rem; padding-left:1rem; padding-right:1rem;}
      h1 {font-size:1.75rem;}
      [data-testid="stMetric"] {min-height:95px; padding:.75rem;}
    }
    [data-testid="stApp"] :focus-visible {
      outline:3px solid #0F766E !important; outline-offset:3px !important;}
    @media (prefers-color-scheme:dark) {
      [data-testid="stApp"] :focus-visible {outline-color:#5EEAD4 !important;}
    }
    @media (prefers-reduced-motion:reduce) {
      [data-testid="stApp"] *, [data-testid="stApp"] *::before,
      [data-testid="stApp"] *::after {
        animation-duration:0.01ms !important; animation-iteration-count:1 !important;
        transition-duration:0.01ms !important; scroll-behavior:auto !important;}
    }
    </style>""", unsafe_allow_html=True)


def page_header(page: str) -> None:
    if st.session_state.get("cashguard_rendered_page") != page:
        st.session_state["cashguard_rendered_page"] = page
        navigation_count = int(st.session_state.get("cashguard_navigation_count", 0)) + 1
        st.session_state["cashguard_navigation_count"] = navigation_count
        # The radio navigation keeps one Streamlit document. Reset only on page
        # changes, never on filter/scenario reruns. No user data enters this script;
        # the internal integer makes consecutive navigation renders distinct.
        st.html(f"""<script>/* navigation {navigation_count:d} */
        requestAnimationFrame(() => {{
          document.querySelector('[data-testid="stMain"]')?.scrollTo({{top:0, behavior:'instant'}});
        }});
        </script>""", unsafe_allow_javascript=True)
    st.title(VIEWS[page][1])
    st.write(PAGE_DESCRIPTIONS[page])


def overview_metrics(bundle: DashboardBundle, currency: str) -> None:
    values = bundle.metrics
    for column, label, amount in zip(st.columns(4),
                                     ["Estimated cash balance", "Total income", "Total expenses", "Estimated 30-day balance"],
                                     [values.estimated_balance, values.total_income, values.total_expenses,
                                      Decimal(int(bundle.forecast.daily.iloc[-1]['balance_cents'])) / 100]):
        column.metric(label, format_money(amount, currency))


def risk_status(risk: RiskResult) -> None:
    label = f"Financial risk indicator · {risk.level}"
    if risk.score is not None:
        label += f" · {risk.score}/100"
    if risk.level == "High":
        st.error(label)
    elif risk.level in {"Moderate", "Insufficient data"}:
        st.warning(label)
    else:
        st.success(label)
    st.caption(f"Data sufficiency: {risk.data_sufficiency}. Heuristic budgeting indicator; not a credit score or validated rating.")
    if risk.data_sufficiency in {"limited", "insufficient"}:
        st.warning("Some inputs are insufficient or unavailable. Treat this indicator as provisional and review the data warnings.")


def warnings_panel(warnings: tuple[str, ...], title: str = "Data sufficiency and limitations") -> None:
    with st.expander(title):
        for warning in dict.fromkeys(warnings):
            st.write(f"• {warning}")


def chart(figure, key: str) -> None:
    description, points = chart_alternative(figure)
    st.plotly_chart(figure, width="stretch", theme="streamlit", key=key,
                    config={"displaylogo": False, "scrollZoom": False}, alt=description)
    with st.expander(f"Chart data: {figure.layout.title.text or 'Financial chart'}"):
        st.write(description)
        if points.empty:
            st.info("No plotted observations are available for these inputs.")
        else:
            st.table(table_values(points), hide_index=True, alt="All plotted source values, without recalculation.")
