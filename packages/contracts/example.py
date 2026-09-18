"""Server-side Python gateway example. Configure credentials in environment only."""
import os
import httpx

with httpx.Client(base_url=os.getenv("GATEWAY_URL", "http://127.0.0.1:8001"), timeout=30) as client:
    response = client.post("/v1/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['VIRTUAL_KEY']}", "Idempotency-Key": "example-1"},
        json={"model": "org-balanced", "messages": [{"role": "user", "content": "Hello"}], "max_tokens": 64})
    response.raise_for_status()
    print(response.json())
