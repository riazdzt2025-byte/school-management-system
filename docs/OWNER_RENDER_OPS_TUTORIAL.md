# Owner's step-by-step Render ops tutorial

_For the owner of `school-management-system-27mn.onrender.com`. Read end-to-end
once first — **Step 2 changes the plan a little** because Render cron jobs
cannot use a persistent disk (a fact that the earlier draft missed)._

You have approved the code (PR #10 merged). These steps are dashboard + one small
config choice. No credentials are ever stored in this repo.

---

## Very important background (read this first)

**Render services have an ephemeral filesystem by default** — any change to a
service's local files is **lost on redeploy/restart**. To keep data you use one of:

- a **Render-managed datastore** (Postgres / Key Value), or
- **object storage** (Cloudflare R2 / AWS S3), or
- a **persistent disk** attached to a **paid web / private / background-worker**
  service.

> ⚠️ **A Render Cron Job cannot attach a persistent disk**, and it cannot read a
> disk belonging to any other service. So:
> - **Student photos → disk on the web service** (`MEDIA_ROOT=/data/media`), Step 1.
>   ✅ — but only on a **paid** instance type. On the **free tier** a disk cannot
>   be attached at all, so use **Step 1-alt**: media in object storage via
>   `USE_S3` (`docs/FREE_TIER_MEDIA_STORAGE.md`). That route is now wired in code.
> - **Backups → object storage** (R2/S3) or a **background worker** running the
>   backup. A cron writing to a local `P0B_BACKUP_ROOT` is **ephemeral — gone
>   after the run**.

---

## Step 1 — Persistent disk + `MEDIA_ROOT` (student photos, D-7) — paid plans

**On the free tier, skip to Step 1-alt below.** A Render disk is a paid add-on and
cannot be attached to a free web service, which is the whole reason the app now
supports `USE_S3` for media.

1. In the Render dashboard, open your **Web Service** (`school-management-system-27mn`).
2. Open its **Disks** tab → **Add Disk**.
   - **Name:** `media` (any label)
   - **Mount path:** `/data`  ← the folder that survives redeploys.
   - **Size:** e.g. **1 GB** to start. *It must be paid.* You can grow it later but
     never shrink it.
3. Add **Environment Variable** on the same service:
   - `MEDIA_ROOT` = `/data/media`
4. **Deploy** (the deploy applies the env var). The disk attaches at `/data`, so
   uploaded photos now live at `/data/media` and survive redeploys.

> **Note:** attaching a disk **disables zero-downtime deploys** for that service
> (Render swaps the instance so only one writer touches the disk). Acceptable for
> this app.
> Also: **the disk is only writable at runtime**, not during the build/predeploy.

**Verify:** log in, upload a student photo from the student edit page, then it
still loads after a redeploy.

### Step 1-alt — `USE_S3` object storage for media (the free-tier route)

Same outcome (uploads survive a redeploy), no disk, no paid instance:

1. Create an R2/S3 bucket + API token — steps 1–3 of
   `docs/FREE_TIER_MEDIA_STORAGE.md` (six env vars, listed there).
2. `python manage.py check` → no `students.E011`; `check --deploy` → no
   `students.W010`.
3. `python manage.py copy_media_to_storage --dry-run` and then for real, to move
   the photos that already exist on disk.
4. Upload a photo → **deploy** → photo still loads.

Pick **one** of Step 1 / Step 1-alt. Do not set both a disk and `USE_S3` and then
wonder which copy is authoritative: with `USE_S3` on, `MEDIA_ROOT` is ignored for
new uploads.

> Step 2 (backups) also wants object storage. It can be the **same provider and
> account**, but **not the same bucket prefix**: `backup_data` writes a folder of
> dumps and has no S3 uploader, so that upload is still done by the script in
> Step 2 Option A, not by the app.

---

## Step 2 — Scheduled backup (P0-8) — **must persist off the cron**

Because a cron job's filesystem is ephemeral, do **one** of these two:

### Option A (recommended): cron runs the backup, then uploads to object storage

Set up **object storage first** (Cloudflare R2 is cheap and S3-compatible; AWS S3
also works):

1. Create a **bucket** (e.g. `sms-backups`).
2. Create an **API token / access key** with `Object Read/Write` on that bucket.
   Keep the **Access Key ID**, **Secret Key**, **Endpoint URL** (for R2, e.g.
   `https://<accountid>.r2.cloudflarestorage.com`), **Bucket name**, and a **public
   URL / custom domain** (R2 gives you a `r2.dev` or custom URL).
3. On Render, add these **Environment Variables** to the cron job (dashboards or
   `render.cron.yaml`), plus the `DATABASE_URL` already on the web service:

   | Var | Example |
   |---|---|
   | `P0B_BACKUP_ROOT` | `/tmp/backups` (staging only — not durable) |
   | `BACKUP_OBJECT_STORAGE_BUCKET` | `sms-backups` |
   | `BACKUP_OBJECT_STORAGE_URL` | `https://<accountid>.r2.cloudflarestorage.com` (copy the folder to `s3://sms-backups/...` or your R2 alias) |
   | `BACKUP_OBJECT_STORAGE_ACCESS_KEY` | `<your-key-id>` (secret) |
   | `BACKUP_OBJECT_STORAGE_SECRET_KEY` | `<your-secret>` (secret) |
   | `HEALTHCHECK_PING_URL` | `https://hc-ping.com/<id>` (from Step 3) |

   Then in the cron's `startCommand`, after the backup is created, upload the
   newest folder. With `rclone` (single binary, S3-compatible) you can add:

   ```bash
   # in scripts/backup_cron.sh after "Backup complete"
   newest=$(ls -dt "$P0B_BACKUP_ROOT"/backup-* | head -1)
   rclone copy "$newest" "backup-r2:sms-backups/$(basename "$newest")"
   ```

   (If you prefer the AWS CLI: `aws s3 cp --recursive "$newest" s3://sms-backups/$(basename "$newest")`.)
   The key idea: **copy the backup off the cron's ephemeral filesystem.**

### Option B: run the backup from a background worker that has a disk

- Provision a Render **Background Worker** (paid), attach a **disk** at
  `/data/backups`, set `P0B_BACKUP_ROOT=/data/backups`, and run `backup_data`
  there. More work and you still want an off-box copy for true redundancy.

**Either way, `manage.py check_backups` stays the health gate** — run it against
the staging path to confirm the backup is complete, and against the object-storage
copy to confirm durability.

> Do **not** treat a cron backup written to local disk as your only copy.

---

## Step 3 — Healthchecks.io alert (so a silent failure wakes you up)

1. Create a free account at **healthchecks.io**.
2. **Add Check** → choose the **cron** / "simple ping" type → name it `sms-backup`.
3. Copy the generated **ping URL**: `https://hc-ping.com/<uuid>`.
4. Wherever the job ends, **ping it**:
   - success → `GET https://hc-ping.com/<uuid>`
   - failure → `GET https://hc-ping.com/<uuid>/fail`
   `scripts/backup_cron.sh` already does this when `HEALTHCHECK_PING_URL` is set.
5. In Healthchecks, set an **alerting schedule** ("down for more than X minutes"
   or "did not check in for N days") and pick **email / Slack / Telegram**.
6. Also on **Render**, the cron job's **exit code** drives failure:
   a **non-zero exit** marks the run failed (Render can email/Slack you). Our
   scripts exit non-zero on failure — so both layers alert you.

---

## Step 4 — Real production backup: end-to-end verify

1. On Render, open the backup cron job → **Trigger run** (you don't wait for the
   schedule). Watch the log:
   - `Database engine: ...`, `Backup folder: ...`, `Backup complete: ...`
   - `check_backups OK: newest backup ...` (exit 0). If you see
     `check_backups FAILED`, read the line above.
2. Confirm an **off-box copy exists**: open your object-storage bucket and see the
   `backup-<UTCtimestamp>/` folder with `db.sqlite3` (or `db.dump`) + `media.tar.gz`
   + `manifest.json`.
3. **Verify integrity** from your own machine (or a Render shell) against a
   **copy**, never the live DB:
   ```bash
   # download the backup folder, then:
   python manage.py restore_backup --backup-root <path> --yes --verify
   ```
   Expect `DB artifact SHA-256 OK`, `migrate --check OK`, media references OK.
   (Full drill in `docs/BACKUP_AND_RESTORE.md` §6.)
4. **Restore drill** on a throwaway DB/`MEDIA_ROOT` (in `/tmp`), not production.
5. Record the timestamp of the successful run — that's your rollback point.

> The commit you merge (PR #10 / `1071b0c`) is tested; **do not** treat a single
> local test restore as proof the scheduled production backup works — do the
> end-to-end step above on Render.

---

## Step 5 — D-6: confirm the permission sets (a quick policy check)

Current state (P0-11 made `students/permissions.py` the single source; running
`setup_groups` no longer diverges). Confirm whether you want:

1. **Exam group** — `permissions.py` does **not** grant `delete_exam`; the old
   `setup_groups` did. **Current behaviour: Exam cannot delete exams.** Confirm
   that's intended (I'd recommend yes — deletes are risky).
2. **Accounts group** — holds `Exam` add/change **and** `ExamMark` add/change/delete.
   Confirm Accounts should keep exam/marks permissions (this was flagged unusual).
3. If either is wrong, change it in **`students/permissions.py`** (the map only),
   then re-run `manage.py setup_groups` — it applies exactly the map.

No code change is needed from me; this is a live-permission-policy confirmation.

---

## Step 6 — P1-10: switching the production DB to Postgres (own, staged session)

The code already reads `DATABASE_URL`, so switching is (in a **staging** env
first — never straight to prod):

1. Provision a **Render Postgres** (paid, or a cheap plan) in the dashboard.
2. Create a **new Render service / preview** pointing at `main` with:
   `DATABASE_URL=postgres://.../dbname` (the new DB). Add `PGPASSWORD`/PG* vars if
   your backup uses them.
3. Run `python manage.py migrate` against that Postgres.
4. Run **`manage.py check`** and the **full test suite** against it (CI already
   proves this in `.github/workflows/tests.yml`).
5. Copy production data: `manage.py backup_data` on the old DB → `pg_restore`
   into Postgres (see `docs/BACKUP_AND_RESTORE.md` §5).
6. Verify counts / integrity, then point the **live** service at `DATABASE_URL` to
   Postgres and set the app's `DATABASE_URL` accordingly. **Keep a rollback**:
   the pre-switch backup + the previous deploy.
7. Confirm `pg_dump`/`pg_restore` exist in the runtime so future backups work.

> This is a **staged data migration** — needs a backup first, a staging copy, and
> a rollback plan. Do it as its own session, never in the same change as feature
> work.

---

## Summary checklist

- [ ] Web service disk `/data` + `MEDIA_ROOT=/data/media` (photos persist).
- [ ] Backup cron writes, then **uploads to object storage** (R2/S3) or runs on a
  disk-backed worker.
- [ ] `HEALTHCHECK_PING_URL` set + Healthchecks alert on "missed check-in".
- [ ] `manage.py check_backups` exits 0 on Render; `Trigger run` verified.
- [ ] Real production backup downloaded + `restore_backup --yes --verify` OK.
- [ ] D-6 permission sets confirmed.
- [ ] (later, own session) P1-10 staged Postgres switch.

Everything marked 🔧 needs your Render account access — that's the only reason it
isn't automated here. No API token/secret is ever asked for.
