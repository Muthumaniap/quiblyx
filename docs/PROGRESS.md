# Implementation progress

## Branding update — 2026-09-17
- Owner supplied the name Quilblyx and PNG logo references.
- Added an SVG interface adaptation of the blue Q, sidebar wordmark, favicon, page metadata and blue/navy theme. Original references preserved.
- Web container now includes public brand assets. See `docs/BRANDING.md`.
- Quilblyx web production build/TypeScript and backend lint/import checks passed. Visual browser inspection remains unverified.

Specification read in full on 2026-09-17. Existing repository contained only the specification and a one-line README. No existing application was replaced.

Milestones are acceptance gates, not claims based on code being present.

## M0 — in progress
- [x] Inspect repository and complete specification; no AGENTS.md found.
- [x] Python services, shared packages, Alembic, Next.js TypeScript console.
- [x] Compose PostgreSQL, Redis AOF, Mailpit, migration, control, gateway, worker and web services.
- [x] Fresh generated local secrets, encrypted provider-secret abstraction, deterministic mock provider.
- [x] CI definition for lint, database migration/integration tests and web build.
- [ ] Clean Compose startup verified (Docker unavailable on this host).
- [x] Python/npm lockfiles generated, console production build and TypeScript verified.
- [x] Fresh non-superuser PostgreSQL migration and full HTTP smoke verified outside Compose.

## M1 — partial
- [x] Organisation creation with explicit retention choice; identities and tenant memberships.
- [x] OIDC bearer verification boundary and explicitly enabled development identity.
- [x] Nested groups and inherited scoped checks; composite tenant foreign keys and forced PostgreSQL RLS migration.
- [x] Application keys: one-time issue, hashed lookup, rotate, revoke; no authentication cache.
- [x] API-backed organisation/provider/application/group/key console.
- [x] Custom role creation, scoped membership assignments, projects, distinct service accounts and last-owner protection.
- [x] Tenant API/RLS isolation, scope boundaries, role/key revocation and hierarchy-cycle tests.
- [ ] Full role editing/removal, multiple scoped bindings per member, provisioning/deprovisioning lifecycle and administrative screens.
- [ ] Browser OIDC/SSO/MFA session workflow.
- [ ] Isolation gates for jobs/cache/objects and full browser E2E.

## M2 — core acceptance flow verified; dashboard browser gate outstanding
- [x] Deterministic text and SSE mock gateway, schema validation, conservative synthetic price bounds.
- [x] Atomic parent/child reservations, immutable ledger, settlement, audit and transactional outbox.
- [x] Request idempotency, payload conflict rejection, immediate revoked-key lookup.
- [x] Usage, request history, reserved/settled dashboard with real API state.
- [x] PostgreSQL concurrency and RLS integration tests written.
- [x] Real PostgreSQL/Redis suite executed; shared parent concurrency uses different keys.
- [x] Real HTTP organisation → provider → application → key → response → usage → budget refusal passed.
- [x] Request detail API/UI exposes original reservations and immutable ledger.
- [ ] Browser interaction/visual verification (no browser connected to computer-use tool).

## M3 — partial mock contract only
- [x] Mock normal/timeout/pre-dispatch/partial-stream behaviours.
- [x] Unsupported request fields and capabilities rejected before dispatch.
- [ ] Real providers, fixtures, current price catalogue, upstream quota semantics, retry/circuit breaker.

## M4 — partial
- [x] Parent monetary budgets and application pause; shared mock quota pool via atomic Redis Lua.
- [x] Optimistic budget mutations; reductions preserve existing reservations.
- [x] Daily/monthly monetary, token and request caps; renewal fails closed when an inherited cap expires.
- [x] 70/85/95% committed threshold events, tenant/period deduplication, in-app records, outbox worker and local SMTP delivery.
- [ ] Per-scope concurrency and request-rate configuration, routing policies, fallback, simulator, notification settings/recipients/cooldowns.

## M5 — partial
- [x] Dispatched uncertainty never expires automatically; no partial-stream retries.
- [x] Admission-period reservation references; duplicate-settlement uniqueness.
- [x] No customer prompt/response content persisted; mock constant response can be replayed.
- [x] Audited owner/admin conservative reconciliation consumes the full uncertain bound; undispatched recovery cannot dispatch later.
- [x] Failure tests: Redis outage, cancellation, partial stream, timeout, duplicate settlement and rollover.
- [x] Real backup/restore into an isolated database followed by per-tenant ledger/balance verification.
- [ ] Automatic crash recovery sweep, real-provider reconciliation, database failover exercise, retention/export/object lifecycle.

## M6 — not started
- [ ] Entitlements, opt-in analysis, separate budgets, recommendations, evaluations, review, rollback.

## M7 — not started
- [ ] Real-provider qualification, security review, measured load/failover targets, pilot, production signoff.
- [x] Local dependency scans and isolated PostgreSQL restore drill (not production qualification).
- [ ] Public deployment and paid calls remain unauthorised; none performed.

## Evidence log
- Python dependencies resolved and installed with uv; compatible Redis client 5.2.1 chosen for Celery 5.5.3.
- Ruff checks, imports, OpenAPI generation and Compose YAML parsing passed.
- Python dependencies were audited; affected cryptography, PyJWT, pytest and Starlette were upgraded with FastAPI. Final audit reports zero known vulnerabilities. Next.js updated to 16.3.5 following PostCSS advisories; npm audit reports zero vulnerabilities.
- 23 tests pass on PostgreSQL 17.6 and Redis 7.4.5, including Hypothesis state-machine sequences and parallel admissions/settlement. Tests were rerun against a freshly migrated independent database. Two test-client deprecation warnings remain.
- `npm run build` passes with TypeScript checking. HTTP GET on console returns 200. Browser visual and interaction testing is NOT claimed.
- `scripts/smoke.py` passed against real local HTTP services: synthetic spend 69 micro-USD, reserved 0, limit 100; second request refused with 429.
- PostgreSQL custom-format dump restored into a separate database: 55 budgets across 53 tenant contexts matched unsettled reservations and settlement ledger entries at that checkpoint.
- Real outbox processing delivered 21 threshold messages to local Mailpit; no external email sent. Worker replay is tested through an injected SMTP sink separately.
- A 500-request simultaneous stream burst completed 500/500 with HTTP 200, spent 34,500 synthetic micro-USD and left zero reservations. On this 8-logical-CPU Windows host it took 35.965 seconds (13.9 completions/sec); admission p95 was 16,019.879 ms. This MISSES the proposed 100 RPS / <100 ms admission target and is not a sustained-throughput benchmark. Evidence: `docs/evidence/load-500.json`. Tenant admission serialization and contention require profiling before production qualification.
- Host PATH lacked Python/Node/Docker. Existing Python 3.13 and bundled Node were located. Docker is not installed at standard location.

## Next steps
Connect a browser and verify onboarding/budgets/key lifecycle/request details visually. Run clean Compose startup and CI on Linux. Complete M1 identity/session and lifecycle gaps, then real-provider offline contracts and price/capability qualification (M3). Advanced governance, content lifecycle and premium analysis remain unimplemented; absence of credentials is not presented as the reason for unfinished offline implementation.
