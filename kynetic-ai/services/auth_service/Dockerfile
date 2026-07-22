FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY services/auth_service/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Copy shared libs and service code
COPY libs/ /app/libs/
COPY services/auth_service/ /app/services/auth_service/

# Set PYTHONPATH so libs.* imports resolve
ENV PYTHONPATH=/app

# Create non-root user for security
RUN adduser --disabled-password --gecos "" kynetic && chown -R kynetic:kynetic /app
USER kynetic

EXPOSE 8001

CMD ["uvicorn", "services.auth_service.main:app", "--host", "0.0.0.0", "--port", "8001"]
