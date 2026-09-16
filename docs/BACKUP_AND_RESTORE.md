# Backup & Restore Runbook

_Last updated 2026-09-16 (second data-safety session: the off-box copy became a
**restore source** — `fetch_backup`, `check_backups --check-remote`, and an
end-to-end off-box drill; two real restore bugs fixed — stale SQLite
journal/WAL sidecars and the `age` decryption path; new deployment checks).
Earlier the same day: encryption at rest, file-mode hardening, the off-box
object-storage copy, media/backend-aware restore verification, and
`scripts/backup_smoke_test.sh`. Original: 2026-09-09 (P0-8 backup session;
+ ops readiness: `check_backups`, `backup_cron.sh`, `render.cron.yaml`; owner
tutorial `docs/OWNER_RENDER_OPS_TUTORIAL.md`)._

> **Read these first:** `docs/BACKUP_RESTORE_GUIDE.md` is the operator guide
> (which command for which failure), and `docs/DATA_SAFETY_STATUS.md` is the
> verified / unverified status record. This page stays the detailed tooling
> runbook.

This runbook describes how to back up and restore the School Management System
across both supported database engines (SQLite, the local default, and
Postgres, used via `DATABASE_URL` in production) and the uploaded-file tree
(student photos) under `MEDIA_ROOT`.

The tooling is two Django management commands plus thin cron-friendly wrappers:

| Command | Purpose |
|---|---|
| `manage.py backup_data` | Create a consistent DB + media snapshot, write a manifest, prune old backups. |
| `manage.py restore_backup` | Restore a backup folder into the configured DB + media dir (destructive, needs `--yes`). |
| `manage.py check_backups` | Backup health gate: verify newest backup (manifest, DB SHA, media SHA, freshness, retention, encryption policy, file modes, and with `--check-remote` that the off-box copy exists); **exit 0 = healthy, non-zero = problem** (for alerting). |
| `manage.py fetch_backup` | Read the off-box copy back: `--list` the bucket, or download a bundle (`--latest` / `--key`), verify it against its manifest and unpack it where `restore_backup` can use it. Read-only — it never writes to the database. |
| `scripts/backup.sh` | Wrapper around `backup_data` for cron; returns a usable exit code. |
| `scripts/restore.sh` | Wrapper around `restore_backup`. |
| `scripts/backup_cron.sh` | Backup + validate + external health-check ping; the recommended cron entrypoint. |
| `scripts/backup_smoke_test.sh` | End-to-end backup → restore drill on **disposable** data (plaintext, encrypted, and — with `--s3-endpoint` — the off-box upload/fetch/restore round trip), then cleans up. Never touches the real DB/MEDIA_ROOT, and clears any inherited `BACKUP_*` env first. |

> **Security rule:** the backup artifact and manifest **never contain
> credentials**. For Postgres the dump is produced by `pg_dump`/`pg_restore`
> driven through the `PG*` environment variables (not argv) so no password is
> written to a log, `ps`, or a file. The same applies to the backup passphrase
> (`openssl -pass env:VAR`) and the object-storage keys (boto3 client kwargs).
>
> **Access control:** backup folders are created `0700` and every artifact and
> manifest `0600`. `check_backups` fails if anything is group/other-readable.

---

## 1. What is backed up

1. **Database** — engine is auto-detected from `settings.DATABASES['default']`:
   - SQLite: a consistent online-backup snapshot (`sqlite3` backup API) so the
     file is frozen mid-write.
   - Postgres: `pg_dump --format=custom` → `db.dump` (restores with
     `pg_restore --clean`).
   - Any other engine: the backup is refused.
2. **Uploaded files** — a `.tar.gz` of `MEDIA_ROOT` (default `BASE_DIR/media`,
   containing `student_photos/...`). Only regular files are archived; symlinks
   are skipped on the way in and refused on the way out.

## 2. Taking a backup

