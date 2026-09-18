"""Single authority for admission and settlement. Never hold locks over provider I/O."""
import hashlib
import json
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import select
from packages.domain.db import transaction
from packages.domain.models import Application, Budget, Request, Reservation, Ledger, Event, Key
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
