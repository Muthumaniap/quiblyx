import os
import asyncio
import pytest
from fastapi import HTTPException
from redis import ConnectionError
from sqlalchemy import select
from tests.integration.test_flow import onboard, call
from packages.domain.db import transaction
from packages.domain.models import Request, Budget
from packages.domain.accounting import admit, transition, settle
import services.gateway.main as gateway

pytestmark = pytest.mark.skipif(os.environ.get("INTEGRATION") != "1", reason="requires PostgreSQL + Redis")


def test_redis_outage_compensates_before_dispatch(monkeypatch):
    tenant, _, key = onboard()
    def unavailable(*args, **kwargs):
        raise ConnectionError("unavailable")
    monkeypatch.setattr(gateway.redis, "eval", unavailable)
    assert call(key).status_code == 503
    with transaction(tenant) as s:
        request = s.scalar(select(Request).where(Request.tenant_id == tenant))
        budget = s.scalar(select(Budget).where(Budget.tenant_id == tenant))
        assert request.state == "released" and budget.reserved == 0 and budget.spent == 0


def test_cancelled_stream_retains_reservation():
    tenant, _, key = onboard()
    async def run():
        body = gateway.Chat(messages=[{"role": "user", "content": "hello"}], stream=True)
        response = await gateway.chat(body, "Bearer " + key["secret"], "cancel-stream")
        iterator = response.body_iterator
        assert "data:" in await anext(iterator)
        await iterator.aclose()
    asyncio.run(run())
    with transaction(tenant) as s:
        request = s.scalar(select(Request).where(Request.tenant_id == tenant))
        budget = s.scalar(select(Budget).where(Budget.tenant_id == tenant))
        assert request.state == "uncertain" and budget.reserved == request.bound and budget.spent == 0


def test_dispatched_recovery_cannot_release():
    tenant, app, key = onboard()
    rid, _ = admit(tenant, key["id"], app, "crash-after-dispatch", {}, 20)
    transition(tenant, rid, "dispatched")
    with pytest.raises(ValueError):
        settle(tenant, rid, 0, pre_dispatch=True)
    with transaction(tenant) as s:
        assert s.scalar(select(Budget.reserved).where(Budget.tenant_id == tenant)) == 20


def test_shared_quota_pool_across_keys():
    tenant, _, key = onboard()
    gateway.redis.set(f"quota:{tenant}:mock", 600, ex=60)
    response = call(key)
    assert response.status_code == 429 and response.headers["retry-after"] == "60"
    with transaction(tenant) as s:
        assert s.scalar(select(Budget.reserved).where(Budget.tenant_id == tenant)) == 0


def test_revocation_checked_again_at_admission():
    from tests.integration.test_flow import c, auth
    tenant, app, key = onboard()
    gateway.authenticate("Bearer " + key["secret"])
    c.post(f"/api/v1/organisations/{tenant}/virtual-keys/{key['id']}/revoke", headers=auth)
    with pytest.raises(HTTPException) as exc:
        admit(tenant, key["id"], app, "revocation-race", {}, 20)
    assert exc.value.status_code == 401
