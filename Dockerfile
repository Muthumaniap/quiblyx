FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.8.17 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY packages ./packages
COPY services ./services
COPY migrations ./migrations
COPY alembic.ini ./
RUN useradd --create-home platform
USER platform
ENV PATH="/app/.venv/bin:$PATH"
CMD ["uvicorn", "services.control_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
