# Data Safety Status

_Last updated 2026-09-16. Status record for backup / data-loss readiness._
_Companion documents: `docs/BACKUP_RESTORE_GUIDE.md` (operator guide),
`docs/BACKUP_AND_RESTORE.md` (tooling runbook)._

**বাংলা সংক্ষিপ্তসার:** চার ধরনের বিপদ আলাদা করে দেখা হয়েছে — অ্যাপ নষ্ট হওয়া,
ডেটাবেস হারানো, ভুল করে ডেটা মুছে ফেলা, আর ছবি/ডকুমেন্ট হারানো। প্রতিটির জন্য
আলাদা প্রতিকার লেখা আছে, কারণ সব ক্ষেত্রে রিস্টর করা ভুল হবে। একমাত্র লেখার-যোগ্য
ডেটাবেস হলো `DATABASE_URL`-এর ডেটাবেস; ব্যাকআপ শুধু পড়ার-যোগ্য কপি, আর ড্রিলের
ডেটাবেস সাময়িক ও শেষে মুছে ফেলা হয় — তিনটি স্বাধীন "লাইভ" ডেটাবেস বানানো হয়নি।
টুলিং স্থানীয়ভাবে পরীক্ষা করা: ৫১০টি টেস্ট পাস, স্মোক টেস্ট SQLite-এ ১৫/১৫ এবং আসল PostgreSQL 16.2-এ ১৬/১৬ ধাপ পাস। যাচাই করতে গিয়ে একটা আসল বাগ ধরা পড়ে ও ঠিক করা হয়েছে: `pg_dump` ভুল করে `localhost`-এ যেত যখন `DATABASE_URL` unix socket ব্যবহার করে।
**লাইভ শিডিউল, অফ-বক্স বাকেট, প্রোডাকশন রিস্টর — কিছুই চালু হয়নি**; এগুলো
মালিকের অনুমোদন ও পেইড রিসোর্স ছাড়া সম্ভব নয়। নিচে verified / unknown তালিকা আছে।

**Scope of this session:** local-tested tooling, tests and documentation only.
Nothing was enabled in production, no scheduler was wired, no paid storage was
created, no production restore was attempted, and the retired SSC
Registration/Summary features were **not** brought back.

---

## 1. Four different failures, four different responses

Treating these as one problem is what turns a small incident into data loss.

| # | Failure | Typical cause | Does the data survive? | Correct response | **Do NOT** |
|---|---|---|---|---|---|
| 1 | **App failure** | Bad deploy, unhandled exception, 500s, container OOM | **Yes** — the database is untouched | Roll back to the previous build/deploy | Restore a backup (it rewinds real records for no reason) |
| 2 | **Database loss / corruption** | Disk loss, provider failure, half-applied migration, truncated file | **No** | Restore the newest good backup into the configured DB (§6.2 of the guide) | Keep retrying the app, or start a second database |
| 3 | **Accidental deletion / overwrite** | Bad bulk action, purge endpoint, wrong `--apply` command, wrong row | Partially — `AuditLog` + the last backup | Restore into a **disposable** copy, take the rows back; or reconstruct from `AuditLog.snapshot` | Full restore without checking what newer data it would destroy |
| 4 | **Media loss** (photos / documents) | Ephemeral container disk (D-7), deleted object, failed upload | Only if media is in a bucket with versioning, or in a backup | Restore `media.tar.gz`, or the bucket's versioned copy | Re-uploading nothing and assuming the DB record is the photo |

**Why the split matters:** cases 1 and 4 are recoverable with *no* database
restore. Case 3 is usually recoverable *without* a full restore. Only case 2
justifies overwriting the live database — and even then a safety backup of the
current state is taken first, so the restore itself is reversible.

Detection today: case 1 is visible immediately (the app is down). Cases 2–4 are
**silent** unless something checks — `manage.py check_backups` is that check for
backups; there is no equivalent automatic probe for "a photo went missing", which
is why bucket versioning is a prerequisite rather than a nice-to-have.

## 2. Authoritative database + independent backups (the plan)

