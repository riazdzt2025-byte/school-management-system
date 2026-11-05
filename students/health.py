"""Health endpoints for uptime monitors and Render health checks.

Why this exists
---------------
`/healthz/` must answer one question honestly: *can this instance serve pages
right now?* For this app that means the database — every page except the public
admission form reads it. A process that is up but cannot reach Postgres returns
HTTP 200 to a naive check, Render keeps routing traffic to it, and users see
500s. So the check actually opens a cursor and runs ``SELECT 1``.

Deliberate rules:

* No login required. A health check that needs a session cookie reports on the
  session, not on the service.
* No secrets, no hostnames, no table names, no exception text in the body. The
  response is ``{"status": "ok"|"error", "db": "ok"|"error"}`` and nothing more,
  so it is safe to expose publicly (Render's health checks hit this path from
  the public internet on some plans).
* ``Cache-Control: no-store`` — a cached "ok" is worse than no check at all.
* The database connection uses ``connect_timeout`` (see
  ``DB_CONNECT_TIMEOUT`` in settings) so a dead database fails the check in
  seconds instead of hanging until the platform's own timeout.
"""
from django.db import connections
from django.http import JsonResponse
from django.views.decorators.http import require_safe


def _database_ok() -> bool:
    """Open a cursor and run the cheapest possible query."""
    try:
        with connections['default'].cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
    except Exception:  # noqa: BLE001 - any failure means "not ready"
        return False
    return True


@require_safe  # GET/HEAD only: a probe has no business accepting POST (405)
def healthz(request):
    """Liveness + database readiness. 200 when healthy, 503 when not."""
    db_ok = _database_ok()
    payload = {
        'status': 'ok' if db_ok else 'error',
        'db': 'ok' if db_ok else 'error',
    }
    response = JsonResponse(payload, status=200 if db_ok else 503)
    response['Cache-Control'] = 'no-store'
    return response
