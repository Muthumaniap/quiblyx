from contextlib import contextmanager
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from packages.domain.config import settings

engine = create_engine(settings().database_url, pool_pre_ping=True,
                       connect_args={"connect_timeout": 5} if settings().database_url.startswith("postgresql") else {})


@contextmanager
def transaction(tenant_id=None):
    with Session(engine) as session, session.begin():
        if tenant_id is not None and engine.dialect.name == "postgresql":
            session.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": tenant_id})
        yield session