```
                 ┌───────────────────────────────┐
   writes ─────▶ │  ONE authoritative database   │  ← DATABASE_URL (prod)
                 │  (the only writable one)      │  ← db.sqlite3 (local dev)
                 └──────────────┬────────────────┘
                                │ backup_data (read-only snapshot)
                                ▼
        backups/backup-<stamp>/  db + media.tar.gz + manifest.json
                                │ (optional) BACKUP_OBJECT_STORAGE_*
                                ▼
                   off-box bucket, server-side encrypted
                                │
                                ▼  restore_backup --yes (explicit, destructive)
                 ┌───────────────────────────────┐
                 │  disposable drill target only │  → deleted when the drill ends
                 └───────────────────────────────┘
```

Rules that follow from it:

1. **One writable database.** `settings.DATABASES` has exactly one entry
   (`default`); no code path opens a second one for writing. Verified by
   inspection: `grep -rn "DATABASES" --include=*.py` returns only
   `settings.py`, `backup_utils.py`, `restore_backup.py` and a test.
2. **Backups are artifacts, not databases.** A `backups/backup-*` folder is
   never mounted, opened read-write, or served by the app.
3. **Drill targets are disposable and deleted.** `scripts/backup_smoke_test.sh`
   creates them under `.restore-drill/` (git-ignored), asserts the resolved
   database path is inside that directory, and removes everything on exit.
4. **No three-writable-database setup.** A "spare live DB kept in sync by hand"
   would diverge within a day and make "which one is true?" unanswerable.
   Redundancy comes from read-only backups instead. The smoke test's guard is the
   enforcement: point it at anything outside the drill directory and it aborts
   with exit 1 before writing anything (verified — see §5).
5. **Restores target the configured database only.** There is deliberately no
   "restore into database X" switch; changing the target means changing
   `DATABASE_URL`, which is a deliberate act.

## 3. Engine handling

| Engine | Backup | Restore | Consistency guarantee |
|---|---|---|---|
| SQLite (local default) | `sqlite3` online-backup API → `db.sqlite3` | file copy over the target | Point-in-time snapshot, safe while the app writes. **Drill passed locally** |
| Postgres (`DATABASE_URL`) | `pg_dump --format=custom --no-owner --no-privileges` → `db.dump` | `pg_restore --clean --if-exists` | Server-side consistent dump; credentials via `PG*` env, never argv. **Drill passed locally against PostgreSQL 16.2** |
| Anything else | **Refused** (`CommandError`) | **Refused** | No silent no-op backup |

**Fixed while verifying the Postgres path:** `pg_dump` was being pointed at
``localhost``. `_postgres_params` read `settings.DATABASES['HOST']` and defaulted
it to `localhost`, but a `DATABASE_URL` like `postgres://user@/dbname?host=/var/run/postgresql`
leaves `HOST` empty and carries the socket directory in `OPTIONS` — so the dump
would have targeted a *different server* from the one the app writes to. The
`PG*` environment is now derived from `connections['default'].get_connection_params()`
(exactly what Django connects with), and an empty value is omitted rather than
invented. Covered by unit tests and by the drill below.

**Unknown:** which engine production actually runs. `settings.py` defaults to
SQLite and honours `DATABASE_URL` via `dj-database-url`; the live value has not
been read in this session. Confirming it is prerequisite P-1 below, together with
confirming that `pg_dump`/`pg_restore` exist in the production runtime image.

## 4. Retention, encryption, access control, failure reporting

| Concern | Mechanism | Default | Status |
|---|---|---|---|
| Retention (local) | `backup_data --keep N` prunes oldest `backup-*` folders | 7 | **Implemented, tested** |
| Retention (off-box) | `BACKUP_OBJECT_STORAGE_KEEP` prunes remote bundles | 30 | **Implemented, unit-tested with a stubbed client; not run against a real bucket** |
| Encryption at rest | `BACKUP_ENCRYPTION=openssl\|age`; passphrase via file or env | `off` | **Implemented, round-trip tested** (openssl); `age` path implemented but not exercised (binary absent) |
| Access control (files) | Backup folder `0700`, artifacts + manifest `0600` | always on | **Implemented, tested** |
| Access control (policy) | `check_backups` fails on group/other-readable files, and on a plaintext backup when encryption is required | always on | **Implemented, tested** |
| Access control (bucket) | Server-side encryption `AES256` on upload; separate scoped key recommended | on upload | **Implemented; not exercised against a real bucket** |
| Credentials in artifacts | Manifest records engine, names, SHA-256, redacted DB label only; `credentials_included: false` | always | **Implemented, tested** (a DB password in settings does not reach the manifest) |
| Failure reporting | Non-zero exit from `backup_data` / `check_backups`; failed backup folder deleted; `scripts/backup_cron.sh` pings `HEALTHCHECK_PING_URL` and `<url>/fail` | always | **Implemented; health-check URL not set (needs an owner account)** |
| Freshness detection | `check_backups --max-age-hours` (48) catches a scheduler that silently stopped | 48 h | **Implemented, tested** |
| Integrity | SHA-256 of on-disk artifacts + plaintext digests for encrypted ones; verified on restore (`--verify`) and by `check_backups` | always | **Implemented, tested** |

