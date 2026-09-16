# Backup & Restore Guide

_Last updated 2026-09-16 (backup tooling + data-safety session). Supersedes nothing:
`docs/BACKUP_AND_RESTORE.md` remains the tooling runbook; this guide is the
operator-facing "what do I run, in what order" document, and
`docs/DATA_SAFETY_STATUS.md` is the verified/unverified status record._

**বাংলা সংক্ষিপ্তসার:** এই গাইড বলে কোন পরিস্থিতিতে কোন কমান্ড চালাতে হবে।
ডেটাবেস ব্যাকআপ একটা `manage.py backup_data` কমান্ডে হয় (SQLite হলে consistent
snapshot, Postgres হলে `pg_dump`), ছবি/ডকুমেন্ট `media.tar.gz`-এ একই ফোল্ডারে যায়।
`manage.py check_backups` ব্যাকআপ সুস্থ কিনা বলে দেয় (exit 0 = ঠিক)।
`scripts/backup_smoke_test.sh` ফেলে-দেওয়া-যায়-এমন ডেটা দিয়ে পুরো
ব্যাকআপ→রিস্টর প্রক্রিয়া পরীক্ষা করে — লাইভ ডেটাবেস ছোঁয় না।
এখনো **লাইভ শিডিউল, অফ-বক্স বাকেট বা প্রোডাকশন রিস্টর চালু হয়নি** — সেগুলোর জন্য
মালিকের অনুমোদন ও (কিছু ক্ষেত্রে) পেইড সার্ভিস দরকার।

---

## 1. The one rule about databases

There is exactly **one writable database**: the one `DATABASE_URL` (or the local
`db.sqlite3`) points at. Everything else in this system is either

* a **read-only backup artifact** (`backups/backup-<stamp>/`), or
* a **disposable drill target** that is deleted when the drill ends.

Do not create a second or third "live" database "just to be safe". Two writable
databases means two divergent sets of student records, and no procedure in this
repo can tell you which one is true. Take more backups instead — they are cheap
and read-only. `scripts/backup_smoke_test.sh` enforces this: it asks Django which
database it resolved and aborts unless that file is inside its own drill
directory.

## 2. Which procedure for which failure

| What went wrong | Use | Detail |
|---|---|---|
| App crashes / bad deploy / 500s | Redeploy the previous build. **No restore.** Data is untouched. | §7 |
| Database lost or corrupt (disk, provider, bad migration) | Restore the newest good backup into the configured DB | §6 |
| Rows deleted or overwritten by mistake | Restore the newest backup **from before** the mistake; prefer restoring into a disposable copy and copying the rows back | §6.3 |
| Uploaded photos/documents missing | Restore `media.tar.gz`, or (with `USE_S3`) the bucket's versioned copy | §5, §6.4 |

The four cases are separated on purpose — see `docs/DATA_SAFETY_STATUS.md` for the
full taxonomy, blast radius and current status of each.

## 3. What a backup contains

```
backups/backup-20260916T163509Z/
├── db.sqlite3            # or db.dump for Postgres  (+ .enc when encrypted)
├── media.tar.gz          # MEDIA_ROOT: student_photos/, imported spreadsheets
└── manifest.json         # engine, artifact names, SHA-256, encryption scheme
```

* **Database** — engine auto-detected from `settings.DATABASES['default']`:
  * SQLite: `sqlite3` online-backup API, i.e. a frozen point-in-time snapshot
    that is consistent even while the app is writing.
  * Postgres: `pg_dump --format=custom --no-owner --no-privileges`.
  * Anything else: the backup is **refused**, not silently skipped.
* **Media** — a `.tar.gz` of `MEDIA_ROOT` (regular files only; symlinks are
  skipped on the way in and refused on the way out).
* **Manifest** — never contains credentials, connection strings or passphrases.
  It records the SHA-256 of the bytes on disk plus, for encrypted backups, the
  SHA-256 of the plaintext, so a restore can prove the decryption was correct.

## 4. Taking a backup

```bash
# Local / manual
.venv/bin/python manage.py backup_data                 # keep 7 (default)
.venv/bin/python manage.py backup_data --keep 30       # a month of dailies

# Scheduled (recommended entrypoint: backup + validate + health-check ping)
P0B_BACKUP_ROOT=/data/backups \
HEALTHCHECK_PING_URL=https://hc-ping.com/<uuid> \
  scripts/backup_cron.sh
```

Where backups are written: `--backup-root` → `$P0B_BACKUP_ROOT` → `./backups`.
**In production `P0B_BACKUP_ROOT` must be a persistent location.** A Render cron
job's disk is wiped after each run, so a local path there is a staging area, not
storage — pair it with the off-box copy (§5.2).

### 4.1 Retention

