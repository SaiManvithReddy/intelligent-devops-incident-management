# Image for the background worker that drains the Redis log queue and runs
# the AI classification pipeline against each event.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY scripts ./scripts
COPY data ./data

CMD ["python", "-m", "scripts.run_worker"]
