# Production Configuration Verification Checklist (P0-7)

_Final checks to run on the live Render service before/at release. Each item is
either a one-time application-side check (command) or an owner/Render-dashboard
action. Run the commands from the deployed shell/session if you have it; the
dashboard items need Render access._

**Legend:** ✅ command we can run · 🔧 Render dashboard / owner action · ⚠️ owner decision

## 1. Application config

| Check | How | Status |
|---|---|---|
| System check passes | `python manage.py check` | ✅ 0 issues |
| No missing migrations | `python manage.py makemigrations --check` | ✅ clean |
| `SECRET_KEY` is a long random value (not default) | Render env `SECRET_KEY` | 🔧 |
| `DEBUG=False` | Render env `DEBUG=False` | 🔧 |
| `ALLOWED_HOSTS` includes the Render host | env, e.g. `school-management-system-27mn.onrender.com` | 🔧 |
| `CSRF_TRUSTED_ORIGINS` includes the https origin | env | 🔧 |
| `TRUST_FORWARDED_PROTO=True` (behind Render proxy) | env — otherwise login POSTs 403 | 🔧 |
| `USE_X_FORWARDED_HOST=True` | env | 🔧 |

## 2. Database

| Check | How | Status |
|---|---|---|
| Engine confirmed (SQLite vs Postgres) | `python manage.py shell` → `databases['default']['ENGINE']` | ⚠️ expected Postgres |
| `DATABASE_URL` set (password not in repo) | Render env | 🔧 |
| `pg_dump`/`pg_restore` exist in runtime (for Postgres backup) | `which pg_dump pg_restore` | 🔧 |
| Battery of conditional unique constraints | CI Postgres job (`.github/workflows/tests.yml`) | ✅ on PR |
| Fresh backup taken | `python manage.py backup_data` | ✅ before destructive ops |

## 3. Media / uploads (D-7)

| Check | How | Status |
|---|---|---|
| `MEDIA_ROOT` points at a persistent disk | env `MEDIA_ROOT=/data/media` | 🔧 |
| Persistent disk attached + mounted at that path | Render dashboard | 🔧 |
| A test upload survives a redeploy | upload a photo → redeploy → photo still loads | 🔧 (manual) |

## 4. Institution isolation / permissions

| Check | How | Status |
|---|---|---|
| A scoped clerk can't reach another institution | run `students.test_institution_isolation` / `_write_isolation` | ✅ 34 tests |
| Group permissions map is the single source | `ensure_default_groups()` (permissions.py) | ✅ (P0-11) |
| Department groups synced at login | login as a clerk → check menu | 🔧 |

## 5. Public + auth hardening (P1-9 / P2-2)

| Check | How | Status |
|---|---|---|
| Public admission form rate-limited | 6 rapid POSTs → throttled | ✅ test_rate_limiting |
| Login locked after 5 failures | 6 bad logins → locked | ✅ test_rate_limiting |
| Upload validation (photo ≤2MB image, xlsx ≤10MB) | `test_upload_security` | ✅ |

## 6. Backup / restore ops (P0-8)

| Check | How | Status |
|---|---|---|
| Scheduled backup runs | Render cron running `scripts/backup_cron.sh` | 🔧 owner |
| Backup persisted **off-cron** | A cron job has **no persistent disk** (it is ephemeral). Copy the backup to **object storage** (R2/S3) or run the backup from a **background worker** that has a disk. `P0B_BACKUP_ROOT` alone on a cron is **not** durable. | 🔧 owner |
| `check_backups` exits 0 when healthy | `python manage.py check_backups` | ✅ |
| Failure alert wired | `HEALTHCHECK_PING_URL` set + health check created | 🔧 owner |
| Restore practised on a disposable DB | `manage.py restore_backup --yes --verify` | ✅ runbook §6 |

> **Correction (important):** Render **cron jobs cannot attach a persistent disk**.
> A disk is available on a paid **web service / private service / background
> worker** only, and a service's disk is not reachable from another service. So a
> cron-run `backup_data` writing to a local `P0B_BACKUP_ROOT` is lost after the
> run — you must upload the backup to object storage (or run the backup from a
> background worker). See `docs/OWNER_RENDER_OPS_TUTORIAL.md` step 2.

## 7. Before a destructive deploy (hard rule)

1. **Back up first** (`manage.py backup_data`).
2. Confirm restore works (`restore_backup --yes --verify` on a throwaway DB).
3. Only then run destructive migrations / commands.
4. Keep a rollback plan (the pre-change backup + prior release).

> **Owner-only, not automatable here:** Render persistent-disk attach, object
> storage upload, health-check/alert creation, and the scheduled cron plan. These
> need Render account access and are documented in `BACKUP_AND_RESTORE.md §8`.
