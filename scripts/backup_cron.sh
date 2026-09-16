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
#   KEEP_BACKUPS / BACKUP_MAX_AGE_HOURS   retention + freshness for the gate.
#   BACKUP_SKIP_REMOTE_CHECK  set to 1 to skip the off-box gate for one run
#                       (by default the gate runs whenever a bucket is set).
#
# Read from the environment by `backup_data` itself (see docs/BACKUP_RESTORE_GUIDE.md):
#   BACKUP_ENCRYPTION / BACKUP_PASSPHRASE_FILE   encryption at rest (recommended).
#   BACKUP_OBJECT_STORAGE_BUCKET / _ACCESS_KEY / _SECRET_KEY [+ _ENDPOINT/_REGION/
#     _PREFIX/_KEEP]  the independent off-box copy. Without these the backup
#     stays local only — on a cron job that means it is wiped after the run.
#     When they ARE set, step 2 also requires the newest backup to be present in
#     the bucket (`check_backups --check-remote`), so a silently failing upload
#     pages instead of passing.
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
#    When an off-box bucket is configured, also require that the newest backup
#    actually reached it — otherwise a rotated key or an expired credential
#    leaves a "healthy" local backup and no copy that survives losing this host.
REMOTE_FLAG=""
if [[ -n "${BACKUP_OBJECT_STORAGE_BUCKET:-}" && "${BACKUP_SKIP_REMOTE_CHECK:-0}" != "1" ]]; then
  REMOTE_FLAG="--check-remote"
fi
"$PY" manage.py check_backups \
  --max-age-hours "${BACKUP_MAX_AGE_HOURS:-48}" \
  --want-keep "${KEEP_BACKUPS:-7}" $REMOTE_FLAG || fail "check_backups (exit $?)"

# 3. Success — ping the health check (no-op when unset).
echo "[backup_cron] OK: backup + validation succeeded at $(date -u +%FT%TZ)"
if [[ -n "$PING_URL" ]]; then
  curl -fsS -m 10 "${PING_URL%/}" >/dev/null 2>&1 \
    || echo "[backup_cron] (healthcheck success-ping errored)" >&2
fi
