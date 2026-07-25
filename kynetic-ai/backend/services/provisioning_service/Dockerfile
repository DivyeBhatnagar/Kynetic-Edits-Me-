FROM python:3.12-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY services/provisioning_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY libs/ ./libs/
COPY services/provisioning_service/ ./services/provisioning_service/
COPY services/__init__.py ./services/__init__.py

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8005

CMD ["uvicorn", "services.provisioning_service.main:app", "--host", "0.0.0.0", "--port", "8005"]