## 5. Verified locally (with the evidence)

Environment: Python 3.11.2, **Django 5.2.17**. The project pins Django 6.1,
which requires Python ≥ 3.12; this sandbox only has 3.11, so the suite was run
against the newest Django that 3.11 supports. `requirements.txt` was **not**
changed. CI (`.github/workflows/tests.yml`) runs Python 3.12 + Django 6.1 on both
SQLite and Postgres 16 — and it ran green on this branch, so the tooling is
proven on the pinned versions as well (see the CI row below).

| Check | Command | Result |
|---|---|---|
| Full suite | `.venv/bin/python manage.py test students` | **Ran 510 tests — OK** (452 before this session; +58 new) |
| Backup tooling tests | `.venv/bin/python manage.py test students.test_backup_tooling` | **Ran 72 tests — OK** (14 before) |
| System check | `.venv/bin/python manage.py check` | No issues |
| Smoke test (SQLite) | `scripts/backup_smoke_test.sh` | **steps passed: 15, failed: 0 — RESULT: PASSED** |
| Smoke test (Postgres) | `scripts/backup_smoke_test.sh --postgres postgres://postgres@/postgres?host=/tmp/pgdata` | **steps passed: 16, failed: 0 — RESULT: PASSED** against PostgreSQL 16.2; the drill created its own two databases and dropped them on exit (verified: only `postgres`, `template0`, `template1` remained) |
| Smoke test guard | Same script with `DATABASE_URL` pointed outside the drill dir | Aborts: `target database ... is NOT inside ... — refusing to continue`, exit 1, **no file created outside the drill** |
| CI on the pinned stack | GitHub Actions run `35128930479` (Python 3.12 + Django 6.1) | All jobs **success**, step by step: `Run test suite (sqlite)`, `Run test suite (postgres)`, `Ensure PostgreSQL client tools`, `Backup / restore smoke test (sqlite)`, `Backup / restore smoke test (postgres)`. Read from the run's step conclusions — the raw step logs were not reachable from this sandbox |

What the smoke test actually proved, on disposable data:

* a real student row + a real PNG written through `Student.photo` were backed up;
* `check_backups` reported the result healthy;
* a restore into a **separate** disposable SQLite file passed `--verify`
  (`migrate --check`, record counts, every file reference resolving);
* the restored photo was **byte-identical** (`sha256sum` match);
* the same cycle with `BACKUP_ENCRYPTION=openssl` produced only `*.enc` artifacts,
  left no plaintext on disk, and restored to identical bytes;
* a **wrong passphrase was rejected** rather than producing a fake "verified"
  restore.

New unit coverage added this session (58 tests): encryption round-trip, plaintext
removal, `0600`/`0700` hardening, passphrase-file handling, unknown-scheme and
missing-tool rejection, `decrypted_backup` for both manifest shapes, manifest
fields with no passphrase leak, off-box config validation, upload packing +
server-side encryption + remote pruning (stubbed S3 client), an end-to-end
`backup_data` against a disposable SQLite file, "failed backup leaves no folder",
the new `check_backups` gates (media SHA, encryption policy, file modes), the
engine-handling rules (sqlite/postgres detection, unsupported engine refused,
`pg_dump` missing), and the `PG*` mapping regression above (socket directory in
`OPTIONS`, blank host never becoming `localhost`, sslmode, no empty password,
client-side kwargs not exported, and a credential-free redacted label).

