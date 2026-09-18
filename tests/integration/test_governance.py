import os
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from tests.integration.test_flow import c, auth, onboard, call
from packages.domain.db import transaction
from packages.domain.models import Budget, Request, Membership
from packages.domain.security import authorize
from packages.domain.accounting import admit, transition, settle

pytestmark = pytest.mark.skipif(os.environ.get("INTEGRATION") != "1", reason="requires PostgreSQL + Redis")


def test_roles_last_owner_and_scope_boundary():
    tenant, _, _ = onboard()
    base = f"/api/v1/organisations/{tenant}"
    first = c.post(base + "/groups", headers=auth, json={"name": "first"}).json()["id"]
    second = c.post(base + "/groups", headers=auth, json={"name": "second"}).json()["id"]
    child = c.post(base + "/groups", headers=auth, json={"name": "child", "parent_id": first}).json()["id"]
    assert c.post(base + "/memberships", headers=auth,
                  json={"subject": "local-owner", "role": "member"}).status_code == 409
    result = c.post(base + "/roles", headers=auth, json={"name": "reporter", "permissions": ["read"]})
    assert result.status_code == 201
    assert c.post(base + "/memberships", headers=auth,
                  json={"subject": "delegate", "role": "manager", "scope_id": first}).status_code == 200
    authorize(tenant, "delegate", True, child)
    for scope in (None, second):
        with pytest.raises(HTTPException):
            authorize(tenant, "delegate", True, scope)
    with transaction(tenant) as s:
        member = s.scalar(select(Membership).where(Membership.tenant_id == tenant, Membership.subject == "delegate"))
        member.role = "member"
    with pytest.raises(HTTPException):
        authorize(tenant, "delegate", True, child)
    assert c.patch(base + f"/groups/{first}", headers=auth, json={"parent_id": child}).status_code == 409


def test_conservative_reconciliation_and_replay():
    tenant, _, key = onboard()
    call(key, mock_fault="timeout")
    with transaction(tenant) as s:
        rid = s.scalar(select(Request.id).where(Request.tenant_id == tenant))
    path = f"/api/v1/organisations/{tenant}/requests/{rid}/reconcile-conservative"
    assert c.post(path, headers=auth).status_code == 200
    assert c.post(path, headers=auth).status_code == 200
    with transaction(tenant) as s:
        budget = s.scalar(select(Budget).where(Budget.tenant_id == tenant))
        assert budget.spent == 77 and budget.reserved == 0


def test_recovered_undispatched_request_cannot_send():
    tenant, application, key = onboard()
    rid, _ = admit(tenant, key["id"], application, "recovery", {}, 30)
    settle(tenant, rid, 0, pre_dispatch=True)
    with pytest.raises(HTTPException):
        transition(tenant, rid, "dispatched")


def test_reduction_and_parent_child_caps():
    tenant, application, key = onboard(100)
    base = f"/api/v1/organisations/{tenant}"
    assert c.post(base + "/budgets", headers=auth,
                  json={"scope_id": application, "hard_limit": 20}).status_code == 200
    with pytest.raises(HTTPException):
        admit(tenant, key["id"], application, "too-large-child", {}, 21)
    rid, _ = admit(tenant, key["id"], application, "small", {}, 20)
    assert c.post(base + "/budgets", headers=auth,
                  json={"scope_id": tenant, "hard_limit": 0, "version": 1}).status_code == 200
    with pytest.raises(HTTPException):
        admit(tenant, key["id"], application, "reduced", {}, 1)
    transition(tenant, rid, "dispatched")
    settle(tenant, rid, 15)
    with transaction(tenant) as s:
        root = s.scalar(select(Budget).where(Budget.tenant_id == tenant, Budget.scope_id == tenant))
        assert root.spent == 15 and root.reserved == 0 and root.hard_limit == 0
