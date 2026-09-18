"""Real HTTP local smoke. Uses development credential from .env; never prints secrets."""
import os
import uuid
import httpx
from dotenv import dotenv_values

token = os.environ.get("DEV_LOGIN_TOKEN") or dotenv_values(".env")["DEV_LOGIN_TOKEN"]
with httpx.Client(base_url="http://127.0.0.1:8000", headers={"Authorization": f"Bearer {token}"}) as c:
    def post(path, body):
        response = c.post(path, json=body)
        response.raise_for_status()
        return response.json()
    org = post("/api/v1/organisations", {"name": "Smoke " + uuid.uuid4().hex[:8], "content_days": 0,
                                      "budget_microusd": 100})
    path = f"/api/v1/organisations/{org['id']}"
    provider = post(path + "/provider-connections", {"provider": "mock"})
    application = post(path + "/applications", {"name": "Smoke server", "connection_id": provider["id"]})
    key = post(path + "/virtual-keys", {"application_id": application["id"]})
    with httpx.Client(base_url="http://127.0.0.1:8001",
                      headers={"Authorization": "Bearer " + key["secret"]}) as gateway:
        payload = {"messages": [{"role": "user", "content": "Hello"}], "max_tokens": 32}
        response = gateway.post("/v1/chat/completions", json=payload)
        response.raise_for_status()
        refused = gateway.post("/v1/chat/completions", json=payload)
        assert refused.status_code == 429, refused.text
    usage = c.get(path + "/usage")
    usage.raise_for_status()
    assert usage.json()["reserved_microusd"] == 0
    print({"organisation_id": org["id"], "usage": usage.json(), "budget_refusal": refused.status_code})
