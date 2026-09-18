"""Maintenance helper; initial schema is checked in, never generated at migration runtime."""
from pathlib import Path
from sqlalchemy import MetaData
from sqlalchemy.schema import CreateTable, CreateIndex
from sqlalchemy.dialects import postgresql
from packages.domain.models import Base

names = {"tenants", "memberships", "groups", "provider_connections", "applications", "virtual_keys",
         "budgets", "requests", "reservations", "ledger_entries", "outbox_events", "audit_events"}
metadata = MetaData()
for table in Base.metadata.sorted_tables:
    if table.name in names:
        copied = table.to_metadata(metadata)
        for column in ("project_id", "service_account_id"):
            if column in copied.c:
                copied._columns.remove(copied.c[column])
statements = []
for table in metadata.sorted_tables:
    statements.append(str(CreateTable(table).compile(dialect=postgresql.dialect())) + ";")
    statements.extend(str(CreateIndex(index).compile(dialect=postgresql.dialect())) + ";" for index in table.indexes)
Path("migrations/schema_v1.sql").write_text("\n".join(statements), encoding="utf-8")
