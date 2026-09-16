#!/usr/bin/env bash
#
# Backup / restore smoke test — DISPOSABLE DATA ONLY.
#
# Proves, end to end, that the backup tooling actually works on this machine:
# build a throwaway database + a throwaway uploaded photo, back them up, verify
# the backup, restore into a *separate* throwaway target, and confirm the
# records and the photo bytes came back identical. Runs the plaintext and the
# encrypted paths (when openssl is available).
#
# It never touches the real database, the real MEDIA_ROOT, or any configured
# bucket:
#   * DATABASE_URL and MEDIA_ROOT are exported to disposable targets, which
#     overrides .env (python-dotenv does not overwrite variables already set);
#   * before doing anything it asks Django which database it resolved and ABORTS
#     unless that target is the drill's own (a file inside the drill directory,
#     or one of the drill databases this script just created) — so a stray
#     production DATABASE_URL cannot be hit by accident;
#   * the object-storage upload is never attempted here (no bucket, no keys);
#   * everything is deleted on the way out unless --keep is given.
#
# Usage:
#   scripts/backup_smoke_test.sh                     # SQLite, disposable file
#   scripts/backup_smoke_test.sh --keep              # keep the drill artifacts
#   scripts/backup_smoke_test.sh --postgres postgres://postgres@localhost:5432/postgres
#
# In --postgres mode the script creates two databases of its own
# (sms_drill_src_<stamp> / sms_drill_dst_<stamp>) on that server and drops them
# on exit; it needs pg_dump/pg_restore on PATH.
#
# Exit code: 0 = every step passed, non-zero = something is broken.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-school_system.settings}"
PY="${PYTHON:-$REPO_ROOT/.venv/bin/python}"
if [[ ! -x "$PY" ]]; then PY="$(command -v python3 || command -v python)"; fi

DRILL_ROOT="$REPO_ROOT/.restore-drill"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DRILL="$DRILL_ROOT/smoke-$STAMP"
KEEP_DIR=0
MODE="sqlite"
PG_BASE_URL=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --keep) KEEP_DIR=1; shift ;;
    --postgres) MODE="postgres"; PG_BASE_URL="${2:-}"; shift 2 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

PASS=0
FAIL=0

step() { echo; echo "== $* =="; }
ok()   { echo "   ok: $*"; PASS=$((PASS + 1)); }
bad()  { echo "   FAIL: $*" >&2; FAIL=$((FAIL + 1)); }

# ---------------------------------------------------------------- postgres --
# Disposable databases of our own on the given server, never an existing one.
# Postgres folds an unquoted identifier to lower case, so the drill database
# names must already be lower case — otherwise `CREATE DATABASE X` makes `x`
# and Django then asks for `X` and does not find it.
PG_STAMP="$(printf '%s' "$STAMP" | tr '[:upper:]' '[:lower:]')"
PG_SRC_NAME="sms_drill_src_$PG_STAMP"
PG_DST_NAME="sms_drill_dst_$PG_STAMP"
PG_DST_NAME_WRONG="${PG_DST_NAME}_wrong"
PG_SRC_URL=""
PG_DST_URL=""

pg_libpq_url() {  # psycopg2/libpq wants postgresql://, not Django's postgres://
  local url="$1"
  echo "${url/postgres:\/\//postgresql://}"
}

pg_split_url() {  # echoes "<prefix-without-dbname> <dbname> <query>"
  local url="$1" noq query name prefix
  if [[ "$url" == *"?"* ]]; then noq="${url%%\?*}"; query="${url#*\?}"; else noq="$url"; query=""; fi
  name="${noq##*/}"
  prefix="${noq%/*}"
  echo "$prefix|$name|$query"
}

if [[ "$MODE" == "postgres" ]]; then
  if [[ -z "$PG_BASE_URL" ]]; then
    echo "--postgres needs a connection URL, e.g. postgres://postgres@localhost:5432/postgres" >&2
    exit 2
  fi
  for tool in pg_dump pg_restore; do
    if ! command -v "$tool" >/dev/null 2>&1; then
      echo "[smoke] $tool is not on PATH — cannot exercise the Postgres backup path." >&2
      exit 1
    fi
  done
  parts="$(pg_split_url "$PG_BASE_URL")"
  pg_prefix="${parts%%|*}"; rest="${parts#*|}"; pg_basedb="${rest%%|*}"; pg_query="${rest#*|}"
  PG_SRC_URL="$pg_prefix/$PG_SRC_NAME"; PG_DST_URL="$pg_prefix/$PG_DST_NAME"
  [[ -n "$pg_query" ]] && { PG_SRC_URL="$PG_SRC_URL?$pg_query"; PG_DST_URL="$PG_DST_URL?$pg_query"; }
