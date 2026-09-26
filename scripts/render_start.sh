#!/usr/bin/env bash
#
# Render web-service Start Command.
#
# Set this as the service's *Start Command* in the Render dashboard:
#
#     ./scripts/render_start.sh
#
# It applies any pending database migrations before the app accepts traffic,
# then launches gunicorn. Running migrate here (rather than only in the Build
# Command) means a fresh or reset database — e.g. when Render's free-tier
# Postgres expires and is replaced with an empty one — is brought up to the
# current schema automatically, instead of leaving the app to return HTTP 500
# on every page that reads an application table (the "login page shows 500"
# symptom).
#
# `migrate` is idempotent: on an already-migrated database it does nothing.
set -euo pipefail

echo "==> Applying database migrations"
python manage.py migrate --noinput

echo "==> Ensuring baseline data (institutions fixture + superuser)"
# Safe on every boot: only loads the fixture into an EMPTY institution table
# and only creates DJANGO_SUPERUSER_USERNAME when that user does not exist.
# This is what lets a free-tier deployment (no Shell access) recover from a
# reset/expired Postgres without any manual commands.
python manage.py ensure_baseline_data

# Static files are normally collected in the Build Command. Collect here too
# only if the manifest is missing, so the app still boots if the build step was
# skipped. Safe to run repeatedly.
if [ ! -f "staticfiles/staticfiles.json" ]; then
    echo "==> Collecting static files (manifest missing)"
    python manage.py collectstatic --noinput
fi

echo "==> Starting gunicorn"
exec gunicorn school_system.wsgi:application \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers "${WEB_CONCURRENCY:-2}" \
    --timeout "${GUNICORN_TIMEOUT:-60}"
