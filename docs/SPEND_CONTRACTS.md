# AI Spend Contracts

Spend Contracts reserve a maximum execution envelope for an entire AI workflow. They are the first implementation of Quiblyx's proposed USP: every AI task receives a spending limit, permission boundary and audit receipt before it runs.

## Invariants

At contract creation, Quiblyx atomically reserves the requested maximum against every applicable organisation, group and application budget. Money, token and request-step reservations use the same period rows as ordinary gateway traffic.

For an active contract:

`settled contract usage + outstanding step allocations <= contract maximum`

The database locks the contract row before allocating a step. Parallel calls therefore share one limit. Contract-backed requests do not reserve tenant budgets a second time. Closing the contract converts the escrow into actual spend and releases unused capacity in one transaction.

Timeouts, disconnected streams and ambiguous dispatch retain their child allocation. A contract cannot close while an allocation is outstanding. An owner/admin may conservatively reconcile such a request at its full reserved cost and token bound; this never treats elapsed time as proof of zero cost.

## Token and request binding

Creation returns a signed, expiring token once. The JWT is restricted to `spend:allocate`, carries the tenant/application/key/contract identity and is checked against current database state on every step. Rotation increments a stored version, invalidating the prior token immediately. Revocation also invalidates new steps. The gateway independently authenticates the virtual key and requires both principals to match.

Use a distinct `CONTRACT_SIGNING_KEY` in deployed environments. Existing local environments without it derive a domain-separated signing key from `SECRET_KEY` for backward-compatible development only.

Gateway headers:

```text
Authorization: Bearer <virtual key>
X-Spend-Contract: <one-time-issued contract token>
X-Contract-Step: answer-generation
Idempotency-Key: ticket-42-answer
```

## Lifecycle

1. `POST /api/v1/organisations/{tenant}/spend-contracts` reserves the envelope.
2. Gateway calls allocate and settle named steps.
3. `GET .../spend-contracts/{id}` returns remaining capacity, allocations, reservations and immutable ledger entries.
4. `POST .../{id}/close` settles actual totals and releases the balance. It fails while uncertain steps remain.
5. `POST .../{id}/revoke` stops new steps. With no outstanding steps it closes and releases capacity immediately.
6. `POST .../{id}/rotate-token` invalidates the previous token and returns a replacement once.

Python and TypeScript server examples are in `packages/contracts/spend_contract_example.*`.

## Honest v1 limitations

- Text requests through the deterministic mock provider are qualified. Real-provider price bounds and usage reconciliation are not.
- `allowed_tools` is stored and fail-closed, but the current chat schema rejects tool calls globally. Tool-specific enforcement arrives with tool-capable provider contracts.
- `data_region` is recorded in the receipt; only the local mock route exists, so cross-region routing is not yet applicable.
- Contracts expire cryptographically, preventing new steps. An automated expiry/reconciliation worker is still required to close expired contracts and release only proven-unused capacity.
- Contract expansion and human approval workflows are not implemented. Create a new contract rather than silently increasing an active maximum.
