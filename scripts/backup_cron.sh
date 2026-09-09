#!/usr/bin/env bash
#
# Cron-friendly backup + health-check for Render / any scheduler.
#
# Runs the Django backup, then validates the newest backup, and pings a
# Healthchecks.io (or compatible) "cron" check on success/failure so a silent
# stop or a broken backup surfaces as an alert. On failure it exits non-zero
# (so scheduler / log tail also flags it).
#
# Env expected (never hard-coded, never committed):
#   P0B_BACKUP_ROOT     where backup folders live (point at a persistent disk).
#   HEALTHCHECK_PING_URL  optional; GET success => ping URL, failure => <url>/fail
#   PYTHON              optional python executable; defaults to .venv/bin/python.
#
# Usage:
#   P0B_BACKUP_ROOT=/data/backups ./scripts/backup_cron.sh
#
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

PY="${PYTHON:-.venv/bin/python}"
if [[ -x "$PY" ]]; then
  :  # fine
else
  PY="python"
fi

PING_URL="${HEALTHCHECK_PING_URL:-}"

fail() {
  echo "[backup_cron] FAILED: $*" >&2
  if [[ -n "$PING_URL" ]]; then
    curl -fsS -m 10 "${PING_URL%/}/fail" >/dev/null 2>&1 \
      || echo "[backup_cron] (healthcheck fail-ping errored)" >&2
  fi
  exit 1
}

# 1. Take the backup (prunes old ones per --keep; default 7).
"$PY" manage.py backup_data --keep "${KEEP_BACKUPS:-7}" || fail "backup_data (exit $?)"

# 2. Validate the newest backup: manifest, DB SHA, freshness, retention.
"$PY" manage.py check_backups \
  --max-age-hours "${BACKUP_MAX_AGE_HOURS:-48}" \
  --want-keep "${KEEP_BACKUPS:-7}" || fail "check_backups (exit $?)"

# 3. Success — ping the health check (no-op when unset).
echo "[backup_cron] OK: backup + validation succeeded at $(date -u +%FT%TZ)"
if [[ -n "$PING_URL" ]]; then
  curl -fsS -m 10 "${PING_URL%/}" >/dev/null 2>&1 \
    || echo "[backup_cron] (healthcheck success-ping errored)" >&2
fi
