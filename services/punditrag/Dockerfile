FROM python:3.11-slim AS builder

ARG PUNDITRAG_TORCH_INDEX_URL=

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_HTTP_TIMEOUT=1200 \
    UV_HTTP_RETRIES=10 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN pip install --no-cache-dir uv==0.8.5

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project \
    && if [ -n "$PUNDITRAG_TORCH_INDEX_URL" ]; then \
         uv pip install --python /opt/venv/bin/python --reinstall \
           torch==2.10.0 --index-url "$PUNDITRAG_TORCH_INDEX_URL"; \
       fi

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PROJECT_ROOT=/app \
    PATH=/opt/venv/bin:$PATH

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv

COPY . .

CMD ["sh", "-lc", "${START_COMMAND:-sleep infinity}"]
