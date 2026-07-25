FROM python:3.12-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY services/ai_router_copilot_service/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Copy shared libs and service code
COPY libs/ /app/libs/
COPY services/ai_router_copilot_service/ /app/services/ai_router_copilot_service/
COPY services/api_gateway/rate_limiter.py /app/services/api_gateway/rate_limiter.py

ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

EXPOSE 8007

CMD ["uvicorn", "services.ai_router_copilot_service.main:app", \
     "--host", "0.0.0.0", "--port", "8007", "--workers", "2"]
