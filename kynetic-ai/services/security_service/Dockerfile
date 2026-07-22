FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Trivy for image scanning (production only)
# In mock mode (SCANNER_MOCK=true) Trivy is never called
RUN curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh \
    | sh -s -- -b /usr/local/bin v0.51.1 || true

# Python dependencies
COPY services/security_service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Source code
COPY libs/ ./libs/
COPY services/security_service/ ./services/security_service/

ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

EXPOSE 8006

CMD ["uvicorn", "services.security_service.main:app", \
     "--host", "0.0.0.0", "--port", "8006", "--workers", "2"]
