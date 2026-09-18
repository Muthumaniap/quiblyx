"""Local burst measurement; does not claim sustained throughput or real-provider qualification."""
import asyncio
import json
import os
import platform
import statistics
import time
from pathlib import Path
import httpx
from dotenv import dotenv_values


async def run():
    token = dotenv_values(".env")["DEV_LOGIN_TOKEN"]
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8000",
                                 headers={"Authorization": f"Bearer {token}"}, timeout=60) as control:
        async def post(path, body):
            r = await control.post(path, json=body)
            r.raise_for_status()
            return r.json()
        org = await post("/api/v1/organisations", {"name": "Local load qualification", "content_days": 0,
                                                  "budget_microusd": 100_000_000})
        base = f"/api/v1/organisations/{org['id']}"
        provider = await post(base + "/provider-connections", {"provider": "mock"})
        app = await post(base + "/applications", {"name": "load", "connection_id": provider["id"]})
        key = await post(base + "/virtual-keys", {"application_id": app["id"]})
        count = int(os.getenv("LOAD_REQUESTS", "100"))
        results = []
        async with httpx.AsyncClient(base_url="http://127.0.0.1:8001", timeout=120,
                    limits=httpx.Limits(max_connections=600, max_keepalive_connections=600),
                    headers={"Authorization": "Bearer " + key["secret"]}) as gateway:
            async def request(i):
                start = time.perf_counter()
                r = await gateway.post("/v1/chat/completions", headers={"Idempotency-Key": f"load-{i}"},
                    json={"messages": [{"role": "user", "content": "Hello"}], "max_tokens": 32, "stream": True})
                results.append({"status": r.status_code, "complete": "data: [DONE]" in r.text,
                                "ms": (time.perf_counter()-start)*1000,
                                "admission_ms": float(r.headers.get("X-Gateway-Admission-Ms", "0"))})
            started = time.perf_counter()
            await asyncio.gather(*(request(i) for i in range(count)))
            elapsed = time.perf_counter()-started
        usage = (await control.get(base + "/usage")).json()
    successful = [r for r in results if r["status"] == 200 and r["complete"]]
    admissions = sorted(r["admission_ms"] for r in successful)
    result = {"scenario": "simultaneous burst, not sustained RPS", "requests": count,
              "completed_streams": len(successful), "elapsed_seconds": round(elapsed, 3),
              "observed_completions_per_second": round(count/elapsed, 2),
              "admission_p95_ms": admissions[int((len(admissions)-1)*.95)] if admissions else None,
              "end_to_end_median_ms": round(statistics.median(r["ms"] for r in results), 2),
              "status_counts": {str(status): sum(r["status"] == status for r in results)
                                for status in {r["status"] for r in results}},
              "usage": usage, "platform": platform.platform(), "logical_cpus": os.cpu_count()}
    Path("docs/evidence").mkdir(exist_ok=True)
    Path(f"docs/evidence/load-{count}.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


asyncio.run(run())
