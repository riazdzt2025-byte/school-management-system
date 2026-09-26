# Login page returns HTTP 500 on Render — cause and fix

**Symptom.** `https://<app>.onrender.com/login/` returns **Server Error (500)**,
while `https://<app>.onrender.com/admin/login/` still loads normally.

## Cause

The custom login page is the first page that reads an **application table**
(`students_institution`). The Django admin login page does not — it only needs
the core `auth`/`sessions` tables. So when the application tables are missing,
the admin login keeps working but the site login crashes:

```
ProgrammingError: relation "students_institution" does not exist   # PostgreSQL
OperationalError:  no such table: students_institution             # SQLite
```

The tables are missing because **`python manage.py migrate` was not run against
the current database**. On Render's free tier this typically happens when the
free PostgreSQL instance expires and is replaced with a fresh, empty one: the
next deploy connects to a blank database, and if the deploy does not run
`migrate`, the app tables are never created.

## Fix (do this once on the live service)

Open the Render dashboard → your web service → **Shell**, and run:

```bash
python manage.py migrate --noinput
python manage.py loaddata students/fixtures/institutions.json   # if the institution list is empty
python manage.py createsuperuser                                # if there is no admin user yet
```

Reload `/login/` — it now shows the institution cards again.

> If you use S3 for media (`USE_S3=True`) the data restore may also involve the
> latest database backup; see `docs/BACKUP_RESTORE_GUIDE.md`.

## Prevent it from happening again

Make every deploy apply migrations automatically. In the Render dashboard set:

- **Build Command**
  ```
  pip install -r requirements.txt && python manage.py collectstatic --noinput
  ```
- **Start Command**
  ```
  ./scripts/render_start.sh
  ```

`scripts/render_start.sh` (added in this repo) runs `migrate --noinput` before
launching gunicorn. `migrate` is idempotent, so it is a no-op once the database
is up to date, but it guarantees a fresh/reset database is brought to the
current schema before the app serves traffic.

## Defensive change in the code

`students.views.institution_login` now catches a missing-table error and renders
the login page with a clear "database has not been initialised yet" banner
(HTTP 503) instead of an opaque 500. This does not replace running the
migrations — it only makes the failure self-explanatory in the browser and logs
a precise message on the server.
