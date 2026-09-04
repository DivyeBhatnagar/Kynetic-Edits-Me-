# Unified Kynetic Backend Microservices Container
# # ponytail: consolidated 9 duplicate Dockerfiles into 1 parameterized multi-service image

FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install root dependencies
COPY pyproject.toml /app/
RUN pip install --no-cache-dir fastapi uvicorn sqlalchemy psycopg2-binary redis pydantic pydantic-settings httpx structlog python-jose cryptography

# Copy shared libraries and services
COPY libs/ /app/libs/
COPY services/ /app/services/

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

RUN adduser --disabled-password --gecos "" kynetic && chown -R kynetic:kynetic /app
USER kynetic

EXPOSE 8000

# Default entrypoint (can be overridden by docker-compose or k8s args)
CMD ["uvicorn", "services.api_gateway.main:app", "--host", "0.0.0.0", "--port", "8000"]
