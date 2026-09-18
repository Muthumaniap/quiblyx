# Quilblyx

Local, mock-backed multi-tenant LLM gateway and administration console. Built with Next.js/TypeScript, FastAPI, PostgreSQL, Redis and Celery. **Development implementation, not production-qualified.** All provider output and pricing are deterministic mocks. No paid provider calls are made.

## Start locally

Requirements: Docker Engine/Desktop with Compose v2; Python 3.12+ and uv to generate local configuration. Node 22+ is needed only for host-side web development.

```sh
uv sync --locked
uv run python scripts/init_env.py
docker compose up --build -d
docker compose logs -f migrate control gateway worker
```

Open http://localhost:3000. Read `DEV_LOGIN_TOKEN` from your local `.env` and enter it in the console (development only). Create an organisation with an explicit retention choice and a monthly micro-USD budget, then a mock provider, application and virtual key. Save the one-time virtual key in your **server's** environment. The console never embeds it into a gateway request.

```sh
export VIRTUAL_KEY='your-once-visible-key'
curl http://localhost:8001/v1/chat/completions \
  -H "Authorization: Bearer $VIRTUAL_KEY" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: example-1" \
  -d '{"model":"org-balanced","messages":[{"role":"user","content":"Hello"}],"max_tokens":64}'
```

PowerShell: set `$env:VIRTUAL_KEY` and use `Invoke-RestMethod` or `curl.exe`. Refresh Overview and Requests to see actual database accounting. Lower the budget using the versioned budget endpoint to test refusal. `1 USD = 1,000,000 micro-USD`.

- Console: http://localhost:3000
- Control OpenAPI: http://localhost:8000/docs
- Gateway OpenAPI: http://localhost:8001/docs
- Local email sink: http://localhost:8025
- Health/readiness: `/health`, `/ready` on both Python services

Docker is not available in the initial development host. Clean Compose startup is not yet verified; see [progress](docs/PROGRESS.md) for actual checks and limitations.

## Host-side development

Start dependencies with `docker compose up -d postgres redis mailpit`, then:

```sh
uv run alembic upgrade head
uv run uvicorn services.control_api.main:app --reload --port 8000
uv run uvicorn services.gateway.main:app --reload --port 8001
uv run celery -A services.worker.main worker --beat --loglevel=INFO
```

Run each long-lived process in a separate terminal. Celery workers should run under Linux/Compose; Windows Celery is not a supported deployment. In `apps/web`: `npm ci`, then `npm run dev`.

## Verification

```sh
uv run ruff check .
uv run pytest -q
# With a migrated PostgreSQL database and Redis running:
INTEGRATION=1 uv run pytest -q
cd apps/web
npm ci
npm run build
```

PowerShell integration flag: `$env:INTEGRATION='1'`. The database user must be non-superuser/NOBYPASSRLS; using postgres makes isolation tests invalid. Tests create isolated random organisations and do not truncate a shared database. Use a dedicated test database for repeated runs. Unit-only success does not establish concurrent accounting correctness.

## Behaviour and limits

Budgets reserve a conservative maximum before dispatch across root/group/application monthly scopes. PostgreSQL, not Redis, protects money. Same tenant/key/idempotency key plus a different payload returns 409. Completed non-stream mock requests replay safely. Streams cannot replay; duplicate dispatch is refused. Timeouts, partial streams and disconnects retain reservations until reconciliation. No automatic fallback or retries are enabled.

Revocation takes effect on the next database authentication lookup; in-flight requests may finish. Child scopes cannot increase an ancestor's monetary allowance. RLS plus composite foreign keys provide database tenant defence; application queries also filter tenant. Prompt content is not stored. The selected retention preference is recorded for future content-storage support.

See [architecture](docs/ARCHITECTURE.md), [provider coverage](docs/PROVIDER_SUPPORT.md), [decisions](docs/adr/0001-budget-authority.md), [recovery](docs/runbooks/recovery.md), and [deployment prerequisites](infra/deployment/README.md). Real integrations, full role lifecycle, OIDC browser sessions, premium analysis, restoration/load/security qualification and pilot deployment remain incomplete.

Stop services with `docker compose down`. Volumes persist; do not delete them to recover accounting failures.
