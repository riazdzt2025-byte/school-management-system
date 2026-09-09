#!/usr/bin/env bash
# Restore wrapper for the School Management System.
#
# Restores a backup folder (from `backup_data`) into the currently configured
# database + media directory. This OVERWRITES current data — use --yes only
# when you are certain. Always prefer restoring into a disposable target for a
# drill (see docs/BACKUP_AND_RESTORE.md).
#
# Usage:
#   scripts/restore.sh --backup backup-20260909T... --yes
#
# For a disposable drill:
#   DATABASE_URL=sqlite:///$PWD/.restore-drill/db.sqlite3 \
#     scripts/restore.sh --backup backup-20260909T... --yes --verify \
#     --media-dir "$PWD/.restore-drill/media"
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-school_system.settings}"
PY="${PYTHON:-$REPO_ROOT/.venv/bin/python}"

cd "$REPO_ROOT"

echo "[restore.sh] $(date -u +'%Y-%m-%dT%H:%M:%SZ') starting restore"
"$PY" "$REPO_ROOT/manage.py" restore_backup "$@"
rc=$?
echo "[restore.sh] exit=$rc"
exit "$rc"
