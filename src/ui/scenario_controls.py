"""Explicit hypothetical form values, never financial calculations."""

import streamlit as st

PRESETS = ("Unexpected expense", "Delayed income", "Reduced income", "Increased recurring costs")


def preset_values(name, forecast):
    payments = [event for event in forecast.events if event.kind == "recurring" and event.amount_cents > 0]
    values = dict(income=0, expenses=0, emergency="0.00", emergency_date=forecast.daily.iloc[0]["date"],
                  payment=None, delay=0)
    if name == "Unexpected expense":
        values["emergency"] = "500.00"
    elif name == "Delayed income":
        if not payments:
            raise ValueError("No supported recurring income is projected to delay")
        values.update(payment=payments[0].event_id, delay=7)
    elif name == "Reduced income":
        values["income"] = 20
    elif name == "Increased recurring costs":
        values["expenses"] = 10
    elif name != "Reset":
        raise ValueError("Choose a supported hypothetical preset")
    return values


def apply_preset(name, forecast):
    values = preset_values(name, forecast)
    st.session_state["cashguard_scenario_controls"] = values
    st.session_state.update(scenario_income=values["income"], scenario_expenses=values["expenses"],
                            scenario_emergency=values["emergency"], scenario_delay=values["delay"])
    for key in list(st.session_state):
        if key.startswith("emergency_date_"):
            st.session_state[key] = values["emergency_date"]
        if key.startswith("scenario_payment_"):
            st.session_state[key] = values["payment"]
    st.session_state.pop("cashguard_latest_scenario", None)
    st.session_state.pop("cashguard_ai_report", None)
