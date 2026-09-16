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
#   * every BACKUP_* variable is UNSET before the drill starts, because
#     python-dotenv would otherwise hand the drill the operator's real
#     encryption passphrase and — worse — the real off-box bucket, where the
#     drill's throwaway bundles would be uploaded and its retention pruning
#     could delete genuine backups;
#   * the plaintext/encrypted steps also pass --no-upload as a second lock;
#   * before doing anything it asks Django which database it resolved and ABORTS
#     unless that target is the drill's own (a file inside the drill directory,
#     or one of the drill databases this script just created) — so a stray
#     production DATABASE_URL cannot be hit by accident;
#   * with --s3-endpoint the off-box round trip runs against THAT endpoint only
#     (a local mock such as moto/MinIO), in a bucket this script creates;
#   * everything is deleted on the way out unless --keep is given.
#
# Usage:
#   scripts/backup_smoke_test.sh                     # SQLite, disposable file
#   scripts/backup_smoke_test.sh --keep              # keep the drill artifacts
#   scripts/backup_smoke_test.sh --postgres postgres://postgres@localhost:5432/postgres
#   scripts/backup_smoke_test.sh --s3-endpoint http://127.0.0.1:5055
#
# In --postgres mode the script creates two databases of its own
# (sms_drill_src_<stamp> / sms_drill_dst_<stamp>) on that server and drops them
# on exit; it needs pg_dump/pg_restore on PATH.
#
# With --s3-endpoint it additionally proves the off-box copy is a *restore
# source* and not just a write: upload, `check_backups --check-remote`,
# `fetch_backup` back to a clean directory, restore from the fetched copy, and
# remote retention pruning. Point it at a mock (moto, MinIO) — never at a real
# bucket: the drill creates and empties the bucket it is given.
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
S3_ENDPOINT=""
S3_BUCKET="sms-drill-backups"
S3_REGION="us-east-1"
S3_PREFIX="drill-backups"
# Dummy credentials for a mock endpoint (moto/MinIO accept anything). They are
# literals for a throwaway bucket on localhost — not secrets, and never used
# against a real provider.
S3_ACCESS_KEY="drill-access-key"
S3_SECRET_KEY="drill-secret-key"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --keep) KEEP_DIR=1; shift ;;
    --postgres) MODE="postgres"; PG_BASE_URL="${2:-}"; shift 2 ;;
    --s3-endpoint) S3_ENDPOINT="${2:-}"; shift 2 ;;
    --s3-bucket) S3_BUCKET="${2:-}"; shift 2 ;;
    --s3-region) S3_REGION="${2:-}"; shift 2 ;;
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
export DRILL_BUCKET_MARKER="$DRILL/.bucket-created-by-drill"

if [[ "$MODE" == "sqlite" ]]; then
  SRC_DB="$DRILL/src.sqlite3"
  DST_DB="$DRILL/dst.sqlite3"
  export DATABASE_URL="sqlite:///$SRC_DB"
else
  export DATABASE_URL="$PG_SRC_URL"
fi
export MEDIA_ROOT="$DRILL/media"
unset USE_S3 AWS_STORAGE_BUCKET_NAME 2>/dev/null || true

# Hermetic drill: drop every backup-related variable the operator's .env (or
# shell) might have set. Without this, a configured off-box bucket would
# receive the drill's throwaway bundles — and the drill's own retention pruning
# (BACKUP_OBJECT_STORAGE_KEEP) could delete real backups. Encryption variables
# are cleared too so step 3 really is the plaintext path.
INHERITED_BACKUP_VARS="$(env | grep -oE '^(BACKUP_[A-Z0-9_]+|P0B_BACKUP_ROOT|KEEP_BACKUPS)=' | tr -d '=' | tr '\n' ' ')"
if [[ -n "${INHERITED_BACKUP_VARS//[[:space:]]/}" ]]; then
  echo "[smoke] cleared inherited backup configuration: ${INHERITED_BACKUP_VARS}"
  for _var in ${INHERITED_BACKUP_VARS}; do unset "${_var:?}"; done
