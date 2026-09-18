# Accounting incident and recovery

1. Stop new gateway admissions after uncertain database failover. Keep the database single-writer.
2. Preserve database/WAL and logs; do not reset reserved balances or delete requests.
3. Compare request state, reservations, immutable ledger and provider evidence for each original admission period.
4. Reserved but undispatched requests can only be released after proving no dispatcher can send them. Dispatched/uncertain requests retain their maximum cost until authoritative usage or an audited conservative adjustment exists.
5. Reconcile before enabling traffic. Never retry partially emitted streams or tools automatically.

Owners/admins may POST `/api/v1/organisations/{tenant}/requests/{request_id}/reconcile-conservative` for an uncertain request. This consumes the full reserved money/token/request bounds and records the action in audit history. It never claims observed upstream usage or releases uncertain cost based on elapsed time. The Requests console offers an explicit review/confirmation for this operation. Do not edit ledger entries directly. Local dump/restore verification passed; production RPO/RTO and failover durability remain unqualified.

## Local backup template

Use `pg_dump --format=custom --file=backup.dump "$BACKUP_DATABASE_URL"` with a native PostgreSQL URL and a separately protected backup role capable of reading all RLS rows. Do not use the application role to dump all tenants. Keep the encryption key separately. Restore into a new isolated database using `pg_restore --no-owner --role=platform --dbname=... backup.dump`; run migrations, RLS checks and `uv run python -m scripts.restore_check` with the restored application's DATABASE_URL before repointing applications. Do not restore over the active database during a drill. Set tenant context when inspecting RLS-protected records. Backup retention/deletion policy is still a launch decision.

## Credential incidents

Revoke compromised virtual keys in the control API; new authentication reads the database immediately. Pause affected applications while investigating. Provider credential compromise requires upstream revocation and replacement as well as platform rotation. Preserve audit evidence without copying secrets into tickets, logs or exports.
