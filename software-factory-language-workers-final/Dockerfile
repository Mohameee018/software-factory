FROM python:3.12.8-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir .
RUN python -m playwright install --with-deps chromium
RUN mkdir -p /data/projects /data/logs
ENV DATABASE_PATH=/data/factory.db WORKSPACE_PATH=/data/projects
CMD ["factory","telegram"]