fi
unset _var INHERITED_BACKUP_VARS

cleanup() {
  local rc=$?
  if [[ -n "$S3_ENDPOINT" && -n "${BACKUP_OBJECT_STORAGE_BUCKET:-}" ]]; then
    if "$PY" - <<'PYEOF'
import os
from pathlib import Path
import boto3
from botocore.config import Config

client = boto3.client(
    "s3",
    endpoint_url=os.environ["BACKUP_OBJECT_STORAGE_ENDPOINT"],
    region_name=os.environ.get("BACKUP_OBJECT_STORAGE_REGION") or None,
    aws_access_key_id=os.environ["BACKUP_OBJECT_STORAGE_ACCESS_KEY"],
    aws_secret_access_key=os.environ["BACKUP_OBJECT_STORAGE_SECRET_KEY"],
    config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
)
bucket = os.environ["BACKUP_OBJECT_STORAGE_BUCKET"]
prefix = os.environ.get("BACKUP_OBJECT_STORAGE_PREFIX", "drill-backups") + "/"
keys = []
for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
    keys += [o["Key"] for o in page.get("Contents", []) or []]
if keys:
    client.delete_objects(Bucket=bucket,
                          Delete={"Objects": [{"Key": k} for k in keys], "Quiet": True})
# Only a bucket this script created may be deleted again.
marker = Path(os.environ["DRILL_BUCKET_MARKER"])
if marker.exists() and marker.read_text().strip() == bucket:
    client.delete_bucket(Bucket=bucket)
    print("deleted the drill bucket")
else:
    print("emptied the drill prefix, bucket left in place")
PYEOF
    then echo "[smoke] cleaned up the drill bucket ($S3_BUCKET)"
    else echo "[smoke] could not clean the drill bucket ($S3_BUCKET) — remove it by hand" >&2
    fi
  fi
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
"$PY" manage.py backup_data --backup-root "$DRILL/backups" --keep 2 --no-upload \
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
    "$PY" manage.py backup_data --backup-root "$DRILL/backups" --keep 2 --no-upload \
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

step "6. Off-box copy round trip (upload -> gate -> fetch -> restore)"
if [[ -z "$S3_ENDPOINT" ]]; then
  echo "   skipped: no --s3-endpoint given, so there is no bucket to talk to."
  echo "   A real bucket must never be part of a drill (it would receive"
  echo "   throwaway bundles, and the drill's own retention could prune real"
  echo "   backups), so this path only runs against a mock you start yourself:"
  echo
  echo "     moto_server -H 127.0.0.1 -p 5055 &      # or: minio server /tmp/minio"
  echo "     scripts/backup_smoke_test.sh --s3-endpoint http://127.0.0.1:5055"
  echo
  echo "   The upload/fetch code is also covered by unit tests with a stubbed"
  echo "   S3 client (students/test_backup_tooling.py)."
else
  export BACKUP_OBJECT_STORAGE_BUCKET="$S3_BUCKET"
  export BACKUP_OBJECT_STORAGE_ACCESS_KEY="$S3_ACCESS_KEY"
  export BACKUP_OBJECT_STORAGE_SECRET_KEY="$S3_SECRET_KEY"
  export BACKUP_OBJECT_STORAGE_ENDPOINT="$S3_ENDPOINT"
  export BACKUP_OBJECT_STORAGE_REGION="$S3_REGION"
  export BACKUP_OBJECT_STORAGE_PREFIX="$S3_PREFIX"
  export BACKUP_OBJECT_STORAGE_KEEP=2
  OFFBOX="$DRILL/backups-offbox"
  FETCHED="$DRILL/fetched"
  mkdir -p "$OFFBOX" "$FETCHED"

  # 6.0 The drill bucket. Created here; the marker file is what tells cleanup
  #     it may delete the bucket again (an operator's pre-existing bucket is
  #     only emptied of this drill's objects, never removed).
  if "$PY" - <<'PYEOF'
import os
import boto3
from botocore.config import Config

client = boto3.client(
    "s3",
    endpoint_url=os.environ["BACKUP_OBJECT_STORAGE_ENDPOINT"],
    region_name=os.environ.get("BACKUP_OBJECT_STORAGE_REGION") or None,
    aws_access_key_id=os.environ["BACKUP_OBJECT_STORAGE_ACCESS_KEY"],
    aws_secret_access_key=os.environ["BACKUP_OBJECT_STORAGE_SECRET_KEY"],
    config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
)
bucket = os.environ["BACKUP_OBJECT_STORAGE_BUCKET"]
try:
    client.head_bucket(Bucket=bucket)
    print(f"   drill bucket already exists: {bucket}")
except Exception:
    client.create_bucket(Bucket=bucket)
    print(f"   created drill bucket: {bucket}")
    with open(os.environ["DRILL_BUCKET_MARKER"], "w") as fh:
        fh.write(bucket)
PYEOF
  then ok "drill bucket ready: $S3_BUCKET at $S3_ENDPOINT"; else bad "could not prepare the drill bucket"; exit 1; fi

  # 6.1 A backup that actually uploads.
  if OFFBOX_OUT="$("$PY" manage.py backup_data --backup-root "$OFFBOX" --keep 3 2>&1)"; then
    ok "backup_data ran with the off-box copy configured"
  else
    echo "$OFFBOX_OUT"; bad "backup_data (off-box)"; exit 1
  fi
  if grep -q "Off-box copy: s3://$S3_BUCKET/" <<<"$OFFBOX_OUT"; then
    ok "off-box copy uploaded: $(grep -oE 's3://[^ ]+' <<<"$OFFBOX_OUT" | head -1)"
  else
    echo "$OFFBOX_OUT"; bad "backup_data did not report an off-box upload"
  fi
  OFFBOX_BACKUP="$(basename "$(ls -1dt "$OFFBOX"/backup-* | head -1)")"

  # 6.2 The health gate must see the remote copy — and must fail without it.
  if "$PY" manage.py check_backups --backup-root "$OFFBOX" --max-age-hours 1 \
       --check-remote >/dev/null 2>&1; then
    ok "check_backups --check-remote confirms the copy is off-box"
  else
    bad "check_backups --check-remote failed on a backup that was uploaded"
  fi
  if BACKUP_OBJECT_STORAGE_PREFIX="no-such-prefix" \
     "$PY" manage.py check_backups --backup-root "$OFFBOX" --max-age-hours 1 \
       --check-remote >/dev/null 2>&1; then
    bad "--check-remote passed even though the off-box copy is missing"
  else
    ok "--check-remote fails when the off-box copy is missing"
  fi

  # 6.3 Read it back: an off-box copy nobody has downloaded is an assumption.
  if "$PY" manage.py fetch_backup --latest --dest "$FETCHED" >/dev/null 2>&1; then
    ok "fetch_backup downloaded the newest bundle"
  else
    "$PY" manage.py fetch_backup --latest --dest "$FETCHED" || true
    bad "fetch_backup --latest"; exit 1
  fi
  if [[ -f "$FETCHED/$OFFBOX_BACKUP/manifest.json" ]]; then
    ok "fetched bundle unpacked and verified against its own manifest"
  else
    bad "the fetched bundle did not produce $OFFBOX_BACKUP/manifest.json"
  fi
  if "$PY" manage.py check_backups --backup-root "$FETCHED" --max-age-hours 1 \
       >/dev/null 2>&1; then
    ok "the fetched copy passes the local health gate (SHA-256 intact)"
  else
    bad "the fetched copy failed the local health gate"
  fi

  # 6.4 Restore from the fetched copy into a fresh disposable target.
  rm -rf "$DRILL/restored-media-offbox" && mkdir -p "$DRILL/restored-media-offbox"
  if [[ "$MODE" == "sqlite" ]]; then
    OFFBOX_RESTORE_URL="sqlite:///$DRILL/dst-offbox.sqlite3"
  else
    OFFBOX_RESTORE_URL="$PG_DST_URL"   # pg_restore --clean reuses the drill DB
  fi
  if DATABASE_URL="$OFFBOX_RESTORE_URL" "$PY" manage.py restore_backup \
       --backup "$FETCHED/$OFFBOX_BACKUP" \
       --media-dir "$DRILL/restored-media-offbox" --yes --verify >/dev/null 2>&1; then
    ok "restore from the off-box copy verified"
  else
    DATABASE_URL="$OFFBOX_RESTORE_URL" "$PY" manage.py restore_backup \
      --backup "$FETCHED/$OFFBOX_BACKUP" \
      --media-dir "$DRILL/restored-media-offbox" --yes --verify || true
    bad "restore_backup from the fetched off-box copy"
  fi
  PHOTO_OFFBOX="$DRILL/restored-media-offbox/$PHOTO_REL"
  if [[ -f "$PHOTO_OFFBOX" ]] && \
     [[ "$(sha256sum "$PHOTO_OFFBOX" | cut -d' ' -f1)" == "$PHOTO_SHA_SRC" ]]; then
    ok "photo restored from the off-box copy is byte-identical"
  else
    bad "photo from the off-box copy is missing or differs"
  fi
  OFFBOX_COUNT="$(DATABASE_URL="$OFFBOX_RESTORE_URL" "$PY" manage.py shell --command "
from students.models import Student
print(Student.objects.count())
" 2>/dev/null | tail -1 | tr -d '\r')"
  if [[ "$OFFBOX_COUNT" == "1" ]]; then
    ok "database restored from the off-box copy has the expected record count"
  else
    bad "record count after the off-box restore is '$OFFBOX_COUNT', expected 1"
  fi

  # 6.5 Remote retention: BACKUP_OBJECT_STORAGE_KEEP=2 must bound the bucket.
  for _run in 1 2; do
    "$PY" manage.py backup_data --backup-root "$OFFBOX" --keep 3 >/dev/null 2>&1 \
      || bad "backup_data (retention run $_run)"
    sleep 1   # keep the folder names distinct (stamps are second-resolution)
  done
  REMOTE_LIST="$("$PY" - <<'PYEOF'
import os
import boto3
from botocore.config import Config

client = boto3.client(
    "s3",
    endpoint_url=os.environ["BACKUP_OBJECT_STORAGE_ENDPOINT"],
    region_name=os.environ.get("BACKUP_OBJECT_STORAGE_REGION") or None,
    aws_access_key_id=os.environ["BACKUP_OBJECT_STORAGE_ACCESS_KEY"],
    aws_secret_access_key=os.environ["BACKUP_OBJECT_STORAGE_SECRET_KEY"],
    config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
)
prefix = os.environ["BACKUP_OBJECT_STORAGE_PREFIX"] + "/"
keys = []
for page in client.get_paginator("list_objects_v2").paginate(
        Bucket=os.environ["BACKUP_OBJECT_STORAGE_BUCKET"], Prefix=prefix):
    keys += [o["Key"] for o in page.get("Contents", []) or []]
print(len(keys))
for key in sorted(keys):
    print(key)
PYEOF
)"
  REMOTE_COUNT="$(head -1 <<<"$REMOTE_LIST")"
  if [[ "$REMOTE_COUNT" == "2" ]]; then
    ok "remote retention kept exactly BACKUP_OBJECT_STORAGE_KEEP=2 bundles"
  else
    echo "$REMOTE_LIST"; bad "remote retention left $REMOTE_COUNT bundle(s), expected 2"
  fi
  NEWEST_LOCAL="$(basename "$(ls -1dt "$OFFBOX"/backup-* | head -1)")"
  if grep -q "$NEWEST_LOCAL.tar.gz" <<<"$REMOTE_LIST"; then
    ok "the newest backup is among the bundles still off-box ($NEWEST_LOCAL)"
  else
    echo "$REMOTE_LIST"; bad "the newest backup ($NEWEST_LOCAL) was pruned off-box"
  fi
fi

echo
echo "[smoke] disposable artifacts live under: $DRILL"
