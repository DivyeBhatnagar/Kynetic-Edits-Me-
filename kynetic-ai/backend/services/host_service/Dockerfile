FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev && rm -rf /var/lib/apt/lists/*

COPY services/host_service/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY libs/ /app/libs/
COPY services/host_service/ /app/services/host_service/

ENV PYTHONPATH=/app

RUN adduser --disabled-password --gecos "" kynetic && chown -R kynetic:kynetic /app
USER kynetic

EXPOSE 8002

CMD ["uvicorn", "services.host_service.main:app", "--host", "0.0.0.0", "--port", "8002"]
