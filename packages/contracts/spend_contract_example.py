"""Server-side contract creation and execution example. Never expose either token to a browser."""
import os
import httpx

control = httpx.Client(base_url=os.getenv("CONTROL_URL", "http://127.0.0.1:8000"),
                       headers={"Authorization": f"Bearer {os.environ['CONTROL_TOKEN']}"})
tenant = os.environ["TENANT_ID"]
contract = control.post(f"/api/v1/organisations/{tenant}/spend-contracts", json={
    "name": "Resolve support ticket", "purpose": "Produce one approved support response",
    "application_id": os.environ["APPLICATION_ID"], "key_id": os.environ["VIRTUAL_KEY_ID"],
    "max_cost_microusd": 80_000, "max_tokens": 4_000, "max_steps": 4,
    "allowed_models": ["org-balanced"], "allowed_tools": [], "data_region": "local",
    "duration_seconds": 1800,
}).raise_for_status().json()

gateway = httpx.Client(base_url=os.getenv("GATEWAY_URL", "http://127.0.0.1:8001"), headers={
    "Authorization": f"Bearer {os.environ['VIRTUAL_KEY']}",
    "X-Spend-Contract": contract["token"], "X-Contract-Step": "answer",
    "Idempotency-Key": "support-ticket-42-answer",
})
result = gateway.post("/v1/chat/completions", json={"model": "org-balanced",
    "messages": [{"role": "user", "content": "Draft the answer"}], "max_tokens": 500})
result.raise_for_status()
receipt = control.post(f"/api/v1/organisations/{tenant}/spend-contracts/{contract['id']}/close")
receipt.raise_for_status()
print(receipt.json())
