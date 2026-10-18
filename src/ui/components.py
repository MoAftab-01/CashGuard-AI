"""Shared native Streamlit components and static, theme-compatible styling."""

import streamlit as st

from src.dashboard_service import DashboardBundle, format_money
from src.risk_engine import RiskResult

PAGE_DESCRIPTIONS = {
    "Overview": "Your cash position, spending patterns and financial risk in one place.",
    "Transactions": "Validate, investigate and export the activity behind your analysis.",
    "Cash Flow Forecast": "A transparent 30-day outlook built from recurring payments and historical spending.",
    "Anomaly Detection": "Investigate unusual activity with comparisons to earlier transactions.",
    "Risk Analysis": "Understand each contribution to your financial risk indicator.",
    "Scenario Simulator": "Explore how changes in income, costs and payment timing affect your cash.",
    "AI Insights": "Local, evidence-linked explanations with calculated summaries always available.",
    "Model Evaluation": "Measure chronological forecast errors and labeled synthetic anomaly detection.",
    "Data quality": "Review import findings before relying on financial totals.",
}


def apply_style() -> None:
    # Static CSS only. User descriptions and financial data never enter HTML.
    st.markdown("""<style>
    .block-container {max-width:1480px; padding-top:4.5rem; padding-bottom:3rem;}
    h1 {letter-spacing:-0.035em; font-weight:700;}
    h2, h3 {letter-spacing:-0.02em;}
    [data-testid="stMetric"] {border:1px solid rgba(128,148,170,.25);
      border-radius:.8rem; padding:1rem 1.1rem; min-height:110px;}
    [data-testid="stMetricValue"] {font-variant-numeric:tabular-nums;
      font-size:clamp(1.2rem,1.7vw,1.55rem); line-height:1.35; white-space:normal;}
    [data-testid="stMetricValue"] > div {white-space:normal; overflow:visible;
      text-overflow:clip; overflow-wrap:anywhere;}
    [data-testid="stSidebar"] .block-container {padding-top:1.5rem;}
    @media (max-width:740px) {
      .block-container {padding-top:4rem; padding-left:1rem; padding-right:1rem;}
      [data-testid="stMetric"] {min-height:95px; padding:.75rem;}
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
    st.caption("CASHGUARD AI  /  FINANCIAL ANALYTICS")
    st.title(page)
    st.write(PAGE_DESCRIPTIONS[page])


def overview_metrics(bundle: DashboardBundle, currency: str) -> None:
    values = bundle.metrics
    for column, label, amount in zip(st.columns(4),
                                     ["Estimated cash balance", "Total income", "Total expenses", "Net cash flow"],
                                     [values.estimated_balance, values.total_income, values.total_expenses, values.net_cash_flow]):
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
    st.plotly_chart(figure, width="stretch", theme="streamlit", key=key,
                    config={"displaylogo": False, "scrollZoom": False})