## 6. Unknown / unverified — do not assume these work yet

| Item | Why it is unverified | What would verify it |
|---|---|---|
| **Postgres on the production server** | The drill passes locally (PostgreSQL 16.2 over a unix socket) and in CI (the `postgres:16` service), but the production server's version, host and credentials have still not been touched | P-1: confirm the production engine and that the runtime image ships `pg_dump`/`pg_restore` |
| **`age` encryption** | The `age` binary is not installed here | Install `age`, repeat the encrypted round-trip |
| **Real off-box upload** | No bucket, no credentials — deliberately | One manual `backup_data` with `BACKUP_OBJECT_STORAGE_*` set, then download the object and restore from it |
| **Production database engine / size** | `DATABASE_URL` never read in this session | Owner: `manage.py dbshell` or the Render dashboard |
| **Live scheduled backup** | No scheduler enabled (rule: approval required) | Apply `render.cron.yaml`, then check a real backup folder appears daily |
| **Health-check alerting** | `HEALTHCHECK_PING_URL` unset (needs an owner account) | Create the check, set the variable, confirm a failure ping arrives |
| **Production restore** | Never attempted against live data — and must not be | An approved maintenance window, with a copy of the real database |
| **Media durability in production** | Whether `USE_S3` is on, and whether the bucket has versioning, is unknown here | Owner: confirm bucket + versioning (or a persistent disk with `MEDIA_ROOT`) |

**A passing local smoke test is not a live backup.** No production backup exists
as a result of this session.

## 7. Deployment prerequisites (owner actions, in order)

Each step needs owner access; several need a paid plan. Nothing here has been
started.

| # | Action | Blocks | Cost / access |
|---|---|---|---|
| P-1 | Confirm the production database engine and that `pg_dump`/`pg_restore` exist in the runtime image (the tooling itself is drill-verified) | Everything else | Dashboard / shell access |
| P-2 | Decide `P0B_BACKUP_ROOT` on a **persistent** location (a cron job's disk is wiped) | Scheduled backup | Paid disk or a worker with a disk |
| P-3 | Create the backup bucket + a **scoped** key; set `BACKUP_OBJECT_STORAGE_*` | Off-box copy | Paid/allocated storage |
| P-4 | Enable **versioning** on the media bucket (or mount a persistent disk for `MEDIA_ROOT`) | Media-loss recovery | Free–cheap, dashboard |
| P-5 | Generate a backup passphrase, store it in the owner's password manager (not on the server, not in the repo); set `BACKUP_ENCRYPTION` + `BACKUP_PASSPHRASE_FILE` | Encryption | Free |
| P-6 | Create a health check; set `HEALTHCHECK_PING_URL` | Failure alerting | Free tier usually enough |
| P-7 | Apply `render.cron.yaml` (daily 02:00 UTC) — **note: Render Cron Jobs have no free tier** | Live scheduling | ≥ paid plan |
| P-8 | Run `scripts/backup_smoke_test.sh` on the production host, then a supervised restore of a real backup into a **disposable** target | Confidence before any destructive deploy | Approved window |
| P-9 | Re-run `scripts/backup_smoke_test.sh` after any change to the backup tooling, and monthly as a drill | Ongoing | Free |

Until P-1…P-7 are done, the honest status is: **the tooling is ready and tested;
live backups are not running.**

## 8. Explicitly out of scope for this session

* No production restore, no destructive migration, no `--apply` cleanup command.
* No paid storage created, no scheduler enabled, no cron applied.
* No secrets, passphrases, connection strings or real backup files committed or
  printed. Test passphrases are literals used only on temp files; `.gitignore`
  already excludes `backups/`, `.restore-drill/`, `media/` and `.env`.
* **SSC Registration / Summary was not restored.** Migration
  `0035_remove_ssc_registration_and_board_result` and the related removals stand;
  nothing in this session re-adds those models, tables or UI. Note the
  consequence for backups: a backup taken **before** 0035 cannot be restored into
  the current code without a schema mismatch, which `migrate --check` in
  `restore_backup --verify` will report.
* No merge, and no remote operations on a closed session; the branch
  `arena/01a0ab02-school-management-system` holds the work pending review.
