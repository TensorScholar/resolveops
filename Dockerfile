FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY . .
RUN python -m pip install --no-cache-dir '.[web]' \
    && mkdir -p /data \
    && chown 65532:65532 /data

USER 65532:65532
EXPOSE 8080
CMD ["resolveops", "serve", "--database", "/data/resolveops.db", "--host", "0.0.0.0", "--port", "8080"]