fi

mkdir -p "$DRILL/media" "$DRILL/backups" "$DRILL/restored-media"

if [[ "$MODE" == "sqlite" ]]; then
  SRC_DB="$DRILL/src.sqlite3"
  DST_DB="$DRILL/dst.sqlite3"
  export DATABASE_URL="sqlite:///$SRC_DB"
else
  export DATABASE_URL="$PG_SRC_URL"
fi
export MEDIA_ROOT="$DRILL/media"
unset USE_S3 AWS_STORAGE_BUCKET_NAME 2>/dev/null || true

cleanup() {
  local rc=$?
  if [[ "$MODE" == "postgres" && -n "${PG_BASE_DSN:-}" ]]; then
    for db in "$PG_SRC_NAME" "$PG_DST_NAME" "$PG_DST_NAME_WRONG"; do
      PG_BASE_DSN="$PG_BASE_DSN" "$PY" -c "
import os, psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
try:
    c = psycopg2.connect(os.environ['PG_BASE_DSN'])
    c.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    c.cursor().execute('DROP DATABASE IF EXISTS ' + '$db')
    c.close()
except Exception as exc:
    print(f'[smoke] could not drop $db: {exc}')
" 2>/dev/null
    done
    echo "[smoke] dropped the disposable Postgres databases"
  fi
  if [[ "$KEEP_DIR" == "1" ]]; then
    echo "[smoke] drill kept for inspection: $DRILL"
  else
    rm -rf "$DRILL"
    rmdir "$DRILL_ROOT" 2>/dev/null || true   # drop the parent when empty
  fi
  echo
  echo "[smoke] steps passed: $PASS, failed: $FAIL"
  if [[ "$FAIL" -ne 0 || $rc -ne 0 ]]; then
    echo "[smoke] RESULT: FAILED"
    exit 1
  fi
  echo "[smoke] RESULT: PASSED (disposable data only — this is not a production backup)"
  exit 0
}
trap cleanup EXIT

# libpq DSN for the server's own database, used to CREATE/DROP the drill DBs.
if [[ "$MODE" == "postgres" ]]; then
  PG_BASE_DSN="$(pg_libpq_url "$PG_BASE_URL")"
  export PG_BASE_DSN
  step "0. Create the disposable Postgres databases"
  for db in "$PG_SRC_NAME" "$PG_DST_NAME"; do
    "$PY" -c "
import os, psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
c = psycopg2.connect(os.environ['PG_BASE_DSN'])
c.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
c.cursor().execute('CREATE DATABASE ' + '$db')
c.close()
print('   created database $db')
" || { bad "could not create database $db"; exit 1; }
  done
  ok "disposable databases created: $PG_SRC_NAME, $PG_DST_NAME"
fi

