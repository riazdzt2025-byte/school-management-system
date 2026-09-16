# Data Safety Status

_Last updated 2026-09-16 (second backup tooling + data-safety session). Status
record for backup / data-loss readiness._
_Companion documents: `docs/BACKUP_RESTORE_GUIDE.md` (operator guide),
`docs/BACKUP_AND_RESTORE.md` (tooling runbook)._

**বাংলা সংক্ষিপ্তসার:** চার ধরনের বিপদ আলাদা করে দেখা হয়েছে — অ্যাপ নষ্ট হওয়া,
ডেটাবেস হারানো, ভুল করে ডেটা মুছে ফেলা, আর ছবি/ডকুমেন্ট হারানো। প্রতিটির জন্য
আলাদা প্রতিকার লেখা আছে, কারণ সব ক্ষেত্রে রিস্টর করা ভুল হবে। একমাত্র লেখার-যোগ্য
ডেটাবেস হলো `DATABASE_URL`-এর ডেটাবেস; ব্যাকআপ শুধু পড়ার-যোগ্য কপি, আর ড্রিলের
ডেটাবেস সাময়িক ও শেষে মুছে ফেলা হয় — তিনটি স্বাধীন "লাইভ" ডেটাবেস বানানো হয়নি
(এখন এটা `manage.py check` নিজেই ধরে দেয়)।

এই সেশনে যাচাই করতে গিয়ে **দুটি আসল বাগ ধরা পড়ে ও ঠিক করা হয়েছে**, দুটোই
রিস্টর-সময়ে নীরবে ডেটা নষ্ট করত:

1. **SQLite রিস্টার পুরনো `-wal`/`-journal` ফাইল মুছত না।** শুধু মূল ফাইল কপি
   করলে পরেরবার ডেটাবেস খোলার সময় SQLite পুরনো journal/WAL রিপ্লে করে — অর্থাৎ
   রিস্টর "সফল" ও `integrity_check` "ok" দেখিয়েও **আসলে পুরনো ডেটাই ফিরত**।
   স্থানীয়ভাবে প্রজনন (reproduce) করা হয়েছে, তারপর ঠিক করা হয়েছে।
2. **`age`-এ এনক্রিপ্ট করা ব্যাকআপ ভুল শাখায় পড়ত।** ম্যানিফেস্ট `age` বললেও
   তখনকার `BACKUP_ENCRYPTION` সেটিং দেখা হতো, তাই সাইফারটেক্সটই প্লেইনটেক্সট
   ধরে কপি হতো — আবারও "সফল" দেখানো এক নীরব বিপর্যয়।

এর সঙ্গে অফ-বক্স কপি এখন **পড়াও যায়**: `fetch_backup` বাকেট থেকে ব্যাকআপ নামিয়ে
manifest দিয়ে যাচাই করে, আর `check_backups --check-remote` নিশ্চিত করে কপিটা সত্যিই
বাকেটে পৌঁছেছে (না পৌঁছালে health-check ফেল করে)। মোক S3 এন্ডপয়েন্ট (moto) ও
স্থানীয় PostgreSQL 18.6 দিয়ে পুরো রাউন্ড ট্রিপ ড্রিল পাস করেছে।
**লাইভ শিডিউল, আসল অফ-বক্স বাকেট, প্রোডাকশন রিস্টর — কিছুই চালু হয়নি**; এগুলো
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
| 2 | **Database loss / corruption** | Disk loss, provider failure, half-applied migration, truncated file | **No** | Restore the newest good backup into the configured DB (§6.2 of the guide; §6.4 if the host is gone too) | Keep retrying the app, or start a second database |
| 3 | **Accidental deletion / overwrite** | Bad bulk action, purge endpoint, wrong `--apply` command, wrong row | Partially — `AuditLog` + the last backup | Restore into a **disposable** copy, take the rows back; or reconstruct from `AuditLog.snapshot` | Full restore without checking what newer data it would destroy |
| 4 | **Media loss** (photos / documents) | Ephemeral container disk (D-7), deleted object, failed upload | Only if media is in a bucket with versioning, or in a backup | Restore `media.tar.gz`, or the bucket's versioned copy | Re-uploading nothing and assuming the DB record is the photo |

