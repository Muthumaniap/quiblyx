"""Roles, projects, service accounts; expand-only."""
from alembic import op
import sqlalchemy as sa
from packages.domain.models import Role, Project, ServiceAccount

revision = "0002"
down_revision = "0001"


def upgrade():
    bind = op.get_bind()
    for model in (Role, Project, ServiceAccount):
        model.__table__.create(bind, checkfirst=True)
    columns = {c["name"] for c in sa.inspect(bind).get_columns("applications")}
    if "project_id" not in columns:
        op.add_column("applications", sa.Column("project_id", sa.String(36), nullable=True))
    columns = {c["name"] for c in sa.inspect(bind).get_columns("virtual_keys")}
    if "service_account_id" not in columns:
        op.add_column("virtual_keys", sa.Column("service_account_id", sa.String(36), nullable=True))
    op.alter_column("memberships", "role", type_=sa.String(80))
    for table in ("roles", "projects", "service_accounts"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY tenant_isolation ON {table} USING "
                   "(tenant_id = current_setting('app.tenant_id', true)) WITH CHECK "
                   "(tenant_id = current_setting('app.tenant_id', true))")
        op.create_foreign_key(f"{table}_tenant_fk", table, "tenants", ["tenant_id"], ["id"])
        op.create_unique_constraint(f"{table}_tenant_id_unique", table, ["tenant_id", "id"])
    for table, field, target in [("projects", "group_id", "groups"),
            ("service_accounts", "application_id", "applications"),
            ("applications", "project_id", "projects"), ("virtual_keys", "service_account_id", "service_accounts")]:
        op.create_foreign_key(f"{table}_{field}_tenant_fk", table, target,
                             ["tenant_id", field], ["tenant_id", "id"])


def downgrade():
    raise RuntimeError("Roll forward; destructive downgrade disabled")
