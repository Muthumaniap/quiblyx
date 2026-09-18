import os
import pytest
from sqlalchemy import select
from tests.integration.test_flow import c, auth, onboard, call
from packages.domain.db import transaction
from packages.domain.models import Budget, Event
from services.worker.main import drain

pytestmark = pytest.mark.skipif(os.environ.get("INTEGRATION") != "1", reason="requires PostgreSQL + Redis")


def test_atomic_daily_request_and_token_limits():
    tenant, _, key = onboard()
    base = f"/api/v1/organisations/{tenant}"
    for unit, maximum in (("requests", 1), ("tokens", 50)):
        response = c.post(base + "/budgets", headers=auth,
                          json={"scope_id": tenant, "hard_limit": maximum, "unit": unit, "cadence": "day"})
        assert response.status_code == 200, response.text
    assert call(key).status_code == 200
    assert call(key).status_code == 429
    with transaction(tenant) as s:
        rows = {b.unit: b for b in s.scalars(select(Budget).where(Budget.tenant_id == tenant))}
        assert rows["requests"].spent == 1
        assert rows["tokens"].spent == 41
        assert all(b.reserved == 0 for b in rows.values())


def test_threshold_deduplication_and_worker_replay(monkeypatch):
    tenant, _, key = onboard(100)
    assert call(key).status_code == 200  # Reservation 77 triggers 70%; actual usage is 69.
    with transaction(tenant) as s:
        thresholds = list(s.scalars(select(Event).where(Event.tenant_id == tenant, Event.kind == "budget.threshold")))
        assert len(thresholds) == 1 and thresholds[0].payload["basis"] == "committed"
        event_id = thresholds[0].id
    sent = []
    class Sink:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def send_message(self, message):
            sent.append(message["Message-ID"])
    monkeypatch.setattr("services.worker.main.smtplib.SMTP", Sink)
    drain()
    drain()
    assert sent.count(f"<{event_id}@platform.local>") == 1
