FROM python:3.12-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl && \
    rm -rf /var/lib/apt/lists/*

COPY services/marketplace_service/requirements.txt /tmp/req.txt
RUN pip install --no-cache-dir -r /tmp/req.txt

COPY libs/ /app/libs/
COPY services/marketplace_service/ /app/services/marketplace_service/

ENV PYTHONPATH=/app

EXPOSE 8003

HEALTHCHECK --interval=10s --timeout=5s --retries=5 \
    CMD curl -f http://localhost:8003/healthz || exit 1