step "1. Guard: the resolved database must be the disposable one"
RESOLVED="$("$PY" - <<'PYEOF'
import django
django.setup()
from django.conf import settings
db = settings.DATABASES["default"]
print(f"{db.get('ENGINE','')}|{db.get('NAME','')}")
PYEOF
)"
ENGINE="${RESOLVED%%|*}"
DB_PATH="${RESOLVED#*|}"
echo "   resolved engine: $ENGINE"
echo "   resolved database: $DB_PATH"
if [[ "$MODE" == "sqlite" ]]; then
  case "$ENGINE" in
    *sqlite3*) ;;
    *) bad "engine is not sqlite ($ENGINE) — refusing to run a sqlite drill against it"; exit 1 ;;
  esac
  case "$DB_PATH" in
    "$DRILL"/*) ok "target database is inside the drill directory" ;;
    *) bad "target database '$DB_PATH' is NOT inside $DRILL — refusing to continue"; exit 1 ;;
  esac
else
  case "$ENGINE" in
    *postgres*) ;;
    *) bad "engine is not postgres ($ENGINE) — refusing to run a postgres drill against it"; exit 1 ;;
  esac
  if [[ "$DB_PATH" == "$PG_SRC_NAME" ]]; then
    ok "target database is the drill's own ($PG_SRC_NAME)"
  else
    bad "target database '$DB_PATH' is NOT the drill database '$PG_SRC_NAME' — refusing to continue"
    exit 1
  fi
fi
case "${MEDIA_ROOT}" in
  "$DRILL"/*) ok "MEDIA_ROOT is inside the drill directory ($MEDIA_ROOT)" ;;
  *) bad "MEDIA_ROOT '$MEDIA_ROOT' is NOT inside $DRILL"; exit 1 ;;
esac

step "2. Build disposable data (schema + one student + one photo)"
"$PY" manage.py migrate --noinput --verbosity 0 || { bad "migrate"; exit 1; }
"$PY" manage.py loaddata students/fixtures/institutions.json --verbosity 0 \
  || { bad "loaddata institutions"; exit 1; }
"$PY" manage.py shell --command "
from django.core.files.base import ContentFile
from io import BytesIO
from PIL import Image
from students.models import Institution, Student
buf = BytesIO()
Image.new('RGB', (32, 32), (12, 130, 200)).save(buf, format='PNG')
s = Student.objects.create(
    name='Smoke Test Student',
    admission_class='9',
    section='A',
    guardian_contact_no='01812345678',
    institution=Institution.objects.get(pk=2),
)
s.photo.save('smoke-test.png', ContentFile(buf.getvalue()), save=True)
print(f'   created student {s.student_id} with photo {s.photo.name}')
" || { bad "create disposable student"; exit 1; }
PHOTO_REL="$("$PY" manage.py shell --command "
from students.models import Student
print(Student.objects.get().photo.name)
" 2>/dev/null | tail -1 | tr -d '\r')"
PHOTO_SRC="$DRILL/media/$PHOTO_REL"
if [[ -f "$PHOTO_SRC" ]]; then
  PHOTO_SHA_SRC="$(sha256sum "$PHOTO_SRC" | cut -d' ' -f1)"
  ok "photo written: $PHOTO_REL (sha256 ${PHOTO_SHA_SRC:0:16}...)"
else
  bad "photo was not written to $PHOTO_SRC"; exit 1
fi

step "3. Backup (plaintext) + health gate"
"$PY" manage.py backup_data --backup-root "$DRILL/backups" --keep 2 \
  || { bad "backup_data (plaintext)"; exit 1; }
"$PY" manage.py check_backups --backup-root "$DRILL/backups" --max-age-hours 1 \
  && ok "check_backups healthy" || bad "check_backups (plaintext)"
PLAIN_BACKUP="$(ls -1dt "$DRILL"/backups/backup-* | head -1)"
echo "   backup folder: $PLAIN_BACKUP"
grep -q '"credentials_included": false' "$PLAIN_BACKUP/manifest.json" \
  && ok "manifest records no credentials" || bad "manifest credentials marker"

step "4. Restore the plaintext backup into a separate disposable target"
if [[ "$MODE" == "sqlite" ]]; then RESTORE_URL="sqlite:///$DST_DB"; else RESTORE_URL="$PG_DST_URL"; fi
DATABASE_URL="$RESTORE_URL" "$PY" manage.py restore_backup \
  --backup "$PLAIN_BACKUP" \
  --media-dir "$DRILL/restored-media" --yes --verify \
  && ok "restore + verify passed" || { bad "restore_backup (plaintext)"; exit 1; }
PHOTO_DST="$DRILL/restored-media/$PHOTO_REL"
if [[ -f "$PHOTO_DST" ]] && [[ "$(sha256sum "$PHOTO_DST" | cut -d' ' -f1)" == "$PHOTO_SHA_SRC" ]]; then
  ok "restored photo is byte-identical"
else
  bad "restored photo missing or differs ($PHOTO_DST)"
fi
RESTORED_COUNT="$(DATABASE_URL="$RESTORE_URL" "$PY" manage.py shell --command "
from students.models import Student
print(Student.objects.count())
" 2>/dev/null | tail -1 | tr -d '\r')"
if [[ "$RESTORED_COUNT" == "1" ]]; then
  ok "restored database has the expected record count (1 student)"
else
  bad "restored record count is '$RESTORED_COUNT', expected 1"
fi

step "5. Encrypted round trip (BACKUP_ENCRYPTION=openssl)"
if command -v openssl >/dev/null 2>&1; then
  KEY_FILE="$DRILL/smoke-test.key"
  # A throwaway passphrase for the throwaway backup. Generated here, deleted
  # with the drill directory, never printed.
  (umask 077; openssl rand -base64 32 > "$KEY_FILE")
  BACKUP_ENCRYPTION=openssl BACKUP_PASSPHRASE_FILE="$KEY_FILE" \
    "$PY" manage.py backup_data --backup-root "$DRILL/backups" --keep 2 \
    && ok "encrypted backup created" || bad "backup_data (encrypted)"
  ENC_BACKUP="$(ls -1dt "$DRILL"/backups/backup-* | head -1)"
  echo "   backup folder: $ENC_BACKUP"
  if compgen -G "$ENC_BACKUP/*.enc" > /dev/null; then
    ok "artifacts on disk are encrypted (*.enc present)"
  else
    bad "no .enc artifact found in $ENC_BACKUP"
  fi
  if [[ -f "$ENC_BACKUP/db.sqlite3" || -f "$ENC_BACKUP/db.dump" ]]; then
    bad "a plaintext database artifact was left behind next to the ciphertext"
  else
    ok "no plaintext database left on disk"
  fi
  BACKUP_ENCRYPTION=openssl BACKUP_PASSPHRASE_FILE="$KEY_FILE" \
    "$PY" manage.py check_backups --backup-root "$DRILL/backups" --max-age-hours 1 \
    && ok "check_backups healthy on the encrypted backup" \
    || bad "check_backups (encrypted)"
  rm -rf "$DRILL/restored-media-enc" && mkdir -p "$DRILL/restored-media-enc"
  if [[ "$MODE" == "sqlite" ]]; then
    ENC_RESTORE_URL="sqlite:///$DRILL/dst-enc.sqlite3"
  else
    # Re-restore into the same drill database; pg_restore --clean handles it.
    ENC_RESTORE_URL="$PG_DST_URL"
  fi
  BACKUP_ENCRYPTION=openssl BACKUP_PASSPHRASE_FILE="$KEY_FILE" \
  DATABASE_URL="$ENC_RESTORE_URL" \
    "$PY" manage.py restore_backup \
      --backup "$ENC_BACKUP" \
      --media-dir "$DRILL/restored-media-enc" --yes --verify \
    && ok "encrypted restore + verify passed" || bad "restore_backup (encrypted)"
  PHOTO_ENC="$DRILL/restored-media-enc/$PHOTO_REL"
  if [[ -f "$PHOTO_ENC" ]] && [[ "$(sha256sum "$PHOTO_ENC" | cut -d' ' -f1)" == "$PHOTO_SHA_SRC" ]]; then
    ok "photo from the encrypted backup is byte-identical"
  else
    bad "photo from the encrypted backup missing or differs"
  fi
  # A wrong passphrase must NOT silently produce a "verified" restore.
  WRONG_KEY="$DRILL/wrong.key"
  (umask 077; openssl rand -base64 32 > "$WRONG_KEY")
  if [[ "$MODE" == "sqlite" ]]; then
    WRONG_URL="sqlite:///$DRILL/dst-wrong.sqlite3"
  else
    WRONG_URL="$pg_prefix/${PG_DST_NAME}_wrong"
    [[ -n "$pg_query" ]] && WRONG_URL="$WRONG_URL?$pg_query"
    "$PY" -c "
import os, psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
c = psycopg2.connect(os.environ['PG_BASE_DSN'])
c.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
c.cursor().execute('CREATE DATABASE ' + '${PG_DST_NAME}_wrong')
c.close()
" || bad "could not create the wrong-passphrase target database"
  fi
  if BACKUP_ENCRYPTION=openssl BACKUP_PASSPHRASE_FILE="$WRONG_KEY" \
     DATABASE_URL="$WRONG_URL" \
     "$PY" manage.py restore_backup \
       --backup "$ENC_BACKUP" --media-dir "$DRILL/restored-media-wrong" \
       --yes --verify > /dev/null 2>&1; then
    bad "restore with the WRONG passphrase unexpectedly succeeded"
  else
    ok "restore with a wrong passphrase is rejected"
  fi
  rm -f "$KEY_FILE" "$WRONG_KEY"
else
  echo "   skipped: openssl not on PATH (encryption path not exercised here)"
fi

step "6. Off-box copy is deliberately not exercised"
echo "   skipped: no bucket/credentials in a smoke test. The upload path is"
echo "   covered by unit tests with a stubbed S3 client; a real upload needs"
echo "   owner approval + a paid bucket (see docs/BACKUP_RESTORE_GUIDE.md)."

echo
echo "[smoke] disposable artifacts live under: $DRILL"