```bash
# From the repo root, using the existing virtualenv:
.venv/bin/python manage.py backup_data                # default keep 7
.venv/bin/python manage.py backup_data --keep 30      # keep a month of dailies

# Cron-friendly (redirect output to a log for failure reporting):
P0B_BACKUP_ROOT=/mnt/backups scripts/backup.sh >> /var/log/sms-backup.log 2>&1
```

Every run writes a folder `backups/backup-<UTCtimestamp>/` into:

- `./backups` by default, or
- `$P0B_BACKUP_ROOT`, or
- `--backup-root <path>`.

Each folder contains `db.sqlite3` or `db.dump`, `media.tar.gz` (if any files),
and `manifest.json`.

### Backup options

| Flag / env | Meaning |
|---|---|
| `--keep N` (default 7) | Keep the N newest backup folders; prune older ones. |
| `--media-dir PATH` | Override the media source (used by the disposable drill). |
| `--backup-root PATH` | Override where backups are written. |
| `P0B_BACKUP_ROOT` | Env form of `--backup-root`. |

## 2b. Encryption at rest and the off-box copy

Both are opt-in through env and both are covered in detail in
`docs/BACKUP_RESTORE_GUIDE.md` §4.2–§4.3. Summary:

```bash
# Encrypt the artifacts (AES-256-CBC + PBKDF2/600k via openssl, or age)
BACKUP_ENCRYPTION=openssl BACKUP_PASSPHRASE_FILE=/etc/sms/backup.key \
  .venv/bin/python manage.py backup_data

# Push an independent copy to an S3-compatible bucket (needs all three)
BACKUP_OBJECT_STORAGE_BUCKET=sms-backups \
BACKUP_OBJECT_STORAGE_ACCESS_KEY=... BACKUP_OBJECT_STORAGE_SECRET_KEY=... \
  .venv/bin/python manage.py backup_data
```

* Encrypted artifacts are written as `db.sqlite3.enc` / `media.tar.gz.enc` and the
  plaintext is deleted immediately; the manifest records the scheme and both the
  ciphertext and the plaintext SHA-256, so `restore_backup --verify` can prove the
  decryption produced the original bytes.
* An unknown `BACKUP_ENCRYPTION` value, a missing passphrase, or a missing
  `openssl`/`age` binary is a **hard error** — never a silent plaintext backup.
* `restore_backup` decrypts into a private temporary directory that is removed on
  the way out; a wrong passphrase fails the verification instead of restoring
  garbage.
* The off-box bundle is one packed `.tar.gz` per backup folder, uploaded with
  `ServerSideEncryption=AES256`, pruned to `BACKUP_OBJECT_STORAGE_KEEP` (30).
  `--no-upload` skips it. **Not enabled in any environment yet** — it needs an
  owner-created bucket and key.
* The copy is readable back, which is what makes it a backup and not a write-only
  artifact:

  ```bash
  manage.py fetch_backup --list                  # what the bucket holds
  manage.py fetch_backup --latest                # download + verify + unpack
  manage.py fetch_backup --key backups/backup-<stamp>.tar.gz --dest /mnt/scratch
  ```

  `fetch_backup` downloads into a private temp dir, validates every tar member
  (no absolute paths, no `..`, no links), unpacks with `0700`/`0600` modes and
  then checks each artifact against the SHA-256 the bundle's own manifest
  records — a truncated off-box copy fails here, not halfway through a 2 a.m.
  restore. A broken fetch is deleted rather than left where
  `restore_backup --backup <name>` could pick it up.
* `check_backups --check-remote` is the gate that catches an upload which quietly
  stopped (rotated key, renamed bucket, expired credential): the newest local
  backup must exist in the bucket and be non-empty. `scripts/backup_cron.sh`
  passes it automatically as soon as `BACKUP_OBJECT_STORAGE_BUCKET` is set
  (`BACKUP_SKIP_REMOTE_CHECK=1` skips one run). A credentials/network error is
  reported as an error, never as "copy missing".

## 3. Retention guidance

