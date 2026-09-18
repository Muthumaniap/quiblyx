# ADR 0002: explicit local adapters

Accepted 2026-09-17. All provider traffic is deterministic local mock code. No external provider endpoint is configurable yet, avoiding an unqualified SSRF surface. Synthetic input units count UTF-8 bytes plus message overhead; output counts characters, capped by max_tokens. Prices are 1/2 micro-USD per input/output unit under mock-v1, not real model tokenization or pricing.

Fernet encrypts stored provider credentials using a separately supplied environment key. This is a development secret-manager boundary, not cloud KMS. Generate a random key for every checkout; never use it for production credentials. Production requires managed key versions, rotation and recovery procedures.

The local console accepts an explicit development bearer credential and keeps it only in memory. The backend can verify RS256 OIDC bearer tokens against configured JWKS/issuer/audience, but browser OIDC sessions and tenant provisioning are not complete. Production cannot use DEV_IDENTITY. Local mock email targets only Mailpit's local-admin mailbox. SMTP delivery is at-least-once: a crash after send may duplicate a message even with stable Message-ID. 70/85/95% committed threshold events are created atomically during admission and deduplicated per budget/period/threshold. Delivery does not control enforcement.

Retention is recorded explicitly but content storage is disabled: no user messages are retained. Only the provider's constant mock output is stored for idempotent replay. Metadata deletion must preserve accounting evidence and needs a separate implementation.

Next.js 15.5.24 was initially selected from https://nextjs.org/blog/august-2026-security-release (checked 2026-09-17). npm audit then identified vulnerable transitive PostCSS versions; Next.js was updated to 16.3.5. The resulting locked dependency tree reports zero npm advisories, and production build/type checking passed. Authentication reference: https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/.
