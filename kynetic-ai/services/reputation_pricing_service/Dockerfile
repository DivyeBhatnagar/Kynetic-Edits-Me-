FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY services/reputation_pricing_service/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY libs/ /app/libs/
COPY services/reputation_pricing_service/ /app/services/reputation_pricing_service/

ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

EXPOSE 8008

CMD ["uvicorn", "services.reputation_pricing_service.main:app", \
     "--host", "0.0.0.0", "--port", "8008", "--workers", "2"]