Default is **keep 7**. Pick a scheme to fit your storage and risk appetite:

| Backup type | Cadence | `--keep` | Keeps roughly |
|---|---|---|---|
| Daily | every day at 02:00 | 7 | 1 week |
| Weekly | every Sunday | 4 | 1 month |
| Monthly | 1st of month | 6 | 6 months |
| Before a destructive deploy | one-off, manually | n/a | until reviewed |

Start with **daily keep 7 + a monthly keep 6**, and store the monthly set off-box
(with the owner) so a single disk failure cannot destroy both the live DB and its
backups. Older backups are pruned only by the command — a backup is never
auto-kept forever.

### Storage sizing

The SQLite file is small today (~0.5 MB) but grows with student records and
uploaded photos. `Media archive` is usually the largest artifact (photos are the
bulk). Monitor `du -sh backups/` and raise `--keep`/lower it accordingly.

## 4. Failure reporting

The commands write progress to stdout and **exit non-zero on any failure**, which
is what a scheduler watches. Wrap in `scripts/backup.sh` and pipe to a log:

```bash
0 2 * * *  /path/to/repo/scripts/backup.sh >> /var/log/sms-backup.log 2>&1
```

A non-zero exit means the backup incomplete. The command also removes the
half-written backup folder so a failed run can never be mistaken for a good one.

`check_backups` complements `backup_data` as the **scheduler-facing health gate**:
it re-opens the newest backup and verifies the manifest, the DB artifact SHA-256
(good against a truncated/corrupt file), the **media archive SHA-256**, freshness
(`--max-age-hours`, default 48 — a scheduled backup that silently stopped
producing new folders becomes stale), retention sanity (more folders than
`--keep` means pruning is not running), **encryption policy** (a plaintext backup
fails when `BACKUP_ENCRYPTION` is set), **file modes** (anything
group/other-readable fails), and — with `--check-remote` — that the newest backup
**exists in the off-box bucket** and is not empty.
It exits **0 when healthy, non-zero on any problem**. A fresh install with fewer
folders than `--keep` is normal and not an error.

```bash
# Cron-style wrapper that takes the backup, validates it, and pings a health check:
P0B_BACKUP_ROOT=/mnt/backups HEALTHCHECK_PING_URL=https://hc-ping.com/<uuid> \
  scripts/backup_cron.sh

# Or wire `check_backups` alone to an uptime/heartbeat monitor:
P0B_BACKUP_ROOT=/mnt/backups python manage.py check_backups --max-age-hours 48
```

**To alert:** point a scheduler (Render cron, Jenkins, GitHub Actions, Uptime
Robot, Healthchecks.io, etc.) at the exit status / log tail. `scripts/backup_cron.sh`
pings an external health check on success/failure when `HEALTHCHECK_PING_URL` is
set (never hard-coded). See §8 for the ready-to-apply Render cron config.

## 5. Restoring

```bash
.venv/bin/python manage.py restore_backup \
  --backup backup-20260909T035337Z \
  --yes
```

- `--backup` can be a folder name under `backups/`, or a full path.
- `--yes` **must** be passed; without it the command refuses. Restoring
  **overwrites** the configured database and `MEDIA_ROOT` with the backup.
- `--verify` runs post-restore integrity checks (DB SHA, `migrate --check`,
  sentinel record counts, and that every `ImageField`/`FileField` reference
  resolves to a file on disk).

### SQLite note (journal / WAL sidecars)

A SQLite database is more than its main file: `db.sqlite3-wal` + `-shm`
(write-ahead log) and `db.sqlite3-journal` (rollback journal) hold committed and
half-committed state. Replacing only the main file — what a naïve
`cp backup/db.sqlite3 db.sqlite3` does — leaves the old sidecars in place, and
**SQLite replays them over the restored file on the next open**. Reproduced
locally: the reader saw the pre-restore rows while `PRAGMA integrity_check`
reported `ok`, i.e. a restore that succeeded, verified, and restored nothing.

