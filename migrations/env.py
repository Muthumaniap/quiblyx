from alembic import context
from packages.domain.db import engine
from packages.domain.models import Base

with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
