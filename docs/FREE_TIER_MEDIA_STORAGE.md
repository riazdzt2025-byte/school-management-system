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
| Private by default | With no public base set, objects stay private and `photo.url` is a **signed URL** (default lifetime 24 h, `AWS_S3_QUERYSTRING_EXPIRE`). Student photos are PII; they do not need to be world-readable. |
| `manage.py copy_media_to_storage` | One-way copy of whatever is already in `MEDIA_ROOT` into the bucket, preserving key names. Idempotent; `--dry-run` first. |
| Checks (`students/checks.py`) | `students.E011` (error, every `check`): `USE_S3` set but `django-storages`/`boto3` not installed. `students.W010` (warning, `check --deploy` only): a production `MEDIA_ROOT` inside the app tree, i.e. uploads about to be lost. |
| `backup_data` | Says so when the media archive is empty because media lives in the bucket, so a 0-file `media.tar.gz` is not mistaken for a broken backup. |

Static files are deliberately **not** moved to the bucket: they are baked into the
build image and served by whitenoise, which is faster and free.

## 3. Setup (Cloudflare R2 shown; AWS S3 / B2 / MinIO are the same five variables)

1. **Create the bucket.** R2 dashboard → Object Storage → Create bucket, e.g.
   `school-media`. Private (no `--public` development URL) unless you deliberately
   want public reads. Enable **versioning** — it is the undo button for a bad
   `copy_media_to_storage` run and it costs nothing at this scale.
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
4. **Copy the existing photos over** (Render shell, before the next deploy
   replaces this container):

   ```bash
   python manage.py copy_media_to_storage --dry-run   # read the list
   python manage.py copy_media_to_storage             # do it
   ```

5. **Verify** from the same shell:

   ```bash
   python manage.py check --deploy        # no students.W010 / E011
   python manage.py shell -c "
   from django.conf import settings
   from django.core.files.storage import default_storage
   print(settings.MEDIA_BACKEND, settings.MEDIA_URL)
   print(default_storage.url('student_photos/<some-existing-name>'))"
   ```

   The URL must be an `https://…/<bucket>/media/…` link that opens in a browser.
   Then in the live app: upload a photo on a student, **deploy again**, confirm
   the photo still renders. That last step is the only real proof (P1-11's test).

## 4. Optional: public bucket / CDN

If the signed-URL lifetime is a nuisance (e.g. printed pages cached for days) or
you want Cloudflare's CDN in front, set

```
AWS_S3_PUBLIC_BASE_URL=https://pub-<id>.r2.dev
```

The app then builds `MEDIA_URL` from it and stops signing (objects must be
public-read). Do this knowingly: **anyone with the URL can read every student
photo**, and `student_photos/<name>` names are not secrets.

## 5. Rollback

Unset `USE_S3` and restart: uploads go back to `MEDIA_ROOT` immediately, with no
data loss on either side (the bucket keeps what it received; new writes go to
disk). Keys are identical, so `copy_media_to_storage` in reverse is just a
`aws s3 sync` / `r2://` download if you ever need the files back locally.

## 6. What this does *not* do

- It does not move the **database**, and it does not upload **backups**.
  `backup_data` writes a folder on the local disk; on a Render cron that folder is
  gone after the run, so backups still need their own off-box copy — see
  `docs/OWNER_RENDER_OPS_TUTORIAL.md` Step 2 (Option A) and
  `docs/BACKUP_AND_RESTORE.md`. Same provider, different concern: `USE_S3` covers
  **uploads**, not **dumps**.
- It does not back the bucket up. Versioning + bucket replication is the owner's
  choice; `backup_data` archives the database only when media is remote.
- No migration, no schema change, no new URL route — it is settings, one command,
  and two checks.

## 7. Verification performed

`manage.py check` → 0 issues (W010 is `--deploy`-only by design);
`makemigrations --check` → clean (nothing to migrate); `manage.py test students` →
**293 pass**, of which `students/test_media_storage.py` contributes 33 (13 on the
backend decision and URL rules, 8 on the two checks, 6 on the copy command, 2 on
its file iterator, 4 on the real `S3Storage` wiring).

Those last 4 skip when `django-storages`/`boto3` are absent — CI and the Render
build install both from `requirements.txt`, so they run there (and they passed on
Python 3.12 / Django 6.1 in CI, which is the pinned combination).
