FROM python:3.12.11-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"
COPY pyproject.toml README.md LICENSE ./
COPY cutline ./cutline
RUN pip install --upgrade pip setuptools wheel && pip install .

FROM python:3.12.11-slim AS runtime

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_MODE=live \
    DATA_BACKEND=firestore \
    PORT=8080
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=65532:65532 cutline ./cutline
COPY --chown=65532:65532 static ./static
USER 65532:65532
EXPOSE 8080
CMD ["uvicorn", "cutline.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers", "--forwarded-allow-ips=*", "--no-server-header", "--timeout-keep-alive", "5", "--limit-concurrency", "80"]
