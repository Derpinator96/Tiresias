# Shared Python 3.11 image for gateway, ai, dashboard and the tools runner.
# Code is bind-mounted per service (see docker-compose.yml) so each container sees only
# the folders it needs. Nothing from the repo is baked in.
FROM python:3.11.17-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app

COPY requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir --require-hashes -r /tmp/requirements.lock \
 && rm /tmp/requirements.lock

# torch (CPU) in its own layer: see requirements-ml.in.
COPY requirements-ml.lock /tmp/requirements-ml.lock
RUN pip install --no-cache-dir --require-hashes -r /tmp/requirements-ml.lock \
 && rm /tmp/requirements-ml.lock

WORKDIR /app
