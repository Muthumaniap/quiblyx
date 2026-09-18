from typing import Literal
from datetime import datetime, timezone
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from packages.domain.config import settings
from packages.domain.db import transaction
from packages.domain.models import (Tenant, Membership, Group, Connection, Application, Key, Budget,
                                    Request, Audit, Event, Role, Project, ServiceAccount, Reservation, Ledger)
from packages.domain.security import identity, authorize, ancestry, encrypt, issue_secret, PERMISSIONS, TEMPLATES
from packages.domain.accounting import month, settle
from packages.observability.http import configure

app = FastAPI(title=f"{settings().product_name} Control API", version="0.1.0")
configure(app, "control")
app.add_middleware(CORSMiddleware, allow_origins=[settings().web_origin],
                   allow_methods=["GET", "POST", "PATCH"], allow_headers=["Authorization", "Content-Type"])


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OrganisationInput(Input):
    name: str = Field(min_length=1, max_length=120)
    content_days: int = Field(ge=0, le=365)
    budget_microusd: int = Field(default=1_000_000, ge=0, le=10**15)


class GroupInput(Input):
    name: str = Field(min_length=1, max_length=120)
    parent_id: str | None = None


class ProviderInput(Input):
    name: str = Field(default="Local mock", min_length=1, max_length=120)
    provider: Literal["mock"] = "mock"
    secret: str = Field(default="", max_length=4096)


class ApplicationInput(Input):
    name: str = Field(min_length=1, max_length=120)
    group_id: str | None = None
    connection_id: str
    project_id: str | None = None


class KeyInput(Input):
    application_id: str
    service_account_id: str | None = None


class BudgetInput(Input):
    scope_id: str
    hard_limit: int = Field(ge=0, le=10**15)
    version: int = Field(default=0, ge=0)
    unit: Literal["money", "tokens", "requests"] = "money"
    cadence: Literal["month", "day"] = "month"


class PauseInput(Input):
    paused: bool


class RoleInput(Input):
    name: str = Field(min_length=1, max_length=80)
    permissions: list[str] = Field(max_length=10)


class MembershipInput(Input):
    subject: str = Field(min_length=1, max_length=255)
    role: str
    scope_id: str | None = None


class MoveInput(Input):
    parent_id: str | None = None


class ServiceAccountInput(Input):
    name: str = Field(min_length=1, max_length=120)
    application_id: str


def record(row):
    excluded = {"encrypted_secret", "digest", "response"}
    return {c.name: getattr(row, c.name) for c in row.__table__.columns if c.name not in excluded}


def find(s, cls, tenant, identifier):
    row = s.scalar(select(cls).where(cls.tenant_id == tenant, cls.id == identifier))
    if row is None:
        raise HTTPException(404, "resource_not_found")
    return row


def audit(s, tenant, subject, action, target):
    s.add(Audit(tenant_id=tenant, actor=subject, action=action, target=target))


@app.get("/health")
def health():
    return {"status": "alive", "identity_mode": "development" if settings().dev_identity else "oidc"}


@app.get("/ready")
def ready():
    with transaction() as s:
        s.execute(text("SELECT 1"))
    return {"status": "ready"}


@app.post("/api/v1/organisations", status_code=201)
def create_org(body: OrganisationInput, subject=Depends(identity)):
    # Tenant registry is global. Tenant data insertion uses transaction-local RLS context.
    with transaction() as s:
        tenant = Tenant(name=body.name, content_days=body.content_days)
        s.add(tenant)
        s.flush()
        tid = tenant.id
        if s.bind.dialect.name == "postgresql":
            s.execute(text("SELECT set_config('app.tenant_id', :id, true)"), {"id": tid})
        s.add(Membership(tenant_id=tid, subject=subject, role="owner"))
        s.add(Budget(tenant_id=tid, scope_id=tid, period=month(), hard_limit=body.budget_microusd))
        audit(s, tid, subject, "organisation.created", tid)
        return {"id": tid, "name": tenant.name, "content_days": tenant.content_days}


@app.get("/api/v1/organisations/{tenant}")
def organisation(tenant: str, subject=Depends(identity)):
    authorize(tenant, subject)
    with transaction(tenant) as s:
        return record(s.get(Tenant, tenant))


