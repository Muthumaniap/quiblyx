"""Workflow-level spend contracts with reserved execution envelopes."""
from alembic import op
import sqlalchemy as sa
from packages.domain.models import SpendContract, ContractReservation, ContractAllocation, ContractLedger

revision = "0004"
down_revision = "0003"


def upgrade():
    bind = op.get_bind()
    for model in (SpendContract, ContractReservation, ContractAllocation, ContractLedger):
        model.__table__.create(bind, checkfirst=True)
    op.add_column("requests", sa.Column("contract_id", sa.String(36), nullable=True))
    op.add_column("requests", sa.Column("contract_step", sa.String(120), nullable=True))
    op.create_index("ix_requests_contract_id", "requests", ["contract_id"])
    tenant_tables = ("spend_contracts", "contract_reservations", "contract_allocations",
                     "contract_ledger_entries")
    for table in tenant_tables:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY tenant_isolation ON {table} USING "
                   "(tenant_id = current_setting('app.tenant_id', true)) WITH CHECK "
                   "(tenant_id = current_setting('app.tenant_id', true))")
        op.create_foreign_key(f"{table}_tenant_fk", table, "tenants", ["tenant_id"], ["id"])
        op.create_unique_constraint(f"{table}_tenant_id_unique", table, ["tenant_id", "id"])
    references = [
        ("spend_contracts", "application_id", "applications"),
        ("spend_contracts", "key_id", "virtual_keys"),
        ("contract_reservations", "contract_id", "spend_contracts"),
        ("contract_reservations", "budget_id", "budgets"),
        ("contract_allocations", "contract_id", "spend_contracts"),
        ("contract_allocations", "request_id", "requests"),
        ("contract_ledger_entries", "contract_id", "spend_contracts"),
        ("contract_ledger_entries", "budget_id", "budgets"),
        ("requests", "contract_id", "spend_contracts"),
    ]
    for table, field, target in references:
        op.create_foreign_key(f"{table}_{field}_tenant_fk", table, target,
                              ["tenant_id", field], ["tenant_id", "id"])
    op.execute("CREATE TRIGGER immutable_contract_ledger BEFORE UPDATE OR DELETE ON contract_ledger_entries "
               "FOR EACH ROW EXECUTE FUNCTION prevent_history_mutation()")


def downgrade():
    raise RuntimeError("Roll forward; destructive downgrade disabled")
