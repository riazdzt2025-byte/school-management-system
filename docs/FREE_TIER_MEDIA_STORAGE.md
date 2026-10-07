# Free-tier media storage (P1-11 / D-7) — uploads that survive a deploy

**Who this is for:** the owner of the Render service, plus whoever runs the next
deploy. Nothing here costs money at this school's volume, and nothing changes
local development.

## 1. The problem in one paragraph

Render's free tier gives a service an **ephemeral container filesystem**. It is
rebuilt from the image on every deploy and reset on every cold start (free
services sleep when idle). Anything written at runtime — a student photo, an
imported spreadsheet — lands in `BASE_DIR/media` and **is deleted**. The database
keeps the row, so the app looks healthy while `photo.url` points at a file that
no longer exists. There is no error to read; the picture is just gone.

A Render **persistent disk** also fixes this, but it is a paid add-on and cannot
be attached to a free instance. Object storage is the free-tier route, so this
repo does object storage.

## 2. What is implemented

| Piece | Behaviour |
|---|---|
| `USE_S3` env flag (`school_system/settings.py`) | `True` → media goes to an S3-compatible bucket via `django-storages`; unset/false → today's local `FileSystemStorage`. Opt-in, so dev/preview are untouched. |
| `media_storage_config(env)` / `media_public_url(config, env)` | Pure helpers that decide the backend and the media URL prefix, and raise `ImproperlyConfigured` at boot if `USE_S3` is on but the bucket or keys are missing. A half-configured bucket is refused rather than silently falling back to the disk that gets wiped. |
| `MEDIA_URL` | `/media/` on the filesystem; on S3 it becomes the bucket/CDN prefix (or your `AWS_S3_PUBLIC_BASE_URL`), overridable with an explicit `MEDIA_URL`. |
| Private by default | With no public base set, objects stay private and `photo.url` is a **signed URL** (default lifetime 24 h, `AWS_S3_QUERYSTRING_EXPIRE`); uploaded objects use `Cache-Control: private, no-store` by default. Student photos are PII; they must not be world-readable. |
| `manage.py copy_media_to_storage` | One-way copy of whatever is already in `MEDIA_ROOT` into the bucket, preserving key names. Idempotent; `--dry-run` first. |
| Checks (`students/checks.py`) | `students.E011` (error, every `check`): `USE_S3` set but `django-storages`/`boto3` not installed. `students.W010` (warning, `check --deploy` only): production `MEDIA_ROOT` inside the app tree. `students.E012` (error, `check --deploy` only): student-photo storage is public/shared-cache or production filesystem media. |
| `backup_data` | Says so when the media archive is empty because media lives in the bucket, so a 0-file `media.tar.gz` is not mistaken for a broken backup. |

Static files are deliberately **not** moved to the bucket: they are baked into the
build image and served by whitenoise, which is faster and free.

## 3. Setup (Cloudflare R2 shown; AWS S3 / B2 / MinIO are the same five variables)

1. **Create the bucket.** R2 dashboard → **R2 Object Storage** → **Create bucket**,
   e.g. `school-media`. Keep it private and do **not** enable the
   `pub-….r2.dev` development URL; the owner-confirmed policy forbids public
   access to student photos.

   **About versioning:** R2 has **no object versioning** (`PutBucketVersioning` is
   not implemented; it has Cloudflare *Bucket Locks* for retention instead). So the
   bucket is not an undo button. What actually protects you here:
   `copy_media_to_storage` never deletes or overwrites a *source* file, it only
   skips or replaces bucket objects; the database dump still lives elsewhere
   (§6); and if you want true versions, choose **AWS S3** (versioning on the bucket)
   or **Backblaze B2** (native file versions) — the app config is identical, only
   `AWS_S3_ENDPOINT_URL` / `AWS_S3_REGION_NAME` change.
2. **API token.** R2 → Manage R2 API Tokens → create, scoped to that bucket,
   Object Read & Write. That gives you an Access Key ID, a Secret Access Key and
   an endpoint like `https://<account-id>.r2.cloudflarestorage.com`.
