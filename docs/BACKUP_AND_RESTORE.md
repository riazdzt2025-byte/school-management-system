# Backup & Restore Runbook

_Last updated 2026-09-09 (P0-8 backup session; + ops readiness: `check_backups`, `backup_cron.sh`, `render.cron.yaml`)._

This runbook describes how to back up and restore the School Management System
across both supported database engines (SQLite, the local default, and
Postgres, used via `DATABASE_URL` in production) and the uploaded-file tree
(student photos) under `MEDIA_ROOT`.

The tooling is two Django management commands plus thin cron-friendly wrappers:

| Command | Purpose |
|---|---|
| `manage.py backup_data` | Create a consistent DB + media snapshot, write a manifest, prune old backups. |
| `manage.py restore_backup` | Restore a backup folder into the configured DB + media dir (destructive, needs `--yes`). |
| `manage.py check_backups` | Backup health gate: verify newest backup (manifest, DB SHA, freshness, retention); **exit 0 = healthy, non-zero = problem** (for alerting). |
| `scripts/backup.sh` | Wrapper around `backup_data` for cron; returns a usable exit code. |
| `scripts/restore.sh` | Wrapper around `restore_backup`. |
| `scripts/backup_cron.sh` | Backup + validate + external health-check ping; the recommended cron entrypoint. |

> **Security rule:** the backup artifact and manifest **never contain
> credentials**. For Postgres the dump is produced by `pg_dump`/`pg_restore`
> driven through the `PG*` environment variables (not argv) so no password is
> written to a log, `ps`, or a file.

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
(good against a truncated/corrupt file), freshness (`--max-age-hours`, default
48 — a scheduled backup that silently stopped producing new folders becomes stale),
and retention sanity (more folders than `--keep` means pruning is not running).
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

### Postgres note

`pg_restore --clean --if-exists` is used, so the target database must exist and
be reachable via the `PG*` env. The destination is the **configured** database
(e.g. `DATABASE_URL`); there is no "restore to a different DB" switch — point
`DATABASE_URL` at the target if you want a different one.

## 6. Restore drill (disposable only)

This is a dry run against **throwaway** storage. It never touches the real DB or
media. It proves the backup can be restored and that the app boots and data/files
are intact. Run it any time before a destructive deploy.

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

The tooling here is ready to use, and the **ops config is now prepared**; only the
**live scheduling and off-box storage are not wired**, because they need
production-level access and decisions this session should not assume (rule 7).

**Ready-to-apply (in-repo, but not live):**

- `manage.py check_backups` — backup health gate (exit 0/1; see §4).
- `scripts/backup_cron.sh` — backup + validate + external health-check ping.
- `render.cron.yaml` — ops-only **Render Blueprint** for a daily Cron Job that runs
  `scripts/backup_cron.sh`. It defines the cron job only (it does **not**
  recreate the existing web service).

Owner actions still required (apply via Render dashboard / Blueprint):

- **Cron job filesystem is EPHEMERAL.** A backup written to a local path is wiped
  after each run, so `P0B_BACKUP_ROOT` **must** point at a persistent location:
  a **Render persistent disk**, or **upload after backup to object storage**
  (R2 / S3 / a server you control). Render does not attach a running service's disk
  to a cron job, so a disk-only approach needs a disk-mounted service plus an
  off-box copy. This is an **owner decision**.
- **Persistent disk:** the default Render filesystem is ephemeral. A backup
  written to it is lost on redeploy. Store backups on a persistent disk or
  upload them to object storage (S3/R2/Render Disks) — an **owner decision**.
  The same disk should host `MEDIA_ROOT` (set `MEDIA_ROOT=/data/media`) so
  uploaded student photos also survive redeploys (D-7).
- **Notification:** create a health check (e.g. Healthchecks.io) and set
  `HEALTHCHECK_PING_URL` (never hard-coded); `backup_cron.sh` pings `<url>` on
  success and `<url>/fail` on failure.
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
