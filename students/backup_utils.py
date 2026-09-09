"""Backup / restore helpers for the school management system.

Covers both supported database engines (SQLite via the default dev path, and
Postgres via ``DATABASE_URL``) plus the uploaded-file tree under
``MEDIA_ROOT``. Kept free of model imports so it can run even for a database
whose schema has not been restored yet.

Design rules honoured here (security):

* Credentials are **never** written to the manifest, the log, or a file name.
  For Postgres we drive ``pg_dump`` / ``pg_restore`` through the ``PG*``
  environment variables (which stay inside the child process) rather than
  putting a password on the command line where it would land in ``ps`` / logs.
* The backup manifest records only engine + artifact file names + SHA-256
  digests + a redacted database name, never connection strings.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tarfile
from pathlib import Path

from django.conf import settings

BACKUPS_ENV = "P0B_BACKUP_ROOT"


def backup_root() -> Path:
    """Where backups live. Overridable for the disposable restore drill."""
    override = os.environ.get(BACKUPS_ENV)
    if override:
        return Path(override).resolve()
    return Path(settings.BASE_DIR) / "backups"


def now_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def db_engine() -> str:
    """'sqlite', 'postgres', or 'unknown' — read from settings."""
    engine = settings.DATABASES["default"].get("ENGINE", "")
    if "sqlite" in engine:
        return "sqlite"
    if "postgres" in engine or "postgresql" in engine:
        return "postgres"
    return "unknown"


def sqlite_path() -> Path:
    return Path(settings.DATABASES["default"]["NAME"])


def _postgres_params() -> dict:
    db = settings.DATABASES["default"]
    return {
        "PGDATABASE": db.get("NAME", ""),
        "PGUSER": db.get("USER", "") or "",
        "PGPASSWORD": db.get("PASSWORD", "") or "",
        "PGHOST": db.get("HOST", "") or "localhost",
        "PGPORT": str(db.get("PORT", "") or "5432"),
    }


def postgres_connect_env() -> dict:
    """The ``PG*`` environment (with credentials) for the child dump/restore."""
    env = os.environ.copy()
    env.update(_postgres_params())
    return env


def redacted_db_name() -> str:
    """A safe one-line description of the database, no credentials."""
    db = settings.DATABASES["default"]
    engine = db_engine()
    if engine == "sqlite":
        return f"sqlite:{sqlite_path().name}"
    name = db.get("NAME", "")
    host = db.get("HOST", "")
    return f"postgres:{name}@{host or 'default'}" if name else f"postgres@{host or 'default'}"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def make_backup_dir() -> tuple[Path, str]:
    """Create ``backups/backup-<UTCtimestamp>/`` and return (dir, stamp)."""
    stamp = now_utc().strftime("%Y%m%dT%H%M%SZ")
    root = backup_root()
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"backup-{stamp}"
    counter = 1
    while target.exists():
        stamp = now_utc().strftime("%Y%m%dT%H%M%SZ")
        target = root / f"backup-{stamp}-{counter}"
        counter += 1
    target.mkdir(parents=True, exist_ok=False)
    return target, stamp


def backup_sqlite(src: Path, dest: Path) -> int:
    """Copy a sqlite file to a consistent point-in-time snapshot.

    ``sqlite3``'s online-backup API is used so the snapshot is a frozen,
    consistent copy even while the app is writing to the live file.
    """
    src = src.resolve()
    dest = dest.resolve()
    if not src.exists():
        raise FileNotFoundError(f"SQLite database not found at {src}")
    # The live file may be in WAL mode; connect to it read-write as sqlite's
    # backup API requires a reader connection.
    source_conn = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    try:
        dest_conn = sqlite3.connect(dest)
        try:
            source_conn.backup(dest_conn)
        finally:
            dest_conn.close()
    finally:
        source_conn.close()
    return dest.stat().st_size


def backup_postgres(dest: Path) -> int:
    """pg_dump the live Postgres database into a custom-format dump.

    Credentials are passed via ``PG*`` env vars (never argv). ``pg_dump`` must
    be on ``PATH``; a clear error is raised otherwise.
    """
    if shutil.which("pg_dump") is None:
        raise RuntimeError(
            "pg_dump is not installed/PATH. Install the PostgreSQL client "
            "tools to back up a Postgres database."
        )
    cmd = ["pg_dump", "--format=custom", "--no-owner", "--no-privileges",
           "--file", str(dest)]
    proc = subprocess.run(
        cmd, env=postgres_connect_env(), capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"pg_dump failed: {proc.stderr.strip()}")
    return dest.stat().st_size


def archive_media(media_root: Path | None, dest: Path) -> tuple[bool, int]:
    """Tarball the media tree (``.tar.gz``).

    Returns ``(media_present, file_count)``. When ``media_root`` is missing or
    empty an empty archive is still written so a restore is deterministic, and
    ``media_present`` reflects whether anything was archived.
    """
    dest = Path(dest)
    count = 0
    media_root = Path(media_root) if media_root else None
    with tarfile.open(dest, "w:gz") as tar:
        if media_root and media_root.exists():
            for path in sorted(media_root.rglob("*")):
                # Only regular files; skip symlinks (avoids archiving and then
                # refusing a symlink on restore) and directories.
                if path.is_file() and not path.is_symlink():
                    tar.add(path, arcname=path.relative_to(media_root))
                    count += 1
    return count > 0, count


def write_manifest(path: Path, *, engine: str, db_file: str | None,
                   media_file: str | None, media_count: int,
                   db_sha: str | None, db_size: int | None) -> None:
    data = {
        "format": 1,
        "created_utc": now_utc().isoformat(),
        "engine": engine,
        "database": redacted_db_name(),
        "db_file": db_file,
        "db_sha256": db_sha,
        "db_size_bytes": db_size,
        "media_file": media_file,
        "media_file_count": media_count,
        # Historical note (SEC-1): never store connection strings / passwords.
        "credentials_included": False,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)


def load_manifest(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def prune_old_backups(keep: int, backup_root_dir: Path | None = None) -> list[str]:
    """Delete the oldest backup folders, leaving ``keep`` (>=1) in place."""
    root = Path(backup_root_dir) if backup_root_dir else backup_root()
    if not root.exists():
        return []
    keep = max(1, int(keep))
    dirs = sorted(
        (d for d in root.iterdir() if d.is_dir() and d.name.startswith("backup-")),
        key=lambda d: d.name,
    )
    removed = []
    for old in dirs[: max(0, len(dirs) - keep)]:
        shutil.rmtree(old, ignore_errors=True)
        removed.append(old.name)
    return removed


def find_backup_dir(identifier: str | Path) -> Path:
    """Resolve a backup folder from a name, a path, or a prefix."""
    root = backup_root()
    candidate = Path(identifier)
    if candidate.exists() and candidate.is_dir():
        return candidate.resolve()
    # Match by exact or prefix of the backup folder name within the root.
    matches = sorted(
        d for d in root.iterdir() if d.is_dir() and d.name.startswith(str(identifier))
    )
    if not matches:
        raise FileNotFoundError(
            f"Backup '{identifier}' not found under {root}. "
            "Use a full path or a backup-<timestamp> folder name."
        )
    return matches[0].resolve()


def safe_extract_tar(tar_path: Path, dest_dir: Path) -> int:
    """Extract a media tarball into ``dest_dir``.

    Cross-version safe (Python 3.11 here, so ``extractall(filter=...)`` is not
    available). Every member is resolved and validated against ``dest_dir``
    before extraction; absolute paths, ``..`` traversal, and symlink/hardlink
    members are rejected outright so a tampered archive cannot write outside
    the intended media root.
    """
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_resolved = dest_dir.resolve()
    count = 0
    with tarfile.open(tar_path, "r:gz") as tar:
        for member in tar.getmembers():
            member_path = Path(member.name)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise RuntimeError(
                    f"Refusing to extract '{member.name}' (unsafe path)"
                )
            target = (dest_dir / member_path).resolve()
            if not target.is_relative_to(dest_resolved):
                raise RuntimeError(
                    f"Refusing to extract '{member.name}' (outside {dest_dir})"
                )
            # Reject links — our own archive_media only stores regular files.
            if member.issym() or member.islnk() or not member.isfile():
                raise RuntimeError(
                    f"Refusing to extract '{member.name}' (non-regular file)"
                )
            tar.extract(member, dest_dir)
            count += 1
    return count


def log(msg: str) -> None:
    sys.stdout.write(f"[backup] {msg}\n")
    sys.stdout.flush()


# Small pieces reused by the verification step inside restore_backup.
def iter_file_fields():
    """Yield (model, field_name) for every ImageField/FileField in the app."""
    from django.apps import apps
    for model in apps.get_models():
        fields = []
        for field in model._meta.get_fields():
            if getattr(field, "field", None) is not None:
                field = field.field
            if field.__class__.__name__ in ("ImageField", "FileField"):
                fields.append(field.name)
        for name in fields:
            yield model, name
