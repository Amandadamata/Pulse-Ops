# syntax=docker/dockerfile:1
# Uma imagem para API, worker, migrações e laboratório (comandos diferentes no Compose).

FROM python:3.12-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app

# extra_ca (opcional): certificado de uma rede com proxy TLS corporativo. Vazio por padrão.
RUN --mount=type=secret,id=extra_ca,required=false \
    if [ -s /run/secrets/extra_ca ]; then export PIP_CERT=/run/secrets/extra_ca; fi; \
    pip install --no-cache-dir uv==0.11.32

COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=secret,id=extra_ca,required=false \
    if [ -s /run/secrets/extra_ca ]; then export SSL_CERT_FILE=/run/secrets/extra_ca; fi; \
    uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN --mount=type=secret,id=extra_ca,required=false \
    if [ -s /run/secrets/extra_ca ]; then export SSL_CERT_FILE=/run/secrets/extra_ca; fi; \
    uv sync --frozen --no-dev --no-editable


FROM python:3.12-slim
RUN useradd --system --uid 10001 --home-dir /app --shell /usr/sbin/nologin pulseops
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY alembic.ini ./
COPY migrations ./migrations
COPY lab ./lab
COPY scripts ./scripts
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app
USER pulseops
EXPOSE 8000
CMD ["uvicorn", "pulseops.web.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
