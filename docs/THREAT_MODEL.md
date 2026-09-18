# Initial threat model

Trust boundaries: untrusted caller → gateway authentication; human identity → control authorization; application role → PostgreSQL RLS; stored secret → process encryption key; database outbox → SMTP sink. Provider output and user prompt data have no administrative authority.

Implemented defences:

- Virtual keys have 256 bits of randomness; database stores SHA-256 digests and public prefixes. Every new admission rechecks revocation. Actual provider secrets are never returned by list/create endpoints or audit payloads.
- Every tenant record uses a tenant UUID. Forced RLS and composite references supplement application filters. Global identity registries are intentionally narrow and not exposed by generic listing.
- JWT bearer verification pins RS256, issuer, audience, subject and expiry. Development identity requires explicit enablement and a separately generated token. Browser login/session management and OIDC integration testing remain open.
- Tenant scoped delegation cannot reach sibling/root resources. Root-only owner delegation and serialised last-owner checks prevent easy privilege escalation.
- Accounting takes authoritative database locks. Redis is not a money authority. Dispatched/uncertain costs remain reserved; no timeout refunds or automatic partial-stream retries.
- Gateway rejects unsupported request fields; input/body limits bound parsing. Secret and prompt contents are not metric labels. No caller-configurable upstream URL exists, so custom-provider SSRF is not exposed.
- Financial/audit history is append-only in PostgreSQL. Platform database role is non-superuser and NOBYPASSRLS, but currently owns schema for local development. Production must separate migration and application grants.

Residual risks / release gates:

- No independent security review, penetration test, production identity rollout or SSO/MFA proof.
- Authentication throttling, per-scope concurrency, TLS termination and egress controls need deployment hardening.
- Local encrypted secret storage is not managed KMS. No managed key rotation/recovery qualification.
- No real-provider billing/capability qualification. Synthetic bounds do not establish real-provider spending guarantees.
- No content object storage or lifecycle jobs; zero content is retained. Metadata retention and backup expiry are not automated.
- Email can duplicate after SMTP success followed by a worker crash. Event deduplication does not make SMTP exactly-once.
- Workers' tenant iteration is privileged by architecture; RLS still scopes each processing transaction. Broker messages contain no prompts or provider secrets.

Dependency audit results are point-in-time evidence, not a security certification. Local credentials, portable binaries and database dumps are ignored and must not be deployed.