`restore_backup` therefore closes all Django connections, deletes any stale
`-wal`/`-shm`/`-journal` next to the target, copies the snapshot, re-reads it and
compares its SHA-256 with the snapshot's (a partial copy is an error, not a
warning), and chmods the result `0600`. Removed sidecar files are named in the
output — their presence means the previous database died mid-write.

### Postgres note

`pg_restore --clean --if-exists` is used, so the target database must exist and
be reachable via the `PG*` env. The destination is the **configured** database
(e.g. `DATABASE_URL`); there is no "restore to a different DB" switch — point
`DATABASE_URL` at the target if you want a different one.

Before overwriting anything, `restore_backup` prints the row counts currently in
the target, so the size of what is about to be replaced is visible.

### Media note (`USE_S3`)

When uploads live in a bucket, extracting `media.tar.gz` into a local
`MEDIA_ROOT` would look like a successful restore and change nothing the app ever
reads. `restore_backup` therefore **refuses** that combination: pass
`--media-dir <staging>` and push with `manage.py copy_media_to_storage`, or
restore the bucket's own versioned copy. With `USE_S3` on, `--verify` checks file
references against the storage backend instead of the local disk.

## 6. Restore drill (disposable only)

This is a dry run against **throwaway** storage. It never touches the real DB or
media. It proves the backup can be restored and that the app boots and data/files
are intact. Run it any time before a destructive deploy.

**Automated version:** `scripts/backup_smoke_test.sh` does all of the below in
one command, on disposable data, with a guard that aborts unless the resolved
database is the drill's own (so a stray `DATABASE_URL` can never be hit). It also
runs the whole cycle again with `BACKUP_ENCRYPTION=openssl` and checks that a
wrong passphrase is rejected. Exit 0 = every step passed.

```bash
scripts/backup_smoke_test.sh                 # SQLite
scripts/backup_smoke_test.sh --postgres postgres://user:pass@host:5432/postgres
scripts/backup_smoke_test.sh --s3-endpoint http://127.0.0.1:5055   # + off-box round trip
```

`--postgres` creates its own two drill databases, exercises `pg_dump`/
`pg_restore`, and drops them on exit. Both modes run in CI on every push.

`--s3-endpoint` adds the off-box round trip against an S3-compatible endpoint you
start yourself (`moto_server -H 127.0.0.1 -p 5055`, or a local MinIO): create the
drill bucket → `backup_data` uploads → `check_backups --check-remote` sees it (and
fails when the prefix is wrong) → `fetch_backup --latest` brings it back and
verifies it → `restore_backup` restores **from the fetched copy** into a fresh
disposable target → the photo is byte-identical → two more backups prove
`BACKUP_OBJECT_STORAGE_KEEP` prunes the remote set. The bucket is emptied and (if
the drill created it) deleted on exit. CI runs this leg too, against moto.

The drill is hermetic: it unsets every inherited `BACKUP_*` / `P0B_BACKUP_ROOT`
variable and passes `--no-upload` on the local steps, so an operator's real
bucket can never receive drill bundles or be pruned by them.

```bash
# 1. Disposable source: a throwaway SQLite DB + media file.
rm -rf .restore-drill && mkdir -p .restore-drill
export DATABASE_URL="sqlite:///$PWD/.restore-drill/src.sqlite3"
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py loaddata students/fixtures/institutions.json
# (add a student + a photo file to exercise file integrity — see §7.)

# 2. Back up that source.
P0B_BACKUP_ROOT=.restore-drill/backups \
  .venv/bin/python manage.py backup_data --media-dir ... --keep 3

# 3. Restore into a *separate* disposable destination, then verify.
export DATABASE_URL="sqlite:///$PWD/.restore-drill/dst.sqlite3"
.venv/bin/python manage.py restore_backup \
  --backup .restore-drill/backups/backup-<...> \
  --media-dir .restore-drill/dst-media --yes --verify
```

