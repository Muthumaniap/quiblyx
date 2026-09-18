import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, BigInteger, DateTime, JSON, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def uid():
    return str(uuid.uuid4())


def now():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Record(Base):
    __abstract__ = True
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(120))
    content_days: Mapped[int] = mapped_column(Integer)
    metadata_days: Mapped[int] = mapped_column(Integer, default=90)


class Membership(Record):
    __tablename__ = "memberships"
    subject: Mapped[str] = mapped_column(String(255), index=True)
    role: Mapped[str] = mapped_column(String(80), default="owner")
    scope_id: Mapped[str | None] = mapped_column(String(36))
    __table_args__ = (UniqueConstraint("tenant_id", "subject"),)


class Group(Record):
    __tablename__ = "groups"
    name: Mapped[str] = mapped_column(String(120))
    parent_id: Mapped[str | None] = mapped_column(String(36))
    paused: Mapped[bool] = mapped_column(default=False)


class Role(Record):
    __tablename__ = "roles"
    name: Mapped[str] = mapped_column(String(80))
    permissions: Mapped[list] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint("tenant_id", "name"),)


class Project(Record):
    __tablename__ = "projects"
    name: Mapped[str] = mapped_column(String(120))
    group_id: Mapped[str | None] = mapped_column(String(36))


class ServiceAccount(Record):
    __tablename__ = "service_accounts"
    name: Mapped[str] = mapped_column(String(120))
    application_id: Mapped[str] = mapped_column(String(36))
    active: Mapped[bool] = mapped_column(default=True)


class Connection(Record):
    __tablename__ = "provider_connections"
    name: Mapped[str] = mapped_column(String(120))
    provider: Mapped[str] = mapped_column(String(30), default="mock")
    encrypted_secret: Mapped[str] = mapped_column(String, default="")


class Application(Record):
    __tablename__ = "applications"
    name: Mapped[str] = mapped_column(String(120))
    group_id: Mapped[str | None] = mapped_column(String(36))
    connection_id: Mapped[str] = mapped_column(String(36))
    paused: Mapped[bool] = mapped_column(default=False)
    project_id: Mapped[str | None] = mapped_column(String(36))


class Key(Base):
    # Authentication registry intentionally outside RLS: hash lookup binds tenant.
    __tablename__ = "virtual_keys"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    application_id: Mapped[str] = mapped_column(String(36))
    digest: Mapped[str] = mapped_column(String(64), unique=True)
    prefix: Mapped[str] = mapped_column(String(16))
    revoked: Mapped[bool] = mapped_column(default=False)
    service_account_id: Mapped[str | None] = mapped_column(String(36))


class Budget(Record):
    __tablename__ = "budgets"
    scope_id: Mapped[str] = mapped_column(String(36))
    period: Mapped[str] = mapped_column(String(10))
    unit: Mapped[str] = mapped_column(String(10), default="money")
    hard_limit: Mapped[int] = mapped_column(BigInteger)
    spent: Mapped[int] = mapped_column(BigInteger, default=0)
    reserved: Mapped[int] = mapped_column(BigInteger, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (UniqueConstraint("tenant_id", "scope_id", "period", "unit"),
                      CheckConstraint("spent >= 0 AND reserved >= 0 AND hard_limit >= 0"))


class Request(Record):
    __tablename__ = "requests"
    application_id: Mapped[str] = mapped_column(String(36))
    key_id: Mapped[str] = mapped_column(String(36))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    payload_hash: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(30), default="reserved")
    bound: Mapped[int] = mapped_column(BigInteger)
    cost: Mapped[int | None] = mapped_column(BigInteger)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    response: Mapped[dict | None] = mapped_column(JSON)
    model: Mapped[str] = mapped_column(String(100), default="mock-text-v1")
    period: Mapped[str] = mapped_column(String(7), default=lambda: now().strftime("%Y-%m"))
    __table_args__ = (UniqueConstraint("tenant_id", "key_id", "idempotency_key"),)


class Reservation(Record):
    __tablename__ = "reservations"
    request_id: Mapped[str] = mapped_column(String(36), index=True)
    budget_id: Mapped[str] = mapped_column(String(36))
    amount: Mapped[int] = mapped_column(BigInteger)
    settled: Mapped[bool] = mapped_column(default=False)
    __table_args__ = (UniqueConstraint("request_id", "budget_id"),)


class Ledger(Record):
    __tablename__ = "ledger_entries"
    request_id: Mapped[str] = mapped_column(String(36))
    budget_id: Mapped[str] = mapped_column(String(36))
    amount: Mapped[int] = mapped_column(BigInteger)
    event: Mapped[str] = mapped_column(String(40))
    __table_args__ = (UniqueConstraint("request_id", "budget_id", "event"),)


class Event(Record):
    __tablename__ = "outbox_events"
    kind: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSON)
    delivered: Mapped[bool] = mapped_column(default=False)
    dedup_key: Mapped[str | None] = mapped_column(String(150), unique=True)


class Audit(Record):
    __tablename__ = "audit_events"
    actor: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(80))
    target: Mapped[str] = mapped_column(String(36))
