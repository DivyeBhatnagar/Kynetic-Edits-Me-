FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl && rm -rf /var/lib/apt/lists/*
COPY services/wallet_billing_service/requirements.txt /tmp/req.txt
RUN pip install --no-cache-dir -r /tmp/req.txt
COPY libs/ /app/libs/
COPY services/wallet_billing_service/ /app/services/wallet_billing_service/
ENV PYTHONPATH=/app
EXPOSE 8004
HEALTHCHECK --interval=10s --timeout=5s --retries=5 \
    CMD curl -f http://localhost:8004/healthz || exit 1
