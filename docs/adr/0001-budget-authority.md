# ADR 0001: single-region PostgreSQL authority

Accepted 2026-09-17. Preserve the proposed FastAPI/SQLAlchemy/Alembic, Next.js, Redis and Celery stack.

Money uses integer USD micro-units. Admission locks the tenant's current UTC monthly root budget first, then applicable budget rows by ID, and creates durable reservations and ledger entries in one transaction. Settlement locks the original root period first and updates balances and ledger atomically. This deliberately serializes a tenant's admissions until measurements justify a more concurrent design. Different tenants proceed independently.

Redis only governs short-window mock upstream capacity. Redis failure stops new dispatch and compensates undispatched reservations. PostgreSQL failure stops admission. No database transaction spans a provider call.

The request row currently also represents its only attempt. Real fallback is disabled until attempts have independent reservation and price snapshots. Dispatched/uncertain records retain their bounds indefinitely; elapsed time never proves non-billing. Admission-time period references survive rollover.

RLS is forced on tenant data with transaction-local context. Tenant registry and hashed-key authentication registry are narrow global tables with server-side scoped queries; they must not be exposed through generic data endpoints. Compose uses a non-superuser without BYPASSRLS. Composite foreign keys prevent cross-tenant references independently of API checks.

Current scope: UTC daily/monthly monetary, token and request budgets, fixed mock aliases, zero customer-content persistence. Monthly root monetary budget is mandatory; existing applicable cap kinds must be renewed explicitly each period or admission stops. Provider concurrency, configurable rate policies, policy versioning and real provider pricing remain acceptance blockers.

References consulted 2026-09-17: https://docs.sqlalchemy.org/en/20/orm/session_basics.html and https://docs.sqlalchemy.org/en/20/orm/session_api.html.
