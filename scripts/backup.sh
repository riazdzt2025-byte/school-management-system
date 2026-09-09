#!/usr/bin/env bash
# Cron-friendly backup wrapper for the School Management System.
#
# Creates a database + media backup via `manage.py backup_data` and returns a
# useful exit code: 0 = success, non-zero = failure. Never logs credentials.
#
# Usage (cron):
#   0 2 * * *  /path/to/school-management-system/scripts/backup.sh >> /var/log/sms-backup.log 2>&1
#
# Overridable env:
#   P0B_BACKUP_ROOT  where backups are written (default ./backups)
#   P0B_KEEP         how many backups to keep (default 7)
#   DJANGO_SETTINGS_MODULE  (default school_system.settings)
#   PYTHON           python interpreter (default: .venv/bin/python in repo root)
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-school_system.settings}"
PY="${PYTHON:-$REPO_ROOT/.venv/bin/python}"
KEEP="${P0B_KEEP:-7}"

cd "$REPO_ROOT"

echo "[backup.sh] $(date -u +'%Y-%m-%dT%H:%M:%SZ') starting backup (keep=$KEEP)"
"$PY" "$REPO_ROOT/manage.py" backup_data --keep "$KEEP" "${@}"
rc=$?
echo "[backup.sh] exit=$rc"
exit "$rc"