@app.post("/api/v1/organisations/{tenant}/groups", status_code=201)
def create_group(tenant: str, body: GroupInput, subject=Depends(identity)):
    authorize(tenant, subject, True, body.parent_id)
    with transaction(tenant) as s:
        ancestry(s, tenant, body.parent_id)
        group = Group(tenant_id=tenant, name=body.name, parent_id=body.parent_id)
        s.add(group)
        s.flush()
        audit(s, tenant, subject, "group.created", group.id)
        return record(group)


@app.post("/api/v1/organisations/{tenant}/provider-connections", status_code=201)
def create_connection(tenant: str, body: ProviderInput, subject=Depends(identity)):
    authorize(tenant, subject, True)
    with transaction(tenant) as s:
        connection = Connection(tenant_id=tenant, name=body.name, provider=body.provider,
                                encrypted_secret=encrypt(body.secret) if body.secret else "")
        s.add(connection)
        s.flush()
        audit(s, tenant, subject, "provider.created", connection.id)
        return record(connection)


@app.post("/api/v1/organisations/{tenant}/applications", status_code=201)
def create_application(tenant: str, body: ApplicationInput, subject=Depends(identity)):
    authorize(tenant, subject, True, body.group_id)
    with transaction(tenant) as s:
        ancestry(s, tenant, body.group_id)
        find(s, Connection, tenant, body.connection_id)
        if body.project_id:
            project = find(s, Project, tenant, body.project_id)
            if project.group_id != body.group_id:
                raise HTTPException(409, "project_billing_path_mismatch")
        application = Application(tenant_id=tenant, **body.model_dump())
        s.add(application)
        s.flush()
        audit(s, tenant, subject, "application.created", application.id)
        return record(application)


@app.post("/api/v1/organisations/{tenant}/virtual-keys", status_code=201)
def create_key(tenant: str, body: KeyInput, subject=Depends(identity)):
    with transaction(tenant) as s:
        application = find(s, Application, tenant, body.application_id)
        authorize(tenant, subject, True, application.group_id)
        service_account = None
        if body.service_account_id:
            service_account = find(s, ServiceAccount, tenant, body.service_account_id)
            if service_account.application_id != application.id or not service_account.active:
                raise HTTPException(403, "invalid_service_account")
        else:
            service_account = ServiceAccount(tenant_id=tenant, name=application.name + " service",
                                             application_id=application.id)
            s.add(service_account)
            s.flush()
        secret, hashed = issue_secret()
        key = Key(tenant_id=tenant, application_id=application.id, service_account_id=service_account.id,
                  digest=hashed, prefix=secret[:12])
        s.add(key)
        s.flush()
        audit(s, tenant, subject, "key.issued", key.id)
        return {**record(key), "secret": secret}


@app.post("/api/v1/organisations/{tenant}/virtual-keys/{key_id}/revoke")
def revoke_key(tenant: str, key_id: str, subject=Depends(identity)):
    authorize(tenant, subject, True)
    with transaction(tenant) as s:
        key = find(s, Key, tenant, key_id)
        key.revoked = True
        audit(s, tenant, subject, "key.revoked", key.id)
        return {"revoked": True, "effective": "immediate for new authentication; in-flight requests may finish"}


@app.post("/api/v1/organisations/{tenant}/virtual-keys/{key_id}/rotate")
def rotate_key(tenant: str, key_id: str, subject=Depends(identity)):
    authorize(tenant, subject, True)
    with transaction(tenant) as s:
        old = find(s, Key, tenant, key_id)
        old.revoked = True
        secret, hashed = issue_secret()
        key = Key(tenant_id=tenant, application_id=old.application_id, service_account_id=old.service_account_id,
                  digest=hashed, prefix=secret[:12])
        s.add(key)
        s.flush()
        audit(s, tenant, subject, "key.rotated", key.id)
        return {**record(key), "secret": secret}


