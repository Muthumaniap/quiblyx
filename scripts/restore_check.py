"""Validate accounting after a restore, using non-bypass tenant contexts."""
from sqlalchemy import select
from packages.domain.db import transaction
from packages.domain.models import Tenant, Budget, Reservation, Ledger

with transaction() as s:
    tenants = list(s.scalars(select(Tenant.id)))
checked = 0
for tenant in tenants:
    with transaction(tenant) as s:
        for budget in s.scalars(select(Budget).where(Budget.tenant_id == tenant)):
            reservations = list(s.scalars(select(Reservation).where(Reservation.tenant_id == tenant,
                                         Reservation.budget_id == budget.id, Reservation.settled.is_(False))))
            ledger = list(s.scalars(select(Ledger).where(Ledger.tenant_id == tenant,
                                   Ledger.budget_id == budget.id, Ledger.event == "settle")))
            assert budget.reserved == sum(r.amount for r in reservations), budget.id
            assert budget.spent == sum(entry.amount for entry in ledger), budget.id
            checked += 1
print(f"Verified {checked} budget balances across {len(tenants)} tenant contexts")
