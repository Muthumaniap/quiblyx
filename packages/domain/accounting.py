"""Single authority for admission and settlement. Never hold locks over provider I/O."""
import hashlib
import json
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import select
from packages.domain.db import transaction
from packages.domain.models import (Application, Budget, Request, Reservation, Ledger, Event, Key,
                                    SpendContract, ContractReservation, ContractAllocation, ContractLedger)
from packages.domain.security import ancestry


def month():
    return datetime.now(timezone.utc).strftime("%Y-%m")


def threshold_events(s, budget):
    if budget.hard_limit <= 0:
        return
    for threshold in (70, 85, 95):
        if (budget.spent + budget.reserved) * 100 >= budget.hard_limit * threshold:
            dedup = f"{budget.tenant_id}:{budget.id}:{threshold}"
            if not s.scalar(select(Event.id).where(Event.tenant_id == budget.tenant_id, Event.dedup_key == dedup)):
                s.add(Event(tenant_id=budget.tenant_id, kind="budget.threshold", dedup_key=dedup,
                            payload={"budget_id": budget.id, "threshold": threshold, "unit": budget.unit,
                                     "basis": "committed", "period": budget.period}))
                s.flush()


def payload_digest(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def admit(tenant, key_id, application_id, idem, payload, bound, token_bound=None):
    if bound <= 0:
        raise ValueError("reservation bound must be positive")
    with transaction(tenant) as s:
        period = month()
        daily = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        # Root lock serializes idempotency and all sibling admissions in this tenant.
        root = s.scalar(select(Budget).where(Budget.tenant_id == tenant, Budget.scope_id == tenant,
                                           Budget.period == period, Budget.unit == "money").with_for_update())
        if root is None:
            raise HTTPException(403, "active_budget_required")
        key = s.scalar(select(Key).where(Key.tenant_id == tenant, Key.id == key_id,
                                        Key.application_id == application_id, Key.revoked.is_(False)))
        if key is None:
            raise HTTPException(401, "invalid_key")
        previous = s.scalar(select(Request).where(Request.tenant_id == tenant, Request.key_id == key_id,
                                                 Request.idempotency_key == idem))
        if previous:
            if previous.payload_hash != payload_digest(payload):
                raise HTTPException(409, "idempotency_payload_conflict")
            if previous.state == "completed" and previous.response and not payload.get("stream"):
                return previous.id, previous.response
            raise HTTPException(409, "request_in_progress_or_non_replayable")
        app = s.scalar(select(Application).where(Application.id == application_id,
                                                Application.tenant_id == tenant))
        if not app or app.paused:
            raise HTTPException(403, "application_paused")
        scopes = [tenant, application_id] + ancestry(s, tenant, app.group_id)
        budgets = list(s.scalars(select(Budget).where(Budget.tenant_id == tenant,
                            Budget.scope_id.in_(scopes), Budget.period.in_([period, daily])).order_by(Budget.id)
                            .with_for_update()))
        history = list(s.scalars(select(Budget).where(Budget.tenant_id == tenant, Budget.scope_id.in_(scopes))))
        active_kinds = {(b.scope_id, b.unit, len(b.period)) for b in budgets}
        if any((b.scope_id, b.unit, len(b.period)) not in active_kinds for b in history):
            raise HTTPException(403, "period_budget_renewal_required")
        bounds = {"money": bound, "tokens": token_bound if token_bound is not None else bound, "requests": 1}
        for budget in budgets:
            if budget.spent + budget.reserved + bounds[budget.unit] > budget.hard_limit:
                raise HTTPException(429, "budget_exhausted")
        request = Request(tenant_id=tenant, key_id=key_id, application_id=application_id,
                          idempotency_key=idem, payload_hash=payload_digest(payload), bound=bound, period=period)
        s.add(request)
        s.flush()
        for budget in budgets:
            amount = bounds[budget.unit]
            budget.reserved += amount
            s.add(Reservation(tenant_id=tenant, request_id=request.id, budget_id=budget.id, amount=amount))
            s.add(Ledger(tenant_id=tenant, request_id=request.id, budget_id=budget.id,
                         amount=amount, event="reserve"))
            threshold_events(s, budget)
        return request.id, None


def transition(tenant, request_id, state):
    with transaction(tenant) as s:
        req = s.scalar(select(Request).where(Request.id == request_id, Request.tenant_id == tenant)
                       .with_for_update())
        if req.state in ("completed", "released"):
            if state == "dispatched":
                raise HTTPException(409, "request_already_finalized")
            return
        allowed = {"reserved": {"dispatched"}, "dispatched": {"uncertain"}, "uncertain": set()}
        if state not in allowed[req.state]:
            raise ValueError("invalid request transition")
        req.state = state


def settle(tenant, request_id, cost, input_tokens=0, output_tokens=0, response=None, pre_dispatch=False):
    with transaction(tenant) as s:
        # Same ordering as admission: root before request and child budget locks.
        req_snapshot = s.scalar(select(Request).where(Request.id == request_id, Request.tenant_id == tenant))
        if req_snapshot is None:
            raise ValueError("unknown request")
        if req_snapshot.contract_id:
            return settle_contract_request(s, req_snapshot, cost, input_tokens, output_tokens,
                                           response, pre_dispatch)
        reservations = list(s.scalars(select(Reservation).where(Reservation.tenant_id == tenant,
                                                        Reservation.request_id == request_id)))
        ids = [r.budget_id for r in reservations]
        root = s.scalar(select(Budget).where(Budget.id.in_(ids), Budget.scope_id == tenant,
                                            Budget.tenant_id == tenant, Budget.unit == "money",
                                            Budget.period == req_snapshot.period).with_for_update())
        if root is None:
            raise ValueError("missing root reservation")
        req = s.scalar(select(Request).where(Request.id == request_id, Request.tenant_id == tenant)
                       .with_for_update().execution_options(populate_existing=True))
        if req.state in ("completed", "released"):
            return
        if cost < 0 or cost > req.bound:
            raise ValueError("usage outside reserved bound; reconciliation required")
        if pre_dispatch and (req.state != "reserved" or cost != 0):
            raise ValueError("cannot release dispatched usage")
        budgets = {b.id: b for b in s.scalars(select(Budget).where(Budget.id.in_(ids),
                   Budget.tenant_id == tenant).order_by(Budget.id).with_for_update())}
        for reservation in reservations:
            budget = budgets[reservation.budget_id]
            if pre_dispatch:
                actual = 0
            elif cost == req.bound and response is None:
                actual = reservation.amount  # Conservative adjustment consumes each bound.
            else:
                actual = {"money": cost, "tokens": input_tokens + output_tokens, "requests": 1}[budget.unit]
            if actual > reservation.amount or actual < 0:
                raise ValueError("usage outside unit reservation")
            budget.reserved -= reservation.amount
            budget.spent += actual
            reservation.settled = True
            s.add(Ledger(tenant_id=tenant, request_id=request_id, budget_id=budget.id,
                         amount=actual, event="settle"))
            s.add(Ledger(tenant_id=tenant, request_id=request_id, budget_id=budget.id,
                         amount=reservation.amount - actual, event="release"))
        req.state = "released" if pre_dispatch else "completed"
        req.cost, req.input_tokens, req.output_tokens = cost, input_tokens, output_tokens
        # Store no prompt/response content by default, including idempotency cache.
        req.response = response
        s.add(Event(tenant_id=tenant, kind="usage.settled", payload={"request_id": request_id}))


def create_spend_contract(tenant, application_id, key_id, name, purpose, max_cost, max_tokens,
                          max_steps, allowed_models, allowed_tools, data_region, expires_at):
    with transaction(tenant) as s:
        period = month()
        daily = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        root = s.scalar(select(Budget).where(Budget.tenant_id == tenant, Budget.scope_id == tenant,
                                           Budget.period == period, Budget.unit == "money").with_for_update())
        if root is None:
            raise HTTPException(403, "active_budget_required")
        key = s.scalar(select(Key).where(Key.tenant_id == tenant, Key.id == key_id,
                                        Key.application_id == application_id, Key.revoked.is_(False)))
        app = s.scalar(select(Application).where(Application.tenant_id == tenant,
                                                Application.id == application_id))
        if key is None or app is None or app.paused:
            raise HTTPException(403, "invalid_contract_principal")
        scopes = [tenant, application_id] + ancestry(s, tenant, app.group_id)
        budgets = list(s.scalars(select(Budget).where(Budget.tenant_id == tenant,
                            Budget.scope_id.in_(scopes), Budget.period.in_([period, daily]))
                            .order_by(Budget.id).with_for_update()))
        bounds = {"money": max_cost, "tokens": max_tokens, "requests": max_steps}
        for budget in budgets:
            if budget.spent + budget.reserved + bounds[budget.unit] > budget.hard_limit:
                raise HTTPException(429, "contract_budget_exhausted")
        contract = SpendContract(tenant_id=tenant, application_id=application_id, key_id=key_id,
            name=name, purpose=purpose, max_cost=max_cost, max_tokens=max_tokens, max_steps=max_steps,
            allowed_models=allowed_models, allowed_tools=allowed_tools, data_region=data_region,
            expires_at=expires_at)
        s.add(contract)
        s.flush()
        for budget in budgets:
            amount = bounds[budget.unit]
            budget.reserved += amount
            s.add(ContractReservation(tenant_id=tenant, contract_id=contract.id,
                                      budget_id=budget.id, amount=amount))
            s.add(ContractLedger(tenant_id=tenant, contract_id=contract.id,
                                 budget_id=budget.id, amount=amount, event="reserve"))
            threshold_events(s, budget)
        s.flush()
        return contract.id


def admit_contract(claims, idem, payload, cost_bound, token_bound, model, step):
    tenant = claims["tenant_id"]
    with transaction(tenant) as s:
        contract = s.scalar(select(SpendContract).where(SpendContract.tenant_id == tenant,
                            SpendContract.id == claims["sub"]).with_for_update())
        if contract is None or contract.state != "active" or contract.token_version != claims["version"]:
            raise HTTPException(401, "inactive_spend_contract")
        now = datetime.now(timezone.utc)
        expires = contract.expires_at if contract.expires_at.tzinfo else contract.expires_at.replace(tzinfo=timezone.utc)
        if expires <= now:
            contract.state = "expired"
            raise HTTPException(401, "spend_contract_expired")
        if (claims["application_id"] != contract.application_id or claims["key_id"] != contract.key_id
                or claims["scope"] != "spend:allocate"):
            raise HTTPException(401, "invalid_spend_contract")
        if model not in contract.allowed_models:
            raise HTTPException(403, "contract_model_not_allowed")
        if payload.get("tools") and not contract.allowed_tools:
            raise HTTPException(403, "contract_tool_not_allowed")
        previous = s.scalar(select(Request).where(Request.tenant_id == tenant,
                            Request.key_id == contract.key_id, Request.idempotency_key == idem))
        if previous:
            if previous.payload_hash != payload_digest(payload) or previous.contract_id != contract.id:
                raise HTTPException(409, "idempotency_payload_conflict")
            if previous.state == "completed" and previous.response and not payload.get("stream"):
                return previous.id, previous.response, contract.id
            raise HTTPException(409, "request_in_progress_or_non_replayable")
        if contract.steps_started >= contract.max_steps:
            raise HTTPException(429, "contract_step_limit_exhausted")
        if contract.spent_cost + contract.outstanding_cost + cost_bound > contract.max_cost:
            raise HTTPException(429, "contract_cost_exhausted")
        if contract.spent_tokens + contract.outstanding_tokens + token_bound > contract.max_tokens:
            raise HTTPException(429, "contract_token_exhausted")
        request = Request(tenant_id=tenant, key_id=contract.key_id, application_id=contract.application_id,
                          idempotency_key=idem, payload_hash=payload_digest(payload), bound=cost_bound,
                          period=month(), contract_id=contract.id, contract_step=step, model=model)
        s.add(request)
        s.flush()
        s.add(ContractAllocation(tenant_id=tenant, contract_id=contract.id, request_id=request.id,
                                 cost_bound=cost_bound, token_bound=token_bound))
        contract.outstanding_cost += cost_bound
        contract.outstanding_tokens += token_bound
        contract.steps_started += 1
        s.add(Event(tenant_id=tenant, kind="contract.step_reserved",
                    payload={"contract_id": contract.id, "request_id": request.id, "step": step}))
        return request.id, None, contract.id


def settle_contract_request(s, request, cost, input_tokens, output_tokens, response, pre_dispatch):
    contract = s.scalar(select(SpendContract).where(SpendContract.tenant_id == request.tenant_id,
                        SpendContract.id == request.contract_id).with_for_update())
    allocation = s.scalar(select(ContractAllocation).where(
        ContractAllocation.tenant_id == request.tenant_id,
        ContractAllocation.request_id == request.id).with_for_update())
    if request.state in ("completed", "released"):
        return
    if allocation is None or contract is None:
        raise ValueError("missing contract allocation")
    conservative = cost == request.bound and response is None and not pre_dispatch
    actual_tokens = allocation.token_bound if conservative else input_tokens + output_tokens
    if cost < 0 or cost > allocation.cost_bound or actual_tokens > allocation.token_bound:
        raise ValueError("usage outside contract allocation")
    if pre_dispatch and (request.state != "reserved" or cost != 0):
        raise ValueError("cannot release dispatched contract usage")
    contract.outstanding_cost -= allocation.cost_bound
    contract.outstanding_tokens -= allocation.token_bound
    allocation.actual_cost = 0 if pre_dispatch else cost
    allocation.actual_tokens = 0 if pre_dispatch else actual_tokens
    allocation.state = "released" if pre_dispatch else "completed"
    if not pre_dispatch:
        contract.spent_cost += cost
        contract.spent_tokens += actual_tokens
        contract.steps_completed += 1
    request.state = "released" if pre_dispatch else "completed"
    request.cost, request.input_tokens, request.output_tokens = cost, input_tokens, output_tokens
    request.response = response
    s.add(Event(tenant_id=request.tenant_id, kind="contract.step_settled",
                payload={"contract_id": contract.id, "request_id": request.id,
                         "cost": allocation.actual_cost, "tokens": allocation.actual_tokens}))


def close_spend_contract(tenant, contract_id, final_state="completed"):
    if final_state not in ("completed", "revoked", "expired"):
        raise ValueError("invalid contract final state")
    with transaction(tenant) as s:
        contract_snapshot = s.scalar(select(SpendContract).where(SpendContract.tenant_id == tenant,
                                     SpendContract.id == contract_id))
        if contract_snapshot is None:
            raise HTTPException(404, "contract_not_found")
        reservations = list(s.scalars(select(ContractReservation).where(
            ContractReservation.tenant_id == tenant, ContractReservation.contract_id == contract_id)))
        budget_ids = [row.budget_id for row in reservations]
        budgets = {row.id: row for row in s.scalars(select(Budget).where(Budget.tenant_id == tenant,
                   Budget.id.in_(budget_ids)).order_by(Budget.id).with_for_update())}
        contract = s.scalar(select(SpendContract).where(SpendContract.tenant_id == tenant,
                            SpendContract.id == contract_id).with_for_update().execution_options(populate_existing=True))
        if contract.closed_at:
            return contract.id
        if contract.outstanding_cost or contract.outstanding_tokens:
            raise HTTPException(409, "contract_has_outstanding_steps")
        actuals = {"money": contract.spent_cost, "tokens": contract.spent_tokens,
                   "requests": contract.steps_started}
        for reservation in reservations:
            budget = budgets[reservation.budget_id]
            actual = actuals[budget.unit]
            if actual > reservation.amount:
                raise ValueError("contract actual exceeds reservation")
            budget.reserved -= reservation.amount
            budget.spent += actual
            reservation.settled = True
            s.add(ContractLedger(tenant_id=tenant, contract_id=contract.id, budget_id=budget.id,
                                 amount=actual, event="settle"))
            s.add(ContractLedger(tenant_id=tenant, contract_id=contract.id, budget_id=budget.id,
                                 amount=reservation.amount - actual, event="release"))
        if contract.state in ("revoked", "expired"):
            final_state = contract.state
        contract.state = final_state
        contract.closed_at = datetime.now(timezone.utc)
        contract.token_version += 1
        s.add(Event(tenant_id=tenant, kind="contract.closed",
                    payload={"contract_id": contract.id, "state": final_state,
                             "cost": contract.spent_cost, "tokens": contract.spent_tokens}))
        s.flush()
        return contract.id