@app.post("/api/v1/organisations/{tenant}/budgets")
def budget(tenant: str, body: BudgetInput, subject=Depends(identity)):
    authorize(tenant, subject, True)
    with transaction(tenant) as s:
        period = month() if body.cadence == "month" else datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if body.scope_id != tenant:
            group = s.scalar(select(Group).where(Group.tenant_id == tenant, Group.id == body.scope_id))
            if group is None:
                find(s, Application, tenant, body.scope_id)
        # Root first, matching the admission lock order.
        s.scalar(select(Budget).where(Budget.tenant_id == tenant, Budget.scope_id == tenant,
                                     Budget.period == month(), Budget.unit == "money").with_for_update())
        row = s.scalar(select(Budget).where(Budget.tenant_id == tenant, Budget.scope_id == body.scope_id,
                                           Budget.period == period, Budget.unit == body.unit).with_for_update())
        if row:
            if row.version != body.version:
                raise HTTPException(409, "version_conflict")
            row.hard_limit = body.hard_limit
            row.version += 1
        else:
            if body.version != 0:
                raise HTTPException(409, "version_conflict")
            row = Budget(tenant_id=tenant, scope_id=body.scope_id, period=period, unit=body.unit,
                         hard_limit=body.hard_limit)
            s.add(row)
        s.flush()
        audit(s, tenant, subject, "budget.updated", row.id)
        return record(row)


@app.patch("/api/v1/organisations/{tenant}/applications/{application_id}")
def pause(tenant: str, application_id: str, body: PauseInput, subject=Depends(identity)):
    authorize(tenant, subject, True)
    with transaction(tenant) as s:
        row = find(s, Application, tenant, application_id)
        row.paused = body.paused
        audit(s, tenant, subject, "application.pause_changed", row.id)
        return {**record(row), "notice": "New admissions stop; in-flight requests may finish."}


CATALOGUE = {"groups": Group, "applications": Application, "virtual-keys": Key,
             "provider-connections": Connection, "budgets": Budget, "requests": Request,
             "audit-events": Audit, "notifications": Event, "memberships": Membership, "roles": Role,
             "projects": Project, "service-accounts": ServiceAccount}


@app.post("/api/v1/organisations/{tenant}/roles", status_code=201)
def create_role(tenant: str, body: RoleInput, subject=Depends(identity)):
    authorize(tenant, subject, permission="roles.manage")
    if body.name in TEMPLATES or not set(body.permissions) <= PERMISSIONS:
        raise HTTPException(422, "invalid_role")
    with transaction(tenant) as s:
        if s.scalar(select(Role).where(Role.tenant_id == tenant, Role.name == body.name)):
            raise HTTPException(409, "role_name_exists")
        role = Role(tenant_id=tenant, name=body.name, permissions=sorted(set(body.permissions)))
        s.add(role)
        s.flush()
        audit(s, tenant, subject, "role.created", role.id)
        return record(role)


@app.post("/api/v1/organisations/{tenant}/memberships")
def assign_membership(tenant: str, body: MembershipInput, subject=Depends(identity)):
    actor_role = authorize(tenant, subject, scope=body.scope_id, permission="members.manage")
    with transaction(tenant) as s:
        # Serialize owner lifecycle and membership modifications for this tenant.
        s.scalar(select(Tenant).where(Tenant.id == tenant).with_for_update())
        ancestry(s, tenant, body.scope_id, check_pause=False)
        if body.role not in TEMPLATES:
            find(s, Role, tenant, body.role)
        # Only a root owner may delegate administrator/custom permissions.
        if actor_role != "owner" and body.role not in ("manager", "member", "auditor"):
            raise HTTPException(403, "cannot_delegate_privilege")
        if body.role == "owner" and body.scope_id:
            raise HTTPException(422, "owner_must_be_root")
        row = s.scalar(select(Membership).where(Membership.tenant_id == tenant,
                                                 Membership.subject == body.subject).with_for_update())
        if row:
            if row.role == "owner" and actor_role != "owner":
                raise HTTPException(403, "cannot_modify_owner")
            if row.role == "owner" and body.role != "owner":
                owners = list(s.scalars(select(Membership).where(Membership.tenant_id == tenant,
                                                                Membership.role == "owner")))
                if len(owners) <= 1:
                    raise HTTPException(409, "last_owner_protected")
            row.role, row.scope_id = body.role, body.scope_id
        else:
            row = Membership(tenant_id=tenant, **body.model_dump())
            s.add(row)
        s.flush()
        audit(s, tenant, subject, "membership.assigned", row.id)
        return record(row)


@app.post("/api/v1/organisations/{tenant}/projects", status_code=201)
def create_project(tenant: str, body: GroupInput, subject=Depends(identity)):
    authorize(tenant, subject, True, body.parent_id)
    with transaction(tenant) as s:
        ancestry(s, tenant, body.parent_id)
        project = Project(tenant_id=tenant, name=body.name, group_id=body.parent_id)
        s.add(project)
        s.flush()
        audit(s, tenant, subject, "project.created", project.id)
        return record(project)


