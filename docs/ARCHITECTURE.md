# Architecture and current scope

Next.js console → FastAPI control API → PostgreSQL. Customer server → independent FastAPI gateway → deterministic provider. Redis admits shared mock capacity. PostgreSQL outbox → Celery → local Mailpit. The dashboard is not required for gateway operation.

Shared domain modules own security, database transactions and accounting. Provider and request schemas have separate packages. Migration creates forced RLS, composite tenant references and append-only audit/ledger triggers. Secrets are encrypted before persistence and stripped from list views; keys are randomly generated and hashed.

Spend Contracts add workflow-level escrow above individual requests. Contract creation reserves applicable tenant budgets once; child requests atomically allocate from the contract, and closing settles aggregate actuals while releasing unused capacity. Signed contract tokens are scoped and bound to the already-authenticated virtual key and application. See `SPEND_CONTRACTS.md`.

The working target is a first local vertical slice. See PROGRESS.md for gate status. Full hierarchy lifecycle, real providers, content storage, advanced governance, premium analysis and production qualification are separate incomplete milestones, not implied by the presence of folders.
