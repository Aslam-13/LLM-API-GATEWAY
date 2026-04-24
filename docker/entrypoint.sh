#!/bin/sh
set -e

ROLE="${1:-${ROLE:-api}}"

case "$ROLE" in
  api)
    exec gunicorn \
      -k uvicorn.workers.UvicornWorker \
      -w "${WEB_CONCURRENCY:-2}" \
      -b 0.0.0.0:8000 \
      --access-logfile - \
      app.main:app
    ;;
  worker)
    exec celery -A app.worker.celery_app worker \
      -l "${CELERY_LOG_LEVEL:-info}" \
      --pool=prefork \
      --concurrency="${CELERY_CONCURRENCY:-2}"
    ;;
  migrate)
    exec alembic upgrade head
    ;;
  *)
    exec "$@"
    ;;
esac