3. **Render → Environment** (add these, restart the service):

   ```
   USE_S3=True
   AWS_STORAGE_BUCKET_NAME=school-media
   AWS_ACCESS_KEY_ID=<from step 2>
   AWS_SECRET_ACCESS_KEY=<from step 2>
   AWS_S3_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
   AWS_S3_REGION_NAME=auto
   ```

   For real AWS S3: drop `AWS_S3_ENDPOINT_URL` and set
   `AWS_S3_REGION_NAME=ap-southeast-1` (or wherever the bucket is). For Backblaze
   B2: `https://s3.<region>.backblazeb2.com`. For MinIO: `http://<host>:9000`.
   `AWS_LOCATION` (default `media`) is the key prefix, so one bucket can hold more
   than one app.
4. **Copy the existing photos over** — *if there are any left to copy*. A Render
   **free web service has no Shell access and cannot run one-off jobs** (paid
   plans only), so pick the route that fits:

   | Route | When | How |
   |---|---|---|
   | **Skip the copy** | the usual case on the free tier: the disk was wiped by the last deploy, so only photos uploaded since then exist | just tell the office to re-upload those few photos after the switch. Zero ops, zero risk |
   | **Run it on Render** | the photos on the live disk matter and there are many | upgrade the service to **Starter ($7)** → *Shell* tab → `python manage.py copy_media_to_storage --dry-run` then without the flag → downgrade to Free. Billing is hourly, so this costs cents |
   | **Run it from a laptop** | you have the same media tree locally (dev machine, a disk snapshot) | `USE_S3=… AWS_…=… python manage.py copy_media_to_storage --media-root ./media` with the six variables exported locally |

   Nothing is deleted by the command, so running it twice, or running it and then
   re-uploading a photo by hand, is harmless.

   > Deliberately **not** a web endpoint: it iterates every upload and issues one
   > S3 request per file, which would sit inside a 60-second request timeout and
   > turn a maintenance task into a user-visible failure. The existing
   > admin-only maintenance pages are for single-record actions; this is not.

