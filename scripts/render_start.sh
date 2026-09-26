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

# Render normally starts this command from the repository root, but resolving
# the root here also makes the command safe when it is invoked from elsewhere
# (for example, with `bash scripts/render_start.sh`).
PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# Use the interpreter from Render's build environment for both management
# commands and Gunicorn. This avoids accidentally starting the app with a
# different system Python than the one that installed requirements.txt.
PYTHON_BIN="${PYTHON_BIN:-python}"

# Django 6.1 requires Python 3.12+. The repository's .python-version file
# selects that version on Render; fail with a useful message if a service still
# has an old runtime configured instead of producing a less obvious import
# error below.
"$PYTHON_BIN" - <<'PY'
import sys

if sys.version_info < (3, 12):
    raise SystemExit(
        "This application requires Python 3.12+ (Django 6.1). "
        "Set Render's PYTHON_VERSION to 3.12.x or use the committed "
        ".python-version file, then redeploy."
    )
PY

echo "==> Applying database migrations"
"$PYTHON_BIN" manage.py migrate --noinput

echo "==> Ensuring baseline data (institutions fixture + superuser)"
# Safe on every boot: only loads the fixture into an EMPTY institution table
# and only creates DJANGO_SUPERUSER_USERNAME when that user does not exist.
# This is what lets a free-tier deployment (no Shell access) recover from a
# reset/expired Postgres without any manual commands.
"$PYTHON_BIN" manage.py ensure_baseline_data

# Static files are normally collected in the Build Command. Collect here too
# only if the manifest is missing, so the app still boots if the build step was
# skipped. Safe to run repeatedly.
if [ ! -f "staticfiles/staticfiles.json" ]; then
    echo "==> Collecting static files (manifest missing)"
    "$PYTHON_BIN" manage.py collectstatic --noinput
fi

echo "==> Starting gunicorn"
exec "$PYTHON_BIN" -m gunicorn school_system.wsgi:application \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers "${WEB_CONCURRENCY:-2}" \
    --timeout "${GUNICORN_TIMEOUT:-60}"