A fifth, rarer case sits underneath all of them: **loss of the host itself**. Its
answer is the off-box copy (§4.3 of the guide) plus `fetch_backup`, because the
local `backups/` folder dies with the machine.

**Why the split matters:** cases 1 and 4 are recoverable with *no* database
restore. Case 3 is usually recoverable *without* a full restore. Only case 2
justifies overwriting the live database — and even then a safety backup of the
current state is taken first, so the restore itself is reversible.

Detection today: case 1 is visible immediately (the app is down). Cases 2–4 are
**silent** unless something checks — `manage.py check_backups` is that check for
backups (`--check-remote` extends it to the off-box copy); there is no equivalent
automatic probe for "a photo went missing", which is why bucket versioning is a
prerequisite rather than a nice-to-have.

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
                                │  fetch_backup (download + verify + unpack)
                                ▼
        a local backup-<stamp>/ folder again — read-only, restorable
                                │  restore_backup --yes (explicit, destructive)
                                ▼
                 ┌───────────────────────────────┐
                 │  disposable drill target only │  → deleted when the drill ends
                 └───────────────────────────────┘
```

Rules that follow from it:

1. **One writable database.** `settings.DATABASES` has exactly one entry
   (`default`); no code path opens a second one for writing. Now **enforced by a
   system check** (`students.W015` in `students/checks.py`): add a second alias
   and every `manage.py check` — a build step, a CI step, a deploy — says so.
   Still true by inspection: `grep -rn "DATABASES" --include=*.py` returns only
   `settings.py`, `backup_utils.py`, `restore_backup.py`, `checks.py` and tests.
2. **Backups are artifacts, not databases.** A `backups/backup-*` folder is
   never mounted, opened read-write, or served by the app. The last part is now
   checked too: `students.E013` fails a deploy check if the backup root sits
   inside `MEDIA_ROOT` or `STATIC_ROOT` (a backup reachable over HTTP is a
   full-PII breach), and `students.W014` warns when backups are written inside
   the app directory on a deployment — the folder a container platform wipes.
3. **Drill targets are disposable and deleted.** `scripts/backup_smoke_test.sh`
   creates them under `.restore-drill/` (git-ignored), asserts the resolved
   database path is inside that directory, and removes everything on exit.
4. **No three-writable-database setup.** A "spare live DB kept in sync by hand"
   would diverge within a day and make "which one is true?" unanswerable.
   Redundancy comes from read-only backups instead. The smoke test's guard is the
   enforcement: point it at anything outside the drill directory and it aborts
   with exit 1 before writing anything (re-verified this session — see §5).
5. **Restores target the configured database only.** There is deliberately no
   "restore into database X" switch; changing the target means changing
   `DATABASE_URL`, which is a deliberate act.
6. **The off-box copy is read-only too.** `fetch_backup` downloads and unpacks;
   it never writes to a database. The destructive step stays a separate,
   `--yes`-gated `restore_backup`.

## 3. Engine handling

| Engine | Backup | Restore | Consistency guarantee |
|---|---|---|---|
| SQLite (local default) | `sqlite3` online-backup API → `db.sqlite3` | replace the file **and delete stale `-wal`/`-shm`/`-journal`**, then SHA-verify the copy | Point-in-time snapshot, safe while the app writes. **Drill passed locally** |
| Postgres (`DATABASE_URL`) | `pg_dump --format=custom --no-owner --no-privileges` → `db.dump` | `pg_restore --clean --if-exists` | Server-side consistent dump; credentials via `PG*` env, never argv. **Drill passed locally against PostgreSQL 18.6** (and 16.2 in an earlier session; CI uses `postgres:16`) |
| Anything else | **Refused** (`CommandError`) | **Refused** | No silent no-op backup |

**Fixed while verifying this session (restore silently doing nothing):**
`_restore_sqlite` copied the snapshot over the main database file and left the
old `-wal`/`-shm`/`-journal` beside it. SQLite replays those on the next open, so
the application saw the *pre-restore* rows while `PRAGMA integrity_check` said
`ok` and `restore_backup --verify` (which re-hashes the artifact, not the live
file) said nothing. Reproduced in a scratch script and kept as an executable
regression test (`test_a_naive_copy_replays_the_stale_wal_and_restores_nothing`).
Restores now go through `backup_utils.replace_sqlite_database()`: close
connections → delete sidecars → copy → re-read and compare SHA-256 with the
snapshot → `chmod 0600`. Removed sidecars are named in the command output, which
also tells the operator the previous database died mid-write.

**Fixed earlier the same day (still relevant):** `pg_dump` was pointed at
`localhost` when a `DATABASE_URL` used a unix socket. The `PG*` environment now
comes from `connections['default'].get_connection_params()` — exactly what Django
connects with — and an empty value is omitted rather than invented. The drills
above run over a unix socket, so this path is exercised, not just unit-tested.

**Fixed this session (encrypted-backup path):** `decrypt_artifact()` consulted
`BACKUP_ENCRYPTION` instead of its own `mode` argument when deciding whether to
use `age`. A backup whose manifest says `age:x25519`, restored on a host where
that variable is unset or says `openssl`, fell through to the plaintext branch
and copied the **ciphertext** as if it were the database. The manifest is now the
only source of truth (as it already was for `openssl`), and the missing-identity
error names `BACKUP_AGE_IDENTITY_FILE`.

**Unknown:** which engine production actually runs. `settings.py` defaults to
SQLite and honours `DATABASE_URL` via `dj-database-url`; the live value has not
been read in this session. Confirming it is prerequisite P-1 below, together with
confirming that `pg_dump`/`pg_restore` exist in the production runtime image.

## 4. Retention, encryption, access control, failure reporting

| Concern | Mechanism | Default | Status |
|---|---|---|---|
| Retention (local) | `backup_data --keep N` prunes oldest `backup-*` folders | 7 | **Implemented, tested** |
| Retention (off-box) | `BACKUP_OBJECT_STORAGE_KEEP` prunes remote bundles | 30 | **Implemented, unit-tested, and drill-verified against a mock S3 endpoint** (2 uploads beyond the limit left exactly 2, newest retained) |
| Encryption at rest | `BACKUP_ENCRYPTION=openssl\|age`; passphrase via file or env | `off` | **Implemented, `openssl` round-trip tested and drilled**; `age` path implemented and dispatch-tested, but the `age` binary is not installed here |
| Access control (files) | Backup folder `0700`, artifacts + manifest `0600` — including folders unpacked by `fetch_backup` | always on | **Implemented, tested** |
| Access control (policy) | `check_backups` fails on group/other-readable files, and on a plaintext backup when encryption is required | always on | **Implemented, tested** |
| Access control (bucket) | Server-side encryption `AES256` on upload; separate scoped key recommended | on upload | **Implemented; exercised against a mock endpoint, not a real bucket** |
| Access control (paths) | `students.E013` (backup root inside a served tree), `students.W014` (backup root wiped by a deploy), `students.W015` (more than one database) | always registered | **Implemented, tested** |
| Credentials in artifacts | Manifest records engine, names, SHA-256, redacted DB label only; `credentials_included: false` | always | **Implemented, tested** (a DB password in settings does not reach the manifest) |
| Failure reporting | Non-zero exit from `backup_data` / `check_backups` / `fetch_backup`; failed backup folder deleted; failed fetch deleted; `scripts/backup_cron.sh` pings `HEALTHCHECK_PING_URL` and `<url>/fail` | always | **Implemented; health-check URL not set (needs an owner account)** |
| Off-box failure reporting | `check_backups --check-remote` (auto in `backup_cron.sh` once a bucket is set) fails when the newest backup never reached the bucket | with a bucket | **Implemented, tested, drilled both ways** (present → pass, wrong prefix → fail) |
| Freshness detection | `check_backups --max-age-hours` (48) catches a scheduler that silently stopped | 48 h | **Implemented, tested** |
| Integrity | SHA-256 of on-disk artifacts + plaintext digests for encrypted ones; verified on restore (`--verify`), by `check_backups`, and by `fetch_backup` against the bundle's own manifest | always | **Implemented, tested** |
| Restore safety | `--yes` required; current row counts printed first; SQLite sidecars removed; restored file SHA-compared with the snapshot | always | **Implemented, tested** |

## 5. Verified locally (with the evidence)

Environment: Python 3.11.2, **Django 5.2.17**. The project pins Django 6.1,
which requires Python ≥ 3.12; this sandbox only has 3.11 (and cannot download a
3.12 build — the release-asset host is unreachable from here), so the suite was
run against the newest Django 3.11 supports. `requirements.txt` was **not**
changed. CI (`.github/workflows/tests.yml`) runs Python 3.12 + Django 6.1 on both
SQLite and Postgres 16, and now also runs the off-box drill against moto.

Supporting services used for the drills, both disposable and both outside the
repository: **PostgreSQL 18.6** (an embedded build from the `embedded-postgres`
PyPI wheel, cluster under `/tmp/pgdrill`, unix socket, dropped databases on exit)
and **moto 5.2.3** (`moto_server` on `127.0.0.1:5055`, a real S3-speaking HTTP
endpoint). Neither is a project dependency; `requirements.txt` still lists only
what the app needs.

| Check | Command | Result |
|---|---|---|
| Full suite | `.venv/bin/python manage.py test students` | **Ran 550 tests — OK** (510 before this session; +40 new) |
| Backup tooling tests | `.venv/bin/python manage.py test students.test_backup_tooling` | **Ran 112 tests — OK** (72 before) |
| System check | `.venv/bin/python manage.py check` | No issues (new checks silent on the default dev config) |
| Deploy check (dev defaults) | `.venv/bin/python manage.py check --deploy` | The same 6 pre-existing Django security warnings as before; the new checks stay silent (they are deploy-only and `DEBUG=True` short-circuits them) |
| Deploy check (production-like) | `DEBUG=False SECRET_KEY=<random> manage.py check --deploy` | `students.W010` (media in the app tree, pre-existing) **and the new `students.W014`** — backups default to `BASE_DIR/backups`, which a container platform wipes. Adding `P0B_BACKUP_ROOT=/data/backups USE_S3=True …` clears both; only 2 optional HSTS warnings remain. No `students.E013` in any configuration tried |
| Migrations | `.venv/bin/python manage.py makemigrations --check` | No changes detected (this session added no models) |
| Smoke test (SQLite) | `scripts/backup_smoke_test.sh` | **steps passed: 15, failed: 0 — RESULT: PASSED** |
| Smoke test (Postgres 18.6, unix socket) | `scripts/backup_smoke_test.sh --postgres "postgres://postgres@/postgres?host=/tmp/pgdrill&port=55432"` | **steps passed: 16, failed: 0 — RESULT: PASSED**; the drill created its own two databases and dropped them on exit |
| Smoke test (SQLite + off-box) | `scripts/backup_smoke_test.sh --s3-endpoint http://127.0.0.1:5055` | **steps passed: 28, failed: 0 — RESULT: PASSED**; drill bucket created and deleted again |
| Smoke test (Postgres + off-box) | `… --postgres … --s3-endpoint http://127.0.0.1:5055` | **steps passed: 29, failed: 0 — RESULT: PASSED** |
| Smoke test guard | Same script with a database target that is not the drill's own | Aborts with exit 1 before writing anything (`could not create database …` / `target database … is NOT …— refusing to continue`); no file was created outside `.restore-drill/` |
| CI on the pinned stack | GitHub Actions runs `35139041077` (push) and `35139099756` (PR #26) — Python 3.12 + Django 6.1 | Both **success**, on every job. Step conclusions read individually: `Django system check`, `Migrations in sync`, `Run test suite (sqlite)`, `Run test suite (postgres)`, `Ensure PostgreSQL client tools`, `Backup / restore smoke test (sqlite)`, `Backup / restore smoke test (postgres)`, `Off-box backup drill (sqlite)`, `Off-box backup drill (postgres)`, and the Node job. The raw step logs are not reachable from this sandbox, so the counts in the rows above are the local ones |

What the drills actually proved, on disposable data:

* a real student row + a real PNG written through `Student.photo` were backed up;
* `check_backups` reported the result healthy;
* a restore into a **separate** disposable target passed `--verify`
  (`migrate --check`, record counts, every file reference resolving);
* the restored photo was **byte-identical** (`sha256sum` match);
* the same cycle with `BACKUP_ENCRYPTION=openssl` produced only `*.enc`
  artifacts, left no plaintext on disk, and restored to identical bytes;
* a **wrong passphrase was rejected** rather than producing a fake "verified"
  restore;
* **off-box:** the bundle was uploaded to the mock bucket, found by
  `check_backups --check-remote` (and reported missing when the prefix was
  wrong), brought back by `fetch_backup --latest`, verified against its own
  manifest, and **restored from the fetched copy** into a fresh disposable
  target — same record count, byte-identical photo;
* **off-box retention:** two further backups left exactly
  `BACKUP_OBJECT_STORAGE_KEEP=2` bundles in the bucket, and the newest local
  backup was still among them.

New unit coverage added this session (40 tests): the `age` dispatch regression
(mode from the manifest beats the environment, for both `age` and `openssl`, and
the identity path — never the secret — is what reaches argv); the SQLite sidecar
regression (stale WAL, stale rollback journal, only the *target's* sidecars
touched, `0600` result, missing snapshot refused, the command-level restore
clearing them, and an executable record of the naïve-copy hazard); the off-box
read path (`verify_remote_copy` present/missing/empty, credentials errors not
swallowed as "missing", `check_backups --check-remote` pass/fail/unconfigured,
the bucket not contacted without the flag); `download_remote_backup`
(round-trip, private modes, corrupt bundle refused **and removed**, bundle
without a manifest refused, no clobbering without `--force`, non-bundle keys
refused); `fetch_backup` (`--list`, `--latest`, no bucket, empty bucket); and the
three new system checks.

Also hardened this session: the drill now **unsets every inherited `BACKUP_*` /
`P0B_BACKUP_ROOT` variable** and passes `--no-upload` on its local steps. Before
that, an operator whose `.env` configured a real bucket would have had the
drill's throwaway bundles uploaded to it — and the drill's own
`BACKUP_OBJECT_STORAGE_KEEP` could have pruned **real** backups. No production
configuration was touched while finding this; it was read off the code path.

## 6. Unknown / unverified — do not assume these work yet

| Item | Why it is unverified | What would verify it |
|---|---|---|
| **A real off-box bucket** | The whole upload → gate → fetch → restore cycle is drill-verified against **moto** (a mock that speaks real S3) and unit-tested with a stub; no provider bucket (R2/B2/S3/MinIO-in-prod) has been touched | P-3: create the bucket, run one `backup_data`, then `fetch_backup --latest` and a disposable restore |
| **Postgres on the production server** | Drilled locally (18.6 over a unix socket) and in CI (`postgres:16`), but the production server's version, host and credentials have still not been touched | P-1: confirm the production engine and that the runtime image ships `pg_dump`/`pg_restore` |
| **`age` encryption end to end** | The `age` binary is not installed here; the dispatch, argv handling and error messages are unit-tested, and the openssl round trip is drilled | Install `age`, repeat the encrypted round trip (`BACKUP_ENCRYPTION=age`) |
| **Production database engine / size** | `DATABASE_URL` never read in this session | Owner: `manage.py dbshell` or the Render dashboard |
| **Live scheduled backup** | No scheduler enabled (rule: approval required) | Apply `render.cron.yaml`, then check a real backup folder appears daily |
| **Health-check alerting** | `HEALTHCHECK_PING_URL` unset (needs an owner account) | Create the check, set the variable, confirm a failure ping arrives (a `--check-remote` failure is the easiest one to trigger on purpose) |
| **Production restore** | Never attempted against live data — and must not be | An approved maintenance window, with a copy of the real database |
| **Media durability in production** | Whether `USE_S3` is on, and whether the bucket has versioning, is unknown here | Owner: confirm bucket + versioning (or a persistent disk with `MEDIA_ROOT`) |
| **SQLite in production** | Only relevant if production really runs SQLite; the sidecar fix matters for any WAL-mode database, and production's journal mode has not been read | `sqlite3 db.sqlite3 'PRAGMA journal_mode;'` on the host, if SQLite is the engine |

**A passing local smoke test is not a live backup.** No production backup exists
as a result of this session.

## 7. Deployment prerequisites (owner actions, in order)

Each step needs owner access; several need a paid plan. Nothing here has been
started.

| # | Action | Blocks | Cost / access |
|---|---|---|---|
| P-1 | Confirm the production database engine and that `pg_dump`/`pg_restore` exist in the runtime image (the tooling itself is drill-verified) | Everything else | Dashboard / shell access |
| P-2 | Decide `P0B_BACKUP_ROOT` on a **persistent** location (a cron job's disk is wiped). `manage.py check --deploy` now flags a backup root that is web-served (E013) or ephemeral (W014) | Scheduled backup | Paid disk or a worker with a disk |
| P-3 | Create the backup bucket + a **scoped** key; set `BACKUP_OBJECT_STORAGE_*`; then run one `backup_data` **and** `fetch_backup --latest` + a disposable restore, so the recovery path is proven with the real credentials | Off-box copy | Paid/allocated storage |
| P-4 | Enable **versioning** on the media bucket (or mount a persistent disk for `MEDIA_ROOT`) | Media-loss recovery | Free–cheap, dashboard |
| P-5 | Generate a backup passphrase, store it in the owner's password manager (not on the server, not in the repo); set `BACKUP_ENCRYPTION` + `BACKUP_PASSPHRASE_FILE` | Encryption | Free |
| P-6 | Create a health check; set `HEALTHCHECK_PING_URL`. With a bucket configured, `backup_cron.sh` now gates on `check_backups --check-remote`, so a dead upload pages too | Failure alerting | Free tier usually enough |
| P-7 | Apply `render.cron.yaml` (daily 02:00 UTC) — **note: Render Cron Jobs have no free tier** | Live scheduling | ≥ paid plan |
| P-8 | Run `scripts/backup_smoke_test.sh` on the production host (add `--s3-endpoint` only against a mock), then a supervised restore of a real backup into a **disposable** target | Confidence before any destructive deploy | Approved window |
| P-9 | Re-run `scripts/backup_smoke_test.sh` after any change to the backup tooling, and monthly as a drill; re-run `fetch_backup --list` monthly so the off-box copy is known-readable | Ongoing | Free |

Until P-1…P-7 are done, the honest status is: **the tooling is ready and tested;
live backups are not running.**

## 8. Explicitly out of scope for this session

* No production restore, no destructive migration, no `--apply` cleanup command.
* No paid storage created, no scheduler enabled, no cron applied. The only
  storage touched was a mock S3 endpoint on `127.0.0.1`, created and deleted by
  the drill itself.
* No secrets, passphrases, connection strings or real backup files committed or
  printed. Test passphrases are literals used only on temp files; the drill's
  S3 credentials are literals for a mock bucket on localhost; `.gitignore`
  already excludes `backups/`, `.restore-drill/`, `media/` and `.env`.
* **SSC Registration / Summary was not restored.** Migration
  `0035_remove_ssc_registration_and_board_result` and the related removals stand;
  nothing in this session re-adds those models, tables or UI. Note the
  consequence for backups: a backup taken **before** 0035 cannot be restored into
  the current code without a schema mismatch, which `migrate --check` in
  `restore_backup --verify` will report.
* No merge, and no remote operations on a closed session; the branch
  `arena/01a0ab72-school-management-system` holds this session's work pending
  review (the previous session's branch, `arena/01a0ab02-…`, was merged as PR
  #25).