5. **Verify.** On a paid instance use the Shell; on the free tier put the commands
   in the service's **Build & System Commands → Build command** instead — they run
   at build time, need no media, and a failing `check` already stops a bad deploy:

   ```bash
   pip install -r requirements.txt && python manage.py collectstatic --noinput \
     && python manage.py check --deploy
   ```


   ```bash
   python manage.py check --deploy        # no students.E011 / W010 / E012
   python manage.py shell -c "
   from django.conf import settings
   from django.core.files.storage import default_storage
   print(settings.MEDIA_BACKEND, settings.MEDIA_URL)
   print(default_storage.url('student_photos/<some-existing-name>'))"
   ```

   The URL must be an `https://…/<bucket>/media/…` signed link that opens while
   valid; do not share the signature publicly. Independently verify the bucket
   blocks anonymous object reads (Django's deploy check cannot inspect policy).
   Then, **if you want live proof** (optional — waived by the owner on 2026-09-09):
   upload a photo on a student, **deploy again**, confirm the photo still renders.
   That last step is the only check that exercises production instead of tests, so
   skipping it leaves P1-11 closed on code + CI evidence only — say so in the notes
   rather than letting the next person assume the live check happened.

## 4. Public bucket / CDN — prohibited for student photos

The owner confirmed on 2026-10-07 that student photos must remain private.
Therefore, **do not set `AWS_S3_PUBLIC_BASE_URL`, a public ACL, or shared-cache
policy for student-photo media**. Public base URLs disable signed URLs and let
anyone with a URL read the photo. If a future product needs public non-student
assets, store them in a separate bucket/backend that cannot contain student
photos; do not weaken this media configuration.

`manage.py check --deploy` fails with `students.E012` for public base URLs,
non-private ACL/signing, public/shared-cache directives, or production filesystem
media. The private S3 default uses signed URLs and `Cache-Control: private, no-store`.
The check cannot inspect bucket policy or effective deployed environment, so owner
verification of anonymous-read blocking remains required.

## 5. Rollback

In **development only**, unsetting `USE_S3` returns new uploads to `MEDIA_ROOT`.
For production, do not roll student photos back to filesystem media: with
`DEBUG=False`, `students.E012` blocks that configuration because there is no
reviewed authenticated media proxy. Restore a working private bucket config or
implement and review a private proxy before changing production storage. The
bucket keeps existing objects; a download for an approved local/isolated drill
can use `aws s3 sync` / `r2://` without changing the production app.

## 6. What this does *not* do

- **If `DATABASE_URL` is unset, the database is `BASE_DIR/db.sqlite3` — on the same
  ephemeral disk this PR exists to escape.** A deploy then wipes students, marks and
  fees, not just photos, and a Free instance cannot attach a disk to fix it. Check
  Render → Environment for `DATABASE_URL` before assuming records are safe
  (`docs/PRODUCTION_CHECKLIST.md` §2, and the open item in `docs/BACKUP_AND_RESTORE.md`).
- It does not upload **backups** from the app itself.
  `backup_data` writes a folder on the local disk; on a Render cron that folder is
  gone after the run, so backups still need their own off-box copy — see
  `docs/OWNER_RENDER_OPS_TUTORIAL.md` Step 2 (Option A) and
  `docs/BACKUP_AND_RESTORE.md`. Same provider, different concern: `USE_S3` covers
  **uploads**, not **dumps**.
- It does not back the **bucket** up. R2 keeps no versions, so an object that is
  overwritten or deleted stays gone (Cloudflare's *Bucket Locks* only block
  deletion for a retention period) — if undo matters to you, use S3/B2 with
  versioning, where the app config is unchanged. Separately, `backup_data` keeps
  archiving the **database**, and its `media.tar.gz` is empty once media is remote.
- It does not create the bucket, and on the free tier you cannot run one-off
  commands on the service at all (no Shell), which is why §3 step 4 lists routes
  instead of one command.
- The original storage-wiring scope required no migration. OF-05 later added the
  `StudentPhotoDeletionJob` outbox table in migration `0048_studentphotodeletionjob.py`.

## 7. Verification

The numbers below are the **historical verification for the original storage
wiring**, not the current OF-05 test totals: `manage.py check` → 0 issues;
`makemigrations --check` → clean; the earlier focused students suite had 293
passes and `students/test_media_storage.py` had 33. The current full/focused
counts and privacy-guard evidence are maintained in
`docs/prompts/reports/OF-05.md` (latest local run: 860 Django + 29 Node; 121
focused, including 39 media-storage tests).

The real `S3Storage` wiring tests require `django-storages`/`boto3`; CI and the
Render build install both from `requirements.txt`. CI runs the deploy guard with
synthetic private storage settings, and separately proves public media settings
fail with `students.E012`. No live bucket request or deployed policy inspection
is performed by those tests.

## 8. Student-photo deletion retries (OF-05)

When a student photo is cleared, replaced, or hard-purged, the database transaction
also writes a `StudentPhotoDeletionJob` row. An `on_commit` fast path deletes the
object immediately when storage is healthy. If the process stops after commit or
the backend fails, the outbox row remains; the worker retries with exponential
backoff, starting at 60 seconds and capped at 24 hours. Only exception type and
job ID are logged—never the object key or backend error message.

Run the bounded worker with:

```sh
python manage.py retry_student_photo_deletions --limit 100
```

A deployment scheduler must invoke it periodically (for example every 5 minutes)
with the same database and media-storage configuration as the web app. The command
returns a nonzero exit if any deletes fail, while retaining those jobs for retry.
On SQLite, schedule only one worker at a time. **No scheduler has been configured
or verified for this project**, and the Render free service has no shell or
one-off jobs; an approved external/scheduled execution path is still required.
Do not treat the durable table alone as proof that automatic retries are running.

The older §6 statement that the storage-wiring change had “no migration” predates
OF-05: photo deletion retry now adds `students_studentphotodeletionjob` in
migration `0048_studentphotodeletionjob.py`.