| Cadence | Command | Keeps |
|---|---|---|
| Daily | `backup_data --keep 7` at 02:00 | 1 week |
| Weekly | `backup_data --keep 4` (Sundays) | 1 month |
| Monthly | `backup_data --keep 6` (1st) | 6 months |
| Before any destructive deploy | one-off `scripts/backup.sh` | until reviewed |

Recommended: **daily keep 7 + monthly keep 6**, with the monthly set off-box.
Pruning only ever removes the oldest `backup-*` folders beyond `--keep`; it never
touches anything else in the folder's parent.

### 4.2 Encryption at rest

Backups hold names, guardian phone numbers and photos. Two independent layers:

```bash
# Layer 1 — file modes (always on): folder 0700, artifacts 0600.

# Layer 2 — encrypt the artifacts themselves (opt-in)
BACKUP_ENCRYPTION=openssl \
BACKUP_PASSPHRASE_FILE=/etc/sms/backup.key \
  .venv/bin/python manage.py backup_data
```

| Variable | Meaning |
|---|---|
| `BACKUP_ENCRYPTION` | `off` (default), `openssl` (AES-256-CBC + PBKDF2, 600 000 iterations) or `age` (X25519) |
| `BACKUP_PASSPHRASE_FILE` | Path to a `0600` file with the passphrase — **preferred** |
| `BACKUP_PASSPHRASE` | Passphrase in the environment (works, but shows up in the scheduler's env dump) |
| `BACKUP_AGE_RECIPIENT` / `BACKUP_AGE_IDENTITY_FILE` | Public key to encrypt with / private key file to decrypt with |

Rules:

* The passphrase **never** appears in argv, the manifest, a file name or the log.
* An unknown scheme is an error, not a silent fallback to plaintext.
* If encryption is requested and the tool (`openssl`/`age`) is missing, the
  backup **fails** rather than writing plaintext.
* `check_backups` fails when `BACKUP_ENCRYPTION` is set but the newest backup is
  plaintext, and when any artifact is group/other-readable.
* Losing the passphrase means losing the backup. Store it in the owner's password
  manager, separate from the server.

### 4.3 The off-box copy (independent storage)

A backup on the same disk as the database survives a bad deploy but not a lost
disk. Setting these variables makes every `backup_data` push one packed,
server-side-encrypted `.tar.gz` per backup folder:

```bash
BACKUP_OBJECT_STORAGE_BUCKET=sms-backups \
BACKUP_OBJECT_STORAGE_ACCESS_KEY=... \
BACKUP_OBJECT_STORAGE_SECRET_KEY=... \
BACKUP_OBJECT_STORAGE_ENDPOINT=https://<account>.r2.cloudflarestorage.com \
BACKUP_OBJECT_STORAGE_REGION=auto \
BACKUP_OBJECT_STORAGE_PREFIX=backups \
BACKUP_OBJECT_STORAGE_KEEP=30 \
  .venv/bin/python manage.py backup_data
```

* Works with any S3-compatible bucket (R2, B2, S3, MinIO) — `boto3` is already a
  project dependency, so nothing new to install.
* Uploaded with `ServerSideEncryption=AES256` on top of `BACKUP_ENCRYPTION`.
* Remote retention is bounded by `BACKUP_OBJECT_STORAGE_KEEP` (default 30).
* A half-configured bucket (name but no keys) is an **error**, not a warning:
  "backup succeeded" with no off-box copy is the worst possible outcome.
* `--no-upload` skips the copy for a one-off run.
* Use a **separate key scoped to the backup bucket** — least privilege, and it
  keeps a compromised media key from reaching the backups.

> **Not enabled yet.** This needs an owner-created bucket, a paid/allocated plan
> and an explicit decision. Until then `backup_data` prints
> `Off-box copy: not configured` and exits 0.

## 5. Verifying that backups are healthy

```bash
P0B_BACKUP_ROOT=/data/backups .venv/bin/python manage.py check_backups \
  --max-age-hours 48 --want-keep 7
```

Exit **0 = healthy**, non-zero = problem. It checks, for the newest backup:
manifest present and parseable; DB artifact present with a matching SHA-256;
media archive present with a matching SHA-256; freshness (a scheduler that
silently stopped becomes stale); retention not exceeding `--want-keep`;
encryption policy satisfied; and no world/group-readable file.

Point any monitor at that exit code, and set `HEALTHCHECK_PING_URL` so
`backup_cron.sh` reports both success and failure (`<url>` / `<url>/fail`).

### 5.1 Smoke test (disposable data)

```bash
scripts/backup_smoke_test.sh                 # SQLite, run and clean up
scripts/backup_smoke_test.sh --keep          # keep the drill directory
scripts/backup_smoke_test.sh --postgres postgres://user:pass@host:5432/postgres
```

Builds a throwaway database and a real uploaded photo, backs them up, runs
`check_backups`, restores into a **separate** throwaway target, verifies record
counts and that the photo is byte-identical — then repeats the whole thing with
`BACKUP_ENCRYPTION=openssl`, including a check that a wrong passphrase is
rejected. It never touches the real database, the real `MEDIA_ROOT`, or any
bucket, and it deletes everything afterwards.

`--postgres` runs the identical drill on the engine production is expected to
use: it creates two databases of its own (`sms_drill_src_<stamp>` /
`sms_drill_dst_<stamp>`), needs `pg_dump`/`pg_restore` on `PATH`, and drops both
databases on exit. CI runs both modes on every push
(`.github/workflows/tests.yml`), the Postgres one against the `postgres:16`
service.

> A passing smoke test proves the **procedure** works. It is not a production
> backup and must never be reported as one.

## 6. Restoring

### 6.1 Drill first (always)

```bash
DATABASE_URL=sqlite:///$PWD/.restore-drill/db.sqlite3 \
  scripts/restore.sh --backup backup-20260916T163509Z \
    --media-dir "$PWD/.restore-drill/media" --yes --verify
```

`--verify` re-checks the artifact SHA-256, decrypts and checks the plaintext
digest when encrypted, runs `migrate --check`, prints sentinel record counts, and
confirms every `ImageField`/`FileField` reference resolves to a real file (on
disk, or in the bucket when `USE_S3` is on).

### 6.2 Production restore

1. Stop writes (scale the web service to zero / put the app in maintenance).
2. Confirm the target: print `DATABASE_URL`'s host+dbname. Restoring always
   targets the **configured** database; there is no "restore somewhere else"
   switch — point `DATABASE_URL` elsewhere if that is what you mean.
3. Take a safety backup of the current state first: `scripts/backup.sh`.
   An accidental restore must be reversible.
4. `scripts/restore.sh --backup <folder> --yes --verify`
   (add `BACKUP_PASSPHRASE_FILE=...` for an encrypted backup).
5. Restart, then check a student list page and one student photo.

Postgres: `pg_restore --clean --if-exists` needs `pg_dump`/`pg_restore` in the
runtime and the `PG*` environment (from `DATABASE_URL`). Credentials travel in
the child process's environment, never in argv.

### 6.3 Accidental deletion — the safer variant

A full restore also rewinds everything that happened *after* the backup. For a
single bad delete, restore into a disposable copy and move the rows back:

```bash
DATABASE_URL=sqlite:///$PWD/.restore-drill/recover.sqlite3 \
  .venv/bin/python manage.py restore_backup --backup <folder> --yes
# then inspect/re-export the rows you need from that copy
```

`AuditLog` records edits and deletions with a `snapshot` of the row, which is
often enough to reconstruct a single record without any restore at all.

### 6.4 Media loss

* **Filesystem media:** `media.tar.gz` from the backup restores the whole tree.
* **`USE_S3=True`:** the bucket is the copy of record. `restore_backup` refuses
  to extract into a local `MEDIA_ROOT` that the app will never read; pass
  `--media-dir <staging>` and push it with `manage.py copy_media_to_storage`, or
  restore the bucket's own versioned copy. **Enable bucket versioning** — it is
  the only undo for a deleted object.

## 7. App failure is not a data problem

A crash, a 500, or a broken deploy is fixed by redeploying the previous build.
Restoring the database in response to an app bug destroys newer records for no
reason. Restore only when the **data** is wrong or gone.

## 8. Before any destructive operation (hard rule)

Migrations that drop data, `merge_duplicate_subjects --apply`,
`clean_student_groups --apply`, and the purge endpoints are irreversible. Run
`scripts/backup.sh` immediately beforehand and confirm:

1. the newest `backups/backup-*` folder exists with a `manifest.json`;
2. `check_backups` exits 0;
3. a `restore_backup --verify-only` on it passes.

## 9. What is *not* enabled (needs owner approval)

| Item | Why it is not on | What it needs |
|---|---|---|
| Live scheduled backup | Render Cron Jobs have no free tier and no persistent disk | Owner: paid cron + `P0B_BACKUP_ROOT` decision (`render.cron.yaml` is ready, unapplied) |
| Off-box object storage | Paid/allocated bucket + a key decision | Owner: bucket + scoped key, then set `BACKUP_OBJECT_STORAGE_*` |
| Health-check alerting | Needs an account + UUID | Owner: create the check, set `HEALTHCHECK_PING_URL` |
| Production restore rehearsal | Must not run against live data | Owner: approved maintenance window + a copy of the real DB |
| Postgres backup path in production | Drill-verified locally (PostgreSQL 16.2) and in CI, but never against the production server | P-1: confirm the runtime has the client tools and the engine matches |

Full status, including what was and was not verified locally:
`docs/DATA_SAFETY_STATUS.md`.
