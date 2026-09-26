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

The goal is to run three commands against the **live** database:

```bash
python manage.py migrate --noinput
python manage.py loaddata students/fixtures/institutions.json   # if the institution list is empty
python manage.py createsuperuser                                # if there is no admin user yet
```

> If you use S3 for media (`USE_S3=True`) the data restore may also involve the
> latest database backup; see `docs/BACKUP_RESTORE_GUIDE.md`.

### Option A — run the commands from your own computer (works on the free tier)

Render's **Shell** is a paid feature, but the **Postgres database accepts
external connections**, so the exact same commands can be run from VS Code /
your laptop against the live database:

1. Render dashboard → your **Postgres** service (not the web service) →
   **Connections** → copy the **External Database URL** (starts with
   `postgres://` — use the *External* one, not the *Internal* one; the internal
   URL only works inside Render's network).
2. In the VS Code terminal, from the repo root (Python 3.12+ needed for
   Django 6.1):

   ```bash
   python -m venv .venv
   # Windows PowerShell:      .\.venv\Scripts\Activate.ps1
   # Windows CMD:             .venv\Scripts\activate.bat
   # macOS / Linux / Git Bash: source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. Point Django at the live database for this terminal session:

   ```bash
   # Windows PowerShell:  $env:DATABASE_URL = "postgres://...external url..."
   # Windows CMD:         set DATABASE_URL=postgres://...external url...
   # macOS / Linux:       export DATABASE_URL="postgres://...external url..."
   ```

4. Run the three commands (shown above). `createsuperuser` asks for the
   username/password interactively in the terminal — that works fine locally.

5. Reload `https://<app>.onrender.com/login/` — the institution cards are back.
   (Free-tier services sleep; the first load may take ~30–60 s to wake up.)

Notes:

- The env var lasts only for that terminal session — leaving it unset later
  means local commands go back to the local SQLite database, which is what you
  want during development.
- Alternatively put `DATABASE_URL=postgres://...` in a local `.env` file
  (already gitignored). Never commit it — the URL contains the DB password.

### Option B — let Render run everything on boot (recommended; no computer needed)

`scripts/render_start.sh` applies migrations and then runs
`manage.py ensure_baseline_data`, which:

- loads the institutions fixture **only when the institution table is empty**
  (admin edits/deletions are never overwritten on restart), and
- creates the superuser named by `DJANGO_SUPERUSER_USERNAME` /
  `DJANGO_SUPERUSER_PASSWORD` **only when that user does not exist yet**.

One-time setup in the Render dashboard:

1. **Environment** (web service) → add:
   - `DJANGO_SUPERUSER_USERNAME` = your admin username
   - `DJANGO_SUPERUSER_PASSWORD` = your admin password
   - `DJANGO_SUPERUSER_EMAIL` (optional)
2. **Settings → Start Command** → `./scripts/render_start.sh`
3. Deploy the latest commit (or just restart the service).

From then on a fresh/expired-and-replaced free-tier Postgres self-heals on the
next boot: update `DATABASE_URL` to the new instance, restart, done — no Shell,
no laptop.

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

The repository includes `.python-version` with `3.12`; keep the Render
`PYTHON_VERSION` setting at Python 3.12 or newer because Django 6.1 does not
install on Python 3.11. If the log says `Django==6.1 ... requires Python
>=3.12`, set `PYTHON_VERSION` to a fully qualified 3.12.x version in Render
and redeploy.

`scripts/render_start.sh` (added in this repo) runs `migrate --noinput` **and
`ensure_baseline_data`** (institutions fixture + superuser from
`DJANGO_SUPERUSER_*` env vars — see Option B above) before launching gunicorn.
Both are idempotent, so they are a no-op once the database is up to date, but
they guarantee a fresh/reset database is brought to the current schema with a
usable admin account before the app serves traffic.

## Defensive change in the code

`students.views.institution_login` now catches a missing-table error and renders
the login page with a clear "database has not been initialised yet" banner
(HTTP 503) instead of an opaque 500. This does not replace running the
migrations — it only makes the failure self-explanatory in the browser and logs
a precise message on the server.
