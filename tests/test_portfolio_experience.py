from pathlib import Path

from streamlit.testing.v1 import AppTest

APP=Path(__file__).resolve().parents[1]/'app.py'


def test_first_run_walkthrough_loads_explicit_demo_and_navigates_without_new_pages():
    app=AppTest.from_file(APP,default_timeout=20).run()
    assert not app.exception
    assert any('fictional transactions' in item.value for item in app.header)
    app.button(key='landing_demo').click().run()
    assert not app.exception and app.session_state['cashguard_walkthrough']
    assert {metric.label:metric.value for metric in app.metric}['Estimated cash balance']=='USD 16,268.23'
    app.button(key='guided_2').click().run()
    assert app.radio(key='navigation').value=='Cash Flow Forecast'
    assert not app.exception
    app.button(key='guided_exit').click().run()
    assert not app.session_state['cashguard_walkthrough']


def test_clear_session_releases_private_results_and_creates_fresh_identity():
    app=AppTest.from_file(APP,default_timeout=20).run()
    old=app.session_state['cashguard_session_id']
    app.button(key='start_demo').click().run()
    assert 'dashboard' in app.session_state['cashguard_private_cache']
    app.button(key='clear_session').click().run()
    assert app.session_state['cashguard_session_id'] != old
    assert 'dashboard' not in app.session_state['cashguard_private_cache']
    assert not app.metric
