FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

COPY services/api_gateway/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY libs/ /app/libs/
COPY services/api_gateway/ /app/services/api_gateway/

ENV PYTHONPATH=/app

RUN adduser --disabled-password --gecos "" kynetic && chown -R kynetic:kynetic /app
USER kynetic

EXPOSE 8000

CMD ["uvicorn", "services.api_gateway.main:app", "--host", "0.0.0.0", "--port", "8000"]
