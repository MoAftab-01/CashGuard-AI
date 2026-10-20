import asyncio
from decimal import Decimal
from threading import Event
from types import SimpleNamespace

import httpx
import pytest

from api.main import create_app
from api.schemas.requests import AnalysisRequest
from api.services.analytics_service import AnalyticsService
from config import SAMPLE_DATA_PATH, TRANSACTION_COLUMNS
from deploy.serve import wait_ready
from scripts.load_demo import run_probe
from src.data_processing import validate_csv
from src.observability import Metrics
from src.settings import Settings


def request_payload():
    imported=validate_csv(SAMPLE_DATA_PATH)
    from src.data_processing import Transaction
    return dict(transactions=[Transaction(**{key:row[key] for key in TRANSACTION_COLUMNS}).model_dump(mode="json")
                              for row in imported.data.to_dict('records')],opening_balance="2500.00")


def test_busy_requests_are_rejected_without_queueing_and_health_stays_responsive(monkeypatch):
    application=create_app(Settings(allowed_hosts=("testserver",),max_concurrent_analytics=1))
    payload=request_payload()
    result=AnalyticsService().dashboard(AnalysisRequest(**payload))
    started,release=Event(),Event()
    def slow(self,request):
        started.set()
        assert release.wait(3)
        return result
    monkeypatch.setattr(AnalyticsService,"dashboard",slow)
    async def check():
        transport=httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport,base_url="http://testserver") as client:
            first=asyncio.create_task(client.post('/api/v1/dashboard/prepare',json=payload))
            assert await asyncio.to_thread(started.wait,2)
            assert application.state.metrics.active._value.get()==1
            health=await client.get('/ready')
            busy=await client.post('/api/v1/dashboard/prepare',json=payload)
            assert health.status_code==200 and busy.status_code==503
            release.set()
            assert (await first).status_code==200
            assert application.state.metrics.active._value.get()==0
    asyncio.run(check())


def test_concurrent_distinct_histories_never_share_financial_state():
    application=create_app(Settings(allowed_hosts=("testserver",),max_concurrent_analytics=3))
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application),base_url="http://testserver") as client:
            async def analyze(amount,name):
                payload={'transactions':[{'date':'2026-01-01','description':name,'amount':amount,'category':'Other'}],
                         'opening_balance':'0.00'}
                response=await client.post('/api/v1/analytics/summary',json=payload)
                assert response.status_code==200
                return Decimal(response.json()['metrics']['estimated_balance'])
            values=await asyncio.gather(analyze('1.23','SESSION_A'),analyze('9.87','SESSION_B'),analyze('1.23','SESSION_A'))
            assert values==[Decimal('1.23'),Decimal('9.87'),Decimal('1.23')]
    asyncio.run(check())


def test_observability_labels_stay_bounded_and_new_routes_have_templates():
    metrics=Metrics()
    metrics.observe_http('/api/v1/dashboard/prepare','POST',200,.01)
    metrics.model_failure('PRIVATE_CANARY','PRIVATE_PROVIDER')
    text=metrics.render().decode()
    assert 'PRIVATE' not in text
    assert 'route="/api/v1/dashboard/prepare"' in text
    assert 'reason="unexpected"' in text
    assert 'cashguard_inflight_analytics' in text
    assert 'provider="huggingface"' in text


def test_supervisor_fails_fast_if_child_exits_before_readiness():
    with pytest.raises(RuntimeError,match='exited'):
        wait_ready('http://127.0.0.1:1',[SimpleNamespace(poll=lambda:1)],timeout=.1)


@pytest.mark.parametrize('count,concurrency',[(0,1),(101,1),(2,0),(2,9),(True,1)])
def test_load_probe_rejects_unbounded_work_without_network(count,concurrency):
    with pytest.raises(ValueError):
        run_probe('http://127.0.0.1:1',count=count,concurrency=concurrency)
