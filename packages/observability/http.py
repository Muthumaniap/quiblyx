import time
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from sqlalchemy.exc import SQLAlchemyError

requests = Counter("platform_http_requests_total", "HTTP requests by service and status", ["service", "status"])
latency = Histogram("platform_http_duration_seconds", "HTTP response-start latency", ["service"])


def configure(app, service):
    @app.exception_handler(SQLAlchemyError)
    async def database_errors(request: Request, exc: SQLAlchemyError):
        return JSONResponse(status_code=503, content={"error": {"code": "accounting_authority_unavailable"}},
                            headers={"Retry-After": "5"})

    @app.exception_handler(HTTPException)
    async def errors(request: Request, exc: HTTPException):
        detail = exc.detail
        code = detail if isinstance(detail, str) else detail.get("code", "request_failed")
        return JSONResponse(status_code=exc.status_code,
                            content={"error": {"code": code}, "detail": detail}, headers=exc.headers)

    @app.middleware("http")
    async def observe(request: Request, call_next):
        # Header checks plus counted ASGI body prevent chunked body size bypass.
        size = 0
        receive = request._receive

        async def bounded_receive():
            nonlocal size
            message = await receive()
            if message["type"] == "http.request":
                size += len(message.get("body", b""))
                if size > 600_000:
                    raise HTTPException(413, "request_too_large")
            return message

        request._receive = bounded_receive
        length = request.headers.get("content-length", "0")
        if not length.isdigit() or int(length) > 600_000:
            return JSONResponse({"error": {"code": "request_too_large"}}, status_code=413)
        start = time.monotonic()
        response = await call_next(request)
        requests.labels(service, str(response.status_code)).inc()
        latency.labels(service).observe(time.monotonic() - start)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/metrics", include_in_schema=False)
    def metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