Expected (and what I saw in this session's drill): `DB artifact SHA-256 OK`,
`migrate --check OK`, sentinel record counts match, `Media references OK`, the
app boots (`.venv/bin/python manage.py check` clean, a page renders), and the
restored uploaded file is byte-identical (`sha256sum` matches).

> **Important:** a successful *test* restore proves the procedure works on
> disposable data. It is **not** the same as having taken a live production
> backup. Only a backup actually produced from the production database counts as
> the live backup.

## 7. What the drill verifies

- **Record integrity:** sentinel model counts (e.g. `Institutions`, `Users`,
  `Students`) equal the source after restore; `migrate --check` is clean.
- **File integrity:** `sha256` of the restored media file matches the original;
  and `_check_media_files` walks every `ImageField`/`FileField` and asserts the
  referenced file exists under the media root.
- **App boots:** Django `check`/`migrate --check` run against the restored DB and
  a page renders without error.

## 8. Production scheduling / external storage — needs owner access & approval

The tooling here is ready to use, and the **ops config is now prepared**; the
**live scheduling is not wired and the off-box bucket does not exist**, because
they need production-level access, a paid plan, and decisions this session must
not assume (rule 7).

**Ready-to-apply (in-repo, but not live):**

- `manage.py check_backups` — backup health gate (exit 0/1; see §4).
- `scripts/backup_cron.sh` — backup + validate + external health-check ping.
- `scripts/backup_smoke_test.sh` — disposable end-to-end drill (see §6).
- The **off-box upload is implemented** in `backup_data` and activates the moment
  `BACKUP_OBJECT_STORAGE_BUCKET` / `_ACCESS_KEY` / `_SECRET_KEY` are set — it has
  only ever been exercised against a stubbed client, never a real bucket.
- `render.cron.yaml` — ops-only **Render Blueprint** for a daily Cron Job that runs
  `scripts/backup_cron.sh`. It defines the cron job only (it does **not**
  recreate the existing web service).

Owner actions still required — **follow `docs/OWNER_RENDER_OPS_TUTORIAL.md`
step-by-step** (apply via Render dashboard / Blueprint):

- **A cron job has NO persistent disk and can't read another service's disk.** A
  backup written to a local `P0B_BACKUP_ROOT` on a cron is **ephemeral — wiped
  after the run**. To keep a backup you MUST **upload it to object storage**
  (R2 / S3) after `backup_data`, or run the backup from a **background worker**
  that has a disk. This is the single most important point (see the tutorial Step 2).
  The upload itself is built in (`BACKUP_OBJECT_STORAGE_*`, §2b); what is missing
  is the bucket and its key.
- **Persistent disk** is for the **web service only** (photos): mount `/data`,
  set `MEDIA_ROOT=/data/media` so uploaded photos survive redeploys (D-7).
- **Notification:** create a health check (e.g. Healthchecks.io) and set
  `HEALTHCHECK_PING_URL` (never hard-coded); `backup_cron.sh` pings `<url>` on
  success and `<url>/fail` on failure. A non-zero exit also fires Render's own
  failure notification.
- **Postgres:** production likely uses `DATABASE_URL` → Postgres. Confirm
  `pg_dump`/`pg_restore` exist in the runtime, and that `PGPASSWORD`/`DATABASE_URL`
  are set in the environment (never in the repo).
- **Plan/billing:** cron jobs have **no free tier**; they run on a paid plan.

Do **not** treat the local test restore as completing/validating any scheduled
production backup.

## 9. Before a destructive deploy (the hard rule)

No destructive migration or command runs without a **fresh** backup: migration
`0035_remove_ssc_registration_and_board_result` is irreversible, and
`merge_duplicate_subjects --apply`, `clean_student_groups --apply`, and the purge
endpoints destroy data on purpose. Immediately before running one:

```bash
scripts/backup.sh
```

then confirm the newest `backups/backup-*` folder exists, contains a
`manifest.json`, and a restore of it into a disposable target passes `--verify`.