@app.post("/api/v1/organisations/{tenant}/service-accounts", status_code=201)
def create_service_account(tenant: str, body: ServiceAccountInput, subject=Depends(identity)):
    authorize(tenant, subject, True)
    with transaction(tenant) as s:
        find(s, Application, tenant, body.application_id)
        account = ServiceAccount(tenant_id=tenant, **body.model_dump())
        s.add(account)
        s.flush()
        audit(s, tenant, subject, "service_account.created", account.id)
        return record(account)


@app.patch("/api/v1/organisations/{tenant}/groups/{group_id}")
def move_group(tenant: str, group_id: str, body: MoveInput, subject=Depends(identity)):
    # Only root governors can move cost paths across delegated boundaries.
    authorize(tenant, subject, True)
    with transaction(tenant) as s:
        # Match admission's root lock before changing the ancestry it resolves.
        s.scalar(select(Budget).where(Budget.tenant_id == tenant, Budget.scope_id == tenant,
                                     Budget.period == month(), Budget.unit == "money").with_for_update())
        group = find(s, Group, tenant, group_id)
        s.scalar(select(Tenant).where(Tenant.id == tenant).with_for_update())
        path = ancestry(s, tenant, body.parent_id, check_pause=False)
        if group_id in path:
            raise HTTPException(409, "hierarchy_cycle")
        group.parent_id = body.parent_id
        audit(s, tenant, subject, "group.moved", group.id)
        return record(group)


@app.post("/api/v1/organisations/{tenant}/requests/{request_id}/reconcile-conservative")
def reconcile(tenant: str, request_id: str, subject=Depends(identity)):
    role = authorize(tenant, subject, True)
    if role not in ("owner", "admin"):
        raise HTTPException(403, "permission_denied")
    with transaction(tenant) as s:
        request = find(s, Request, tenant, request_id)
        if request.state not in ("uncertain", "completed"):
            raise HTTPException(409, "request_not_uncertain")
        if request.state == "completed" and request.cost != request.bound:
            raise HTTPException(409, "request_already_settled_with_actual_usage")
        bound = request.bound
        audit(s, tenant, subject, "request.conservative_reconciliation_requested", request_id)
    # Always charges the entire bound. No unverified cost may release uncertain funds.
    settle(tenant, request_id, bound)
    return {"id": request_id, "state": "completed", "cost_provenance": "conservative_bound",
            "cost_microusd": bound}


@app.get("/api/v1/organisations/{tenant}/usage")
def usage(tenant: str, subject=Depends(identity)):
    authorize(tenant, subject)
    with transaction(tenant) as s:
        root = s.scalar(select(Budget).where(Budget.tenant_id == tenant, Budget.scope_id == tenant,
                                            Budget.period == month(), Budget.unit == "money"))
        return {"period": month(), "currency": "USD", "provider_mode": "mock",
                "spent_microusd": root.spent if root else 0, "reserved_microusd": root.reserved if root else 0,
                "hard_limit_microusd": root.hard_limit if root else 0}


@app.get("/api/v1/organisations/{tenant}/requests/{request_id}")
def request_detail(tenant: str, request_id: str, subject=Depends(identity)):
    authorize(tenant, subject)
    with transaction(tenant) as s:
        request = find(s, Request, tenant, request_id)
        return {"request": record(request), "provider_mode": "mock", "price_version": "mock-v1",
                "content_retained": False,
                "reservations": [record(row) for row in s.scalars(select(Reservation).where(
                    Reservation.tenant_id == tenant, Reservation.request_id == request_id))],
                "ledger": [record(row) for row in s.scalars(select(Ledger).where(
                    Ledger.tenant_id == tenant, Ledger.request_id == request_id).order_by(Ledger.created_at))]}


@app.get("/api/v1/organisations/{tenant}/{resource}")
def listing(tenant: str, resource: str, offset: int = 0, limit: int = 50, subject=Depends(identity)):
    authorize(tenant, subject)
    if resource not in CATALOGUE or offset < 0 or not 1 <= limit <= 100:
        raise HTTPException(400, "invalid_query")
    cls = CATALOGUE[resource]
    with transaction(tenant) as s:
        return {"items": [record(row) for row in s.scalars(select(cls).where(cls.tenant_id == tenant)
                     .order_by(cls.id).offset(offset).limit(limit))], "offset": offset, "limit": limit}
