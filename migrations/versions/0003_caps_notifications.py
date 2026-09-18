"""Multi-unit period caps and threshold event deduplication."""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"


def upgrade():
    op.add_column("budgets", sa.Column("unit", sa.String(10), nullable=False, server_default="money"))
    op.alter_column("budgets", "period", type_=sa.String(10))
    for constraint in sa.inspect(op.get_bind()).get_unique_constraints("budgets"):
        if set(constraint["column_names"]) == {"tenant_id", "scope_id", "period"}:
            op.drop_constraint(constraint["name"], "budgets", type_="unique")
    op.create_unique_constraint("budget_scope_period_unit", "budgets", ["tenant_id", "scope_id", "period", "unit"])
    op.add_column("requests", sa.Column("period", sa.String(7), nullable=False, server_default="legacy"))
    # RLS is forced; update old requests under each explicit tenant context.
    tenants = op.get_bind().execute(sa.text("SELECT id FROM tenants")).scalars().all()
    for tenant in tenants:
        op.get_bind().execute(sa.text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": tenant})
        op.execute("UPDATE requests SET period = to_char(created_at AT TIME ZONE 'UTC', 'YYYY-MM')")
    op.add_column("outbox_events", sa.Column("dedup_key", sa.String(150), nullable=True))
    op.create_unique_constraint("event_deduplication", "outbox_events", ["dedup_key"])


def downgrade():
    raise RuntimeError("Roll forward; destructive downgrade disabled")
