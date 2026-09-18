import os
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from services.control_api.main import app as control
from services.gateway.main import app as gateway
from packages.domain.db import transaction
from packages.domain.models import Budget, Request, Ledger, Membership, Group
from packages.domain.accounting import admit, settle, transition

pytestmark = pytest.mark.skipif(os.environ.get("INTEGRATION") != "1", reason="requires real PostgreSQL + Redis")
c = TestClient(control)
g = TestClient(gateway, raise_server_exceptions=False)
auth = {"Authorization": "Bearer test-local-token"}


def onboard(limit=1000000):
    org = c.post("/api/v1/organisations", headers=auth,
                 json={"name": "Test " + uuid.uuid4().hex, "content_days": 0, "budget_microusd": limit})
    assert org.status_code == 201, org.text
    tid = org.json()["id"]
    path = f"/api/v1/organisations/{tid}"
    connection = c.post(path + "/provider-connections", headers=auth, json={"provider": "mock"})
    assert connection.status_code == 201, connection.text
    app = c.post(path + "/applications", headers=auth,
                 json={"name": "server", "connection_id": connection.json()["id"]})
    assert app.status_code == 201, app.text
    key = c.post(path + "/virtual-keys", headers=auth, json={"application_id": app.json()["id"]})
    assert key.status_code == 201, key.text
    return tid, app.json()["id"], key.json()


def call(key, **kwargs):
    return g.post("/v1/chat/completions", headers={"Authorization": "Bearer " + key["secret"],
                        "Idempotency-Key": kwargs.pop("idem", str(uuid.uuid4()))},
                  json={"messages": [{"role": "user", "content": "Hello"}], "max_tokens": 32, **kwargs})


def test_complete_flow_and_revocation():
    tid, _, key = onboard()
    response = call(key, idem="replay")
    assert response.status_code == 200, response.text
    assert call(key, idem="replay").json() == response.json()
    assert call(key, idem="replay", max_tokens=33).status_code == 409
    usage = c.get(f"/api/v1/organisations/{tid}/usage", headers=auth).json()
    assert usage["spent_microusd"] > 0
    assert usage["reserved_microusd"] == 0
    c.post(f"/api/v1/organisations/{tid}/virtual-keys/{key['id']}/revoke", headers=auth)
    assert call(key).status_code == 401


def test_shared_parent_parallel_admission():
    tid, aid, key = onboard(100)
    other_key = c.post(f"/api/v1/organisations/{tid}/virtual-keys", headers=auth,
                       json={"application_id": aid}).json()
    def attempt(i):
        try:
            return admit(tid, key["id"] if i % 2 else other_key["id"], aid, str(i), {"n": i}, 10)[0]
        except HTTPException as exc:
            assert exc.detail == "budget_exhausted"
            return None
    with ThreadPoolExecutor(max_workers=16) as pool:
        accepted = [r for r in pool.map(attempt, range(40)) if r]
    assert len(accepted) == 10
    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(lambda _: settle(tid, accepted[0], 5), range(20)))
    with transaction(tid) as s:
        budget = s.scalar(select(Budget).where(Budget.tenant_id == tid))
        assert budget.spent == 5 and budget.reserved == 90
        entries = list(s.scalars(select(Ledger).where(Ledger.tenant_id == tid,
                                Ledger.request_id == accepted[0], Ledger.event == "settle")))
        assert len(entries) == 1


def test_cross_tenant_api_and_rls_pool():
    t1, _, key1 = onboard()
    t2, _, _ = onboard()
    with transaction(t2) as s:
        member = s.scalar(select(Membership).where(Membership.tenant_id == t2))
        member.subject = "different-owner"
    assert c.get(f"/api/v1/organisations/{t2}/usage", headers=auth).status_code == 403
    assert c.post(f"/api/v1/organisations/{t1}/virtual-keys/{key1['id']}/revoke",
                  headers={"Authorization": "invalid"}).status_code == 401
    for _ in range(4):
        with transaction(t1) as s:
            assert not list(s.scalars(select(Budget).where(Budget.tenant_id == t2)))
            # No tenant filter deliberately: RLS must provide defence in depth.
            assert {row.tenant_id for row in s.scalars(select(Budget))} == {t1}
        with transaction() as s:
            assert not list(s.scalars(select(Budget)))
            assert not s.scalar(text("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname=current_user"))


def test_cross_tenant_reference_rejected():
    t1, _, _ = onboard()
    t2, _, _ = onboard()
    response = c.post(f"/api/v1/organisations/{t2}/groups", headers=auth, json={"name": "other"})
    group = response.json()["id"]
    assert c.post(f"/api/v1/organisations/{t1}/groups", headers=auth,
                  json={"name": "bad", "parent_id": group}).status_code == 404
    with transaction(t1) as s:
        with pytest.raises(Exception):
            s.add(Group(tenant_id=t1, name="bad", parent_id=group))
            s.flush()


def test_failure_accounting():
    tid, _, key = onboard()
    assert call(key, mock_fault="before_dispatch").status_code == 503
    assert call(key, mock_fault="timeout").status_code == 502
    with transaction(tid) as s:
        requests = list(s.scalars(select(Request).where(Request.tenant_id == tid)))
        assert {r.state for r in requests} == {"released", "uncertain"}
        budget = s.scalar(select(Budget).where(Budget.tenant_id == tid))
        assert budget.spent == 0 and budget.reserved == 77
        uncertain = next(r.id for r in requests if r.state == "uncertain")
    with pytest.raises(ValueError):
        settle(tid, uncertain, 0, pre_dispatch=True)


def test_stream_completion_and_partial_failure():
    tid, _, key = onboard()
    response = call(key, stream=True)
    assert "data: [DONE]" in response.text
    call(key, stream=True, mock_fault="partial_stream")
    with transaction(tid) as s:
        states = list(s.scalars(select(Request.state).where(Request.tenant_id == tid)))
        assert sorted(states) == ["completed", "uncertain"]


def test_admission_period_persists_and_budget_reduction(monkeypatch):
    tid, aid, key = onboard(100)
    rid, _ = admit(tid, key["id"], aid, "period", {}, 50)
    transition(tid, rid, "dispatched")
    from packages.domain import accounting
    original_period = accounting.month()
    monkeypatch.setattr(accounting, "month", lambda: "2099-01")
    settle(tid, rid, 20)
    with transaction(tid) as s:
        budget = s.scalar(select(Budget).where(Budget.tenant_id == tid))
        assert budget.period == original_period and budget.spent == 20 and budget.reserved == 0
