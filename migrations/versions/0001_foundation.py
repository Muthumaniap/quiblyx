"""Initial tenant and accounting schema; tenant context is transaction-local."""
from alembic import op
from pathlib import Path

revision = "0001"
down_revision = None

TENANT_TABLES = ["memberships", "groups", "provider_connections", "applications", "budgets",
                 "requests", "reservations", "ledger_entries", "outbox_events", "audit_events"]


def upgrade():
    op.execute(Path(__file__).resolve().parents[1].joinpath("schema_v1.sql").read_text(encoding="utf-8"))
    for table in TENANT_TABLES:
        op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
        op.execute(f"CREATE POLICY tenant_isolation ON {table} USING "
                   "(tenant_id = current_setting('app.tenant_id', true)) WITH CHECK "
                   "(tenant_id = current_setting('app.tenant_id', true))")
    for table in TENANT_TABLES + ["virtual_keys"]:
        op.create_foreign_key(f"{table}_tenant_fk", table, "tenants", ["tenant_id"], ["id"])
        op.create_unique_constraint(f"{table}_tenant_id_unique", table, ["tenant_id", "id"])
    for table, field, target in [
        ("groups", "parent_id", "groups"), ("applications", "group_id", "groups"),
        ("applications", "connection_id", "provider_connections"),
        ("virtual_keys", "application_id", "applications"),
        ("requests", "application_id", "applications"), ("requests", "key_id", "virtual_keys"),
        ("reservations", "request_id", "requests"), ("reservations", "budget_id", "budgets"),
        ("ledger_entries", "request_id", "requests"), ("ledger_entries", "budget_id", "budgets")]:
        op.create_foreign_key(f"{table}_{field}_tenant_fk", table, target,
                             ["tenant_id", field], ["tenant_id", "id"])
    op.execute("""CREATE FUNCTION prevent_history_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
                  BEGIN RAISE EXCEPTION 'append-only history'; END $$""")
    for table in ("ledger_entries", "audit_events"):
        op.execute(f"CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE ON {table} "
                   "FOR EACH ROW EXECUTE FUNCTION prevent_history_mutation()")


def downgrade():
    raise RuntimeError("Destructive rollback disabled. Restore a verified backup or roll forward.")
