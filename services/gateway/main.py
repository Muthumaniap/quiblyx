import asyncio
import json
import uuid
import time
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from redis import Redis, RedisError
from sqlalchemy import select, text
from packages.contracts.chat import Chat
from packages.domain.config import settings
from packages.domain.db import transaction
from packages.domain.models import Key, ServiceAccount
from packages.domain.security import digest, verify_contract_token
from packages.domain.accounting import admit, settle, transition, admit_contract
from packages.providers import mock
from packages.observability.http import configure

app = FastAPI(title=f"{settings().product_name} Gateway — MOCK providers only", version="0.1.0")
configure(app, "gateway")
redis = Redis.from_url(settings().redis_url, socket_connect_timeout=2, socket_timeout=2)


def authenticate(authorization):
    with transaction() as s:
        key = s.scalar(select(Key).where(Key.digest == digest(authorization.removeprefix("Bearer ")),
                                        Key.revoked.is_(False)))
        if key is None:
            raise HTTPException(401, "invalid_key")
        tenant, kid, aid, sid = key.tenant_id, key.id, key.application_id, key.service_account_id
    if sid:
        with transaction(tenant) as s:
            account = s.scalar(select(ServiceAccount).where(ServiceAccount.tenant_id == tenant,
                                                            ServiceAccount.id == sid))
            if account is None or not account.active:
                raise HTTPException(401, "invalid_key")
    return tenant, kid, aid


@app.get("/health")
def health():
    return {"status": "alive", "provider_mode": "mock"}


@app.get("/ready")
def ready():
    with transaction() as s:
        s.execute(text("SELECT 1"))
    redis.ping()
    return {"status": "ready"}


@app.get("/v1/models")
def models(authorization: str = Header(default="")):
    authenticate(authorization)
    return {"object": "list", "data": [{"id": "mock-text-v1", "object": "model", "owned_by": "mock"}]}


@app.post("/v1/chat/completions")
async def chat(body: Chat, authorization: str = Header(default=""),
               idempotency_key: str = Header(default="", max_length=128),
               x_spend_contract: str = Header(default="", max_length=4096),
               x_contract_step: str = Header(default="model-call", max_length=120)):
    admitted_at = time.perf_counter()
    x_spend_contract = x_spend_contract if isinstance(x_spend_contract, str) else ""
    x_contract_step = x_contract_step if isinstance(x_contract_step, str) else "model-call"
    tenant, key_id, application_id = await asyncio.to_thread(authenticate, authorization)
    payload = body.model_dump()
    idem = idempotency_key or str(uuid.uuid4())
    contract = None
    if x_spend_contract:
        claims = verify_contract_token(x_spend_contract)
        if (claims["tenant_id"], claims["key_id"], claims["application_id"]) != (tenant, key_id, application_id):
            raise HTTPException(403, "contract_principal_mismatch")
        rid, replay, contract = await asyncio.to_thread(admit_contract, claims, idem, payload,
            mock.bound(body), mock.input_units(body) + body.max_tokens, body.model, x_contract_step)
    else:
        rid, replay = await asyncio.to_thread(admit, tenant, key_id, application_id, idem, payload,
            mock.bound(body), mock.input_units(body) + body.max_tokens)
    if replay:
        return replay
    try:
        # A shared tenant upstream pool; TTL makes fixed-window increments atomic.
        capacity = await asyncio.to_thread(redis.eval,
            "local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],60) end; return n",
            1, f"quota:{tenant}:mock")
        if capacity > 600:
            raise HTTPException(429, "rate_limited", headers={"Retry-After": "60"})
        if body.mock_fault == "before_dispatch":
            raise HTTPException(503, "upstream_unavailable")
    except (RedisError, HTTPException) as exc:
        await asyncio.to_thread(settle, tenant, rid, 0, pre_dispatch=True)
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(503, "capacity_authority_unavailable") from None
    await asyncio.to_thread(transition, tenant, rid, "dispatched")
    admission_ms = (time.perf_counter() - admitted_at) * 1000

    def result(content):
        units = mock.input_units(body)
        return {"id": rid, "object": "chat.completion", "model": "mock-text-v1",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": content},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": units, "completion_tokens": len(content),
                          "total_tokens": units + len(content)},
                "platform": {"provider": "mock", "price_version": "mock-v1",
                             "cost_microusd": units + len(content)*2,
                             "spend_contract_id": contract if contract else None,
                             "contract_step": x_contract_step if contract else None}}

    async def execute(stream):
        content = ""
        try:
            async for chunk in mock.chunks(body):
                content += chunk
                if stream:
                    yield "data: " + json.dumps({"id": rid, "object": "chat.completion.chunk",
                        "model": "mock-text-v1", "choices": [{"index": 0, "delta": {"content": chunk}}]}) + "\n\n"
            response = result(content)
            # Mock output is constant, contains no user input, safe for replay.
            await asyncio.to_thread(settle, tenant, rid, response["platform"]["cost_microusd"],
                                    mock.input_units(body), len(content), response)
            if stream:
                yield "data: " + json.dumps({"id": rid, "choices": [], "usage": response["usage"]}) + "\n\n"
                yield "data: [DONE]\n\n"
            else:
                yield response
        except BaseException:
            # Cancellation/timeout is not proof of zero usage. Keep all reservations.
            await asyncio.shield(asyncio.to_thread(transition, tenant, rid, "uncertain"))
            raise

    if body.stream:
        return StreamingResponse(execute(True), media_type="text/event-stream",
                                 headers={"X-Request-ID": rid, "Cache-Control": "no-store",
                                          "X-Gateway-Admission-Ms": f"{admission_ms:.3f}",
                                          "X-Spend-Contract-ID": contract if contract else ""})
    try:
        async for response in execute(False):
            return response
    except TimeoutError:
        raise HTTPException(502, {"code": "upstream_unavailable", "request_id": rid}) from None
