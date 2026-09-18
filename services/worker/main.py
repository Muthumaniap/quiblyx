"""Outbox remains the durable source; beat can safely enqueue duplicate drains."""
import smtplib
from email.message import EmailMessage
from celery import Celery
from sqlalchemy import select
from packages.domain.config import settings
from packages.domain.db import transaction
from packages.domain.models import Tenant, Event

app = Celery("platform", broker=settings().redis_url)
app.conf.update(task_acks_late=True, task_reject_on_worker_lost=True,
                broker_transport_options={"visibility_timeout": 3600},
                beat_schedule={"outbox": {"task": "outbox.drain", "schedule": 10.0}})


@app.task(name="outbox.drain", autoretry_for=(OSError,), retry_backoff=True, max_retries=5)
def drain():
    with transaction() as s:
        tenants = list(s.scalars(select(Tenant.id)))
    for tenant in tenants:
        with transaction(tenant) as s:
            events = list(s.scalars(select(Event).where(Event.tenant_id == tenant, Event.delivered.is_(False))
                                    .with_for_update(skip_locked=True).limit(100)))
            for event in events:
                if event.kind != "budget.threshold":
                    event.delivered = True
                    continue
                # Development sink only. No recipient from an untrusted event payload.
                message = EmailMessage()
                message["From"] = "notifications@quiblyx.local"
                message["To"] = "local-admin@localhost"
                message["Subject"] = f"[{settings().product_name} MOCK] Budget at {event.payload['threshold']}% committed"
                message["Message-ID"] = f"<{event.id}@quiblyx.local>"
                message.set_content(f"Organisation {tenant}: request accounting event {event.id}. "
                                    "View details in your authenticated console.")
                with smtplib.SMTP(settings().smtp_host, settings().smtp_port, timeout=5) as smtp:
                    smtp.send_message(message)
                event.delivered = True
