"""Presentation-only routes. Keep original route IDs and financial state intact."""

import streamlit as st

VIEWS = {
    "Overview": ("Home", "Home", "home"),
    "Transactions": ("Explore", "Transactions", "transactions"),
    "Cash Flow Forecast": ("Explore", "Cash forecast", "forecast"),
    "Anomaly Detection": ("Explore", "Unusual Activity", "unusual-activity"),
    "Risk Analysis": ("Explore", "Financial Risk", "financial-risk"),
    "Scenario Simulator": ("Plan", "Plan", "plan"),
    "AI Insights": ("AI Assistant", "AI Assistant", "assistant"),
    "Model Evaluation": ("Advanced", "Model Evaluation", "evaluation"),
    "Data quality": ("Advanced", "Data quality", "data-quality"),
}
AREAS = ("Home", "Explore", "Plan", "AI Assistant")
EXPLORE = tuple(route for route, values in VIEWS.items() if values[0] == "Explore")


def resolve_view(value):
    """Allow only known labels/legacy IDs/slugs; URLs never carry financial inputs."""
    return next((route for route, values in VIEWS.items() if value in (route, values[1], values[2])), None)


def initialize():
    requested = st.query_params.get("view", st.query_params.get("page", ""))
    if st.session_state.get("cashguard_url_seen") != requested:
        resolved = resolve_view(requested)
        if resolved:
            st.session_state["navigation"] = resolved
    st.session_state.setdefault("navigation", "Overview")
    st.session_state["cashguard_url_seen"] = requested


def navigate(route):
    if route not in VIEWS:
        raise ValueError("Unknown dashboard view")
    st.session_state["navigation"] = route
    st.query_params["view"] = VIEWS[route][2]
    st.session_state["cashguard_url_seen"] = VIEWS[route][2]


def _selected():
    navigate(st.session_state["navigation"])


def _explore_selected():
    selected = st.session_state.get("explore_view")
    if selected in EXPLORE:
        navigate(selected)


def sidebar_navigation():
    current = st.session_state["navigation"]
    area = VIEWS[current][0]
    if current in EXPLORE:
        st.session_state["cashguard_explore_route"] = current
    destinations = ("Overview", st.session_state.get("cashguard_explore_route", "Transactions"),
                    "Scenario Simulator", "AI Insights")
    for index, (label, target) in enumerate(zip(AREAS, destinations)):
        st.button(label, key=f"area_{index}", width="stretch",
                  type="primary" if area == label else "tertiary", on_click=navigate, args=(target,))
    with st.expander("Advanced", expanded=area == "Advanced"):
        st.caption("Model evaluation, data quality and the complete view directory.")
        # This native directory also preserves the original route/widget contract.
        current = st.radio("Navigation", list(VIEWS), key="navigation",
                           format_func=lambda value: VIEWS[value][1], on_change=_selected)
    return current


def explore_navigation(route):
    if route in EXPLORE:
        st.session_state["explore_view"] = route
        st.pills("Explore", EXPLORE, format_func=lambda value: VIEWS[value][1],
                 key="explore_view", on_change=_explore_selected, required=True, wrap=True)
