import os
import uuid
import pytest
from hypothesis import settings, strategies as st
from hypothesis.stateful import RuleBasedStateMachine, rule, invariant
from sqlalchemy import select
from fastapi import HTTPException
from tests.integration.test_flow import onboard
from packages.domain.accounting import admit, settle, transition
from packages.domain.db import transaction
from packages.domain.models import Budget


class AccountingMachine(RuleBasedStateMachine):
    def __init__(self):
        super().__init__()
        self.tenant, self.application, self.key = onboard(100)
        self.requests = {}

    @rule(amount=st.integers(min_value=1, max_value=60))
    def reserve(self, amount):
        committed = sum(x["cost"] if x["state"] == "completed" else x["bound"] for x in self.requests.values())
        if committed + amount > 100:
            with pytest.raises(HTTPException):
                admit(self.tenant, self.key["id"], self.application, str(uuid.uuid4()), {}, amount)
        else:
            rid, _ = admit(self.tenant, self.key["id"], self.application, str(uuid.uuid4()), {}, amount)
            self.requests[rid] = {"bound": amount, "state": "reserved", "cost": 0}

    @rule(choice=st.integers(min_value=0, max_value=100), fraction=st.integers(min_value=0, max_value=100))
    def settle_or_replay(self, choice, fraction):
        if not self.requests:
            return
        rid = sorted(self.requests)[choice % len(self.requests)]
        item = self.requests[rid]
        cost = item["bound"] * fraction // 100
        if item["state"] != "completed":
            transition(self.tenant, rid, "dispatched")
            item["state"], item["cost"] = "completed", cost
        settle(self.tenant, rid, cost)

    @invariant()
    def balances_match_model(self):
        spent = sum(x["cost"] for x in self.requests.values() if x["state"] == "completed")
        reserved = sum(x["bound"] for x in self.requests.values() if x["state"] != "completed")
        with transaction(self.tenant) as s:
            row = s.scalar(select(Budget).where(Budget.tenant_id == self.tenant))
            assert (row.spent, row.reserved) == (spent, reserved)
            assert spent + reserved <= row.hard_limit


TestAccountingMachine = AccountingMachine.TestCase
TestAccountingMachine.settings = settings(max_examples=12, stateful_step_count=25, deadline=None)
TestAccountingMachine = pytest.mark.skipif(os.environ.get("INTEGRATION") != "1",
                                            reason="requires real PostgreSQL")(TestAccountingMachine)
