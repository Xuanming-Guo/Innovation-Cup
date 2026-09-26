# syntax=docker/dockerfile:1.7
FROM ghcr.io/astral-sh/uv:0.11.18 AS uv

FROM python:3.13-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1 \
    PYTHONPATH="/app/src" \
    PATH="/app/.venv/bin:$PATH"

COPY --from=uv /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-install-project

COPY src ./src

RUN useradd --system --uid 10001 --no-create-home coordination \
    && chown -R coordination:coordination /app
USER coordination

EXPOSE 8080
CMD ["python", "-m", "uvicorn", "coordination.api.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--forwarded-allow-ips", "*"]
