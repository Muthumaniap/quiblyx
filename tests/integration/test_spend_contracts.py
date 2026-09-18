import os
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import select
from tests.integration.test_flow import c, g, auth, onboard
from packages.domain.db import transaction
from packages.domain.models import (Budget, SpendContract, ContractAllocation,
                                    ContractReservation, ContractLedger, Request)

pytestmark = pytest.mark.skipif(os.environ.get("INTEGRATION") != "1", reason="requires PostgreSQL + Redis")


def create_contract(tenant, application, key, **changes):
    body = {"name": "Resolve support ticket", "purpose": "Answer one customer issue",
            "application_id": application, "key_id": key["id"], "max_cost_microusd": 200,
            "max_tokens": 200, "max_steps": 2, "allowed_models": ["org-balanced"],
            "allowed_tools": [], "data_region": "local", "duration_seconds": 3600}
    body.update(changes)
    response = c.post(f"/api/v1/organisations/{tenant}/spend-contracts", headers=auth, json=body)
    assert response.status_code == 201, response.text
    return response.json()


def contract_call(key, token, idem=None, **changes):
    body = {"model": "org-balanced", "messages": [{"role": "user", "content": "Hello"}],
            "max_tokens": 32}
    body.update(changes)
    return g.post("/v1/chat/completions", headers={"Authorization": "Bearer " + key["secret"],
                  "Idempotency-Key": idem or str(uuid.uuid4()), "X-Spend-Contract": token,
                  "X-Contract-Step": "answer"}, json=body)


def test_contract_reserves_executes_and_closes_with_receipt():
    tenant, application, key = onboard(1000)
    contract = create_contract(tenant, application, key)
    with transaction(tenant) as s:
        budget = s.scalar(select(Budget).where(Budget.tenant_id == tenant))
        assert budget.reserved == 200 and budget.spent == 0
    first = contract_call(key, contract["token"], "step-1")
    second = contract_call(key, contract["token"], "step-2")
    assert first.status_code == second.status_code == 200
    assert first.json()["platform"]["spend_contract_id"] == contract["id"]
    assert contract_call(key, contract["token"], "step-3").status_code == 429
    receipt = c.post(f"/api/v1/organisations/{tenant}/spend-contracts/{contract['id']}/close",
                     headers=auth)
    assert receipt.status_code == 200, receipt.text
    data = receipt.json()
    assert data["contract"]["spent_cost"] == 138
    assert data["contract"]["spent_tokens"] == 82
    assert len(data["allocations"]) == 2
    with transaction(tenant) as s:
        budget = s.scalar(select(Budget).where(Budget.tenant_id == tenant))
        assert budget.reserved == 0 and budget.spent == 138
        assert len(list(s.scalars(select(ContractLedger).where(
            ContractLedger.tenant_id == tenant, ContractLedger.contract_id == contract["id"])))) == 3


def test_parallel_steps_cannot_exceed_contract():
    tenant, application, key = onboard(5000)
    contract = create_contract(tenant, application, key, max_cost_microusd=500,
                               max_tokens=500, max_steps=5)
    with ThreadPoolExecutor(max_workers=12) as pool:
        responses = list(pool.map(lambda i: contract_call(key, contract["token"], f"parallel-{i}"), range(12)))
    assert sum(response.status_code == 200 for response in responses) == 5
    assert all(response.status_code in (200, 429) for response in responses)
    with transaction(tenant) as s:
        row = s.scalar(select(SpendContract).where(SpendContract.id == contract["id"],
                                                   SpendContract.tenant_id == tenant))
        assert row.steps_started == 5 and row.spent_cost == 345 and row.outstanding_cost == 0
        assert len(list(s.scalars(select(ContractAllocation).where(
            ContractAllocation.tenant_id == tenant, ContractAllocation.contract_id == contract["id"])))) == 5


def test_rotated_token_invalidates_old_and_binds_principal():
    tenant, application, key = onboard(1000)
    other = c.post(f"/api/v1/organisations/{tenant}/virtual-keys", headers=auth,
                   json={"application_id": application}).json()
    contract = create_contract(tenant, application, key)
    rotated = c.post(f"/api/v1/organisations/{tenant}/spend-contracts/{contract['id']}/rotate-token",
                     headers=auth).json()
    assert contract_call(key, contract["token"]).status_code == 401
    assert contract_call(other, rotated["token"]).status_code == 403
    assert contract_call(key, rotated["token"]).status_code == 200


def test_uncertain_step_blocks_close_then_conservative_reconciliation():
    tenant, application, key = onboard(1000)
    contract = create_contract(tenant, application, key)
    response = contract_call(key, contract["token"], mock_fault="timeout")
    assert response.status_code == 502
    close = c.post(f"/api/v1/organisations/{tenant}/spend-contracts/{contract['id']}/close", headers=auth)
    assert close.status_code == 409
    with transaction(tenant) as s:
        request = s.scalar(select(Request).where(Request.tenant_id == tenant,
                                                 Request.contract_id == contract["id"]))
        assert request.state == "uncertain"
        request_id = request.id
    reconcile = c.post(f"/api/v1/organisations/{tenant}/requests/{request_id}/reconcile-conservative",
                       headers=auth)
    assert reconcile.status_code == 200, reconcile.text
    receipt = c.post(f"/api/v1/organisations/{tenant}/spend-contracts/{contract['id']}/close", headers=auth)
    assert receipt.status_code == 200
    assert receipt.json()["contract"]["spent_cost"] == 77
    assert receipt.json()["contract"]["spent_tokens"] == 45


def test_revoke_prevents_new_steps_and_releases_unused_escrow():
    tenant, application, key = onboard(1000)
    contract = create_contract(tenant, application, key)
    revoked = c.post(f"/api/v1/organisations/{tenant}/spend-contracts/{contract['id']}/revoke",
                     headers=auth)
    assert revoked.status_code == 200 and revoked.json()["state"] == "revoked"
    assert contract_call(key, contract["token"]).status_code == 401
    receipt = c.get(f"/api/v1/organisations/{tenant}/spend-contracts/{contract['id']}", headers=auth).json()
    assert receipt["contract"]["state"] == "revoked" and receipt["contract"]["closed_at"]
    with transaction(tenant) as s:
        budget = s.scalar(select(Budget).where(Budget.tenant_id == tenant))
        reservation = s.scalar(select(ContractReservation).where(ContractReservation.tenant_id == tenant,
                                                                  ContractReservation.contract_id == contract["id"]))
        assert budget.reserved == 0 and reservation.settled
