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
  The same rule applies to the backup passphrase (``-pass env:VAR``) and to the
  object-storage keys (boto3 client kwargs), neither of which ever reaches argv.
* The backup manifest records only engine + artifact file names + SHA-256
  digests + a redacted database name, never connection strings.
* Artifacts are chmod ``0600`` and backup folders ``0700``: they contain PII,
  so a shared host / a misconfigured web root must not expose them.
* Artifacts can be encrypted at rest (``BACKUP_ENCRYPTION=openssl|age``) and an
  independent copy can be pushed to an S3-compatible bucket, so losing the app
  host does not mean losing the backups.
"""
from __future__ import annotations

import contextlib
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

#: Journal / write-ahead-log files SQLite keeps next to a database file. They
#: carry committed (or half-committed) state, so a restore that replaces only
#: the main file leaves the database in the old state — see
#: :func:`remove_sqlite_sidecars`.
SQLITE_SIDECAR_SUFFIXES = ("-wal", "-shm", "-journal")

# --- Encryption at rest -----------------------------------------------------
# A backup folder is a full copy of the school's PII (names, guardian numbers,
# photos). It therefore has to be unreadable to anyone who is not the owner:
# on the local filesystem that is a 0600 file mode, and for anything that
# leaves the box (object storage, a USB stick, a support ticket) it is
# encryption. Both are opt-in via env so development keeps working unchanged.
ENCRYPTION_ENV = "BACKUP_ENCRYPTION"
PASSPHRASE_ENV = "BACKUP_PASSPHRASE"
PASSPHRASE_FILE_ENV = "BACKUP_PASSPHRASE_FILE"
AGE_RECIPIENT_ENV = "BACKUP_AGE_RECIPIENT"
AGE_IDENTITY_ENV = "BACKUP_AGE_IDENTITY_FILE"

# Key-stretching iterations for the openssl passphrase. 600k is above
# openssl's own 10k default and costs ~0.3 s per call — irrelevant for a
# nightly job, expensive for someone guessing passphrases offline.
OPENSSL_ITERATIONS = 600000
ENCRYPTED_SUFFIX = ".enc"

#: Human-readable label written into the manifest so a restore years from now
#: knows exactly which scheme (and parameters) produced the artifact.
ENCRYPTION_LABELS = {
    "openssl": f"openssl:aes-256-cbc:pbkdf2:{OPENSSL_ITERATIONS}",
    "age": "age:x25519",
}

# --- Off-box copy (object storage) -----------------------------------------
# A backup that lives on the same disk as the database survives a bad deploy
# but not a lost disk. These variables point at an S3-compatible bucket that
# holds an independent copy. They are deliberately separate from the media
# bucket's AWS_* variables so the backup key can be scoped to one bucket.
OBJECT_STORAGE_BUCKET_ENV = "BACKUP_OBJECT_STORAGE_BUCKET"
OBJECT_STORAGE_ACCESS_KEY_ENV = "BACKUP_OBJECT_STORAGE_ACCESS_KEY"
OBJECT_STORAGE_SECRET_KEY_ENV = "BACKUP_OBJECT_STORAGE_SECRET_KEY"
OBJECT_STORAGE_ENDPOINT_ENV = "BACKUP_OBJECT_STORAGE_ENDPOINT"
OBJECT_STORAGE_REGION_ENV = "BACKUP_OBJECT_STORAGE_REGION"
OBJECT_STORAGE_PREFIX_ENV = "BACKUP_OBJECT_STORAGE_PREFIX"
OBJECT_STORAGE_KEEP_ENV = "BACKUP_OBJECT_STORAGE_KEEP"


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


def _pg_connection_params() -> dict:
    """The psycopg2 kwargs Django itself connects with.

    This is the single source of truth for where the database actually is.
    Reading ``settings.DATABASES['default']['HOST']`` instead is wrong: a
    ``DATABASE_URL`` such as ``postgres://user@/dbname?host=/var/run/postgresql``
    leaves ``HOST`` empty and puts the socket directory in ``OPTIONS``, so a
    dump driven off ``HOST`` would target ``localhost`` — a different server
    from the one the application is writing to.
    """
    from django.db import connections
    return connections["default"].get_connection_params()


# psycopg2 connection kwargs -> libpq environment variables. Anything not in
# this map (cursor_factory, client_encoding, ...) is a client-side setting with
# no meaning to pg_dump and is deliberately dropped.
_PG_ENV_MAP = {
    "dbname": "PGDATABASE",
    "user": "PGUSER",
    "password": "PGPASSWORD",
    "host": "PGHOST",
    "port": "PGPORT",
    "options": "PGOPTIONS",
    "application_name": "PGAPPNAME",
    "connect_timeout": "PGCONNECT_TIMEOUT",
    "sslmode": "PGSSLMODE",
    "sslrootcert": "PGSSLROOTCERT",
    "sslcert": "PGSSLCERT",
    "sslkey": "PGSSLKEY",
    "target_session_attrs": "PGTARGETSESSIONATTRS",
    "service": "PGSERVICE",
}


def _postgres_params() -> dict:
    """The ``PG*`` environment for pg_dump / pg_restore, from Django's params.

    Empty values are omitted rather than defaulted: an unset ``PGHOST`` makes
    libpq use its default socket directory, which is exactly what Django does
    when ``HOST`` is blank. Inventing ``localhost`` there would silently point
    the dump at another server.
    """
    env = {}
    for key, var in _PG_ENV_MAP.items():
        value = _pg_connection_params().get(key)
        if value is None or value == "":
            continue
        env[var] = str(value)
    return env


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
    # Prefer the host Django actually connects with (OPTIONS can carry a socket
    # directory that HOST does not), and fall back to settings if resolving it
    # is impossible — this label must never be the reason a backup fails.
    host = db.get("HOST", "")
    try:
        host = _pg_connection_params().get("host") or host
    except Exception:  # noqa: BLE001 - a broken config must not break the label
        pass
    where = host or "local socket"
    return f"postgres:{name}@{where}" if name else f"postgres@{where}"


def media_backend_label() -> str:
    """Where uploaded media actually lives: ``filesystem`` or ``s3:<bucket>``.

    Recorded in the manifest because it decides whether ``media.tar.gz`` is the
    whole story. With ``USE_S3`` on, the local tree is legitimately empty and the
    bucket is the copy of record for uploads — a restorer who does not know that
    would "restore" zero photos and believe the job was done.
    """
    config = getattr(settings, "MEDIA_CONFIG", None) or {}
    if config.get("backend") == "s3":
        return f"s3:{config.get('bucket', '')}"
    return "filesystem"


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
    # Private from the moment it exists: it is about to hold the whole DB.
    harden_permissions(root)
    harden_permissions(target)
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
    harden_permissions(Path(dest))
    return dest.stat().st_size


def sqlite_sidecars(db_path: Path) -> list[Path]:
    """The journal / WAL sidecar files that belong to ``db_path``.

    SQLite keeps write-ahead and rollback state *next to* the database file
    (``-wal`` + ``-shm`` in WAL mode, ``-journal`` for a rollback journal). They
    are part of the database's state, not decoration.
    """
    db_path = Path(db_path)
    return [db_path.with_name(db_path.name + suffix)
            for suffix in SQLITE_SIDECAR_SUFFIXES]


def remove_sqlite_sidecars(db_path: Path) -> list[str]:
    """Delete any stale sidecar files next to ``db_path``; return their names.

    A restore that replaces only the main file is *silently wrong* when the old
    sidecars survive: on the next open SQLite replays the leftover ``-wal``
    (or rolls back from a hot ``-journal``) and the application sees the data
    that was there **before** the restore, with ``PRAGMA integrity_check``
    reporting ``ok``. Reproduced locally: restoring a snapshot containing
    ``NEW`` over a WAL-mode database whose stale ``-wal`` held ``OLD`` made the
    first reader see ``OLD`` — a restore that reported success and restored
    nothing. So the sidecars go before the file is replaced.
    """
    removed = []
    for sidecar in sqlite_sidecars(db_path):
        try:
            sidecar.unlink()
        except FileNotFoundError:
            continue
        except OSError as exc:  # a sidecar we cannot remove must not be ignored
            raise RuntimeError(
                f"Could not remove the stale SQLite sidecar {sidecar}: {exc}. "
                "Refusing to restore over a database whose journal state is "
                "out of our control."
            )
        removed.append(sidecar.name)
    return removed


def replace_sqlite_database(src: Path, dest: Path) -> tuple[int, list[str]]:
    """Overwrite ``dest`` with the snapshot ``src``; return (size, removed).

    The whole replacement, in the order it has to happen:

    1. drop any stale ``-wal``/``-shm``/``-journal`` next to the target (see
       :func:`remove_sqlite_sidecars` — leaving them makes the restore a no-op
       that looks like a success),
    2. copy the snapshot over the target,
    3. re-read the target and compare its SHA-256 with the source's, so a
       truncated or partial copy is reported here instead of surfacing later as
       "database disk image is malformed",
    4. harden the file mode (a restored database is as sensitive as a backup).

    Callers must close Django's connections first (``connections.close_all()``):
    an open handle can re-create a sidecar file the moment it is closed.
    """
    src, dest = Path(src), Path(dest)
    if not src.exists():
        raise FileNotFoundError(f"Snapshot to restore not found at {src}")
    removed = remove_sqlite_sidecars(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)
    source_sha, dest_sha = sha256(src), sha256(dest)
    if source_sha != dest_sha:
        raise RuntimeError(
            f"Restored database at {dest} does not match the snapshot "
            f"({dest_sha[:12]}… != {source_sha[:12]}…) — the copy is incomplete. "
            "Do not start the application against it."
        )
    harden_permissions(dest)
    return dest.stat().st_size, removed


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
    harden_permissions(Path(dest))
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
    harden_permissions(Path(dest))
    return count > 0, count


def write_manifest(path: Path, *, engine: str, db_file: str | None,
                   media_file: str | None, media_count: int,
                   db_sha: str | None, db_size: int | None,
                   encryption: str | None = None,
                   db_plain_sha: str | None = None,
                   media_plain_sha: str | None = None,
                   media_sha: str | None = None,
                   media_backend: str | None = None) -> None:
    """Write ``manifest.json``.

    ``db_sha`` / ``media_sha`` are always the digests of the bytes **on disk**
    (the ciphertext when encryption is on) — that is what ``check_backups``
    validates, because it is what corruption or a truncated upload changes.
    ``db_plain_sha`` / ``media_plain_sha`` are the digests of the *decrypted*
    payload, so a restore can prove the decryption produced the original file
    and not merely "some" file.
    """
    data = {
        "format": 2,
        "created_utc": now_utc().isoformat(),
        "engine": engine,
        "database": redacted_db_name(),
        "db_file": db_file,
        "db_sha256": db_sha,
        "db_size_bytes": db_size,
        "media_file": media_file,
        "media_file_count": media_count,
        "media_sha256": media_sha,
        # Where uploads live, so a restore knows whether media.tar.gz is the
        # whole story or whether a bucket holds the copy of record.
        "media_backend": media_backend,
        # None when artifacts are plaintext; the scheme label when encrypted.
        "encryption": encryption,
        "db_plain_sha256": db_plain_sha,
        "media_plain_sha256": media_plain_sha,
        # Historical note (SEC-1): never store connection strings / passwords.
        "credentials_included": False,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
    harden_permissions(Path(path))


def load_manifest(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


# --------------------------------------------------------------------------
# Access control on the local filesystem
# --------------------------------------------------------------------------
def harden_permissions(path: Path) -> None:
    """Make a backup path private: ``0700`` for a directory, ``0600`` for a file.

    A backup is a complete copy of the school's PII. The default umask leaves it
    world-readable (``0644``), which on a shared host — or in a web root that
    got mounted one directory too high — is a data breach waiting to happen.
    Best-effort by design: a filesystem without POSIX modes (a Windows checkout,
    some network mounts) must not fail an otherwise good backup.
    """
    path = Path(path)
    if not path.exists():
        return
    try:
        path.chmod(0o700 if path.is_dir() else 0o600)
    except OSError:
        pass


def world_readable(path: Path) -> bool:
    """True when group or others can read ``path`` (POSIX only)."""
    if os.name != "posix":
        return False
    try:
        mode = Path(path).stat().st_mode
    except OSError:
        return False
    return bool(mode & 0o077)


# --------------------------------------------------------------------------
# Encryption at rest (optional)
# --------------------------------------------------------------------------
def encryption_mode(env=None) -> str:
    """The requested encryption scheme: ``'off'``, ``'openssl'`` or ``'age'``.

    Unknown values raise rather than silently falling back to plaintext: an
    operator who asked for encryption and got none has been lied to, and the
    artifacts are already sitting on disk unencrypted.
    """
    env = os.environ if env is None else env
    raw = (env.get(ENCRYPTION_ENV) or "off").strip().lower()
    if raw in ("", "off", "none", "false", "0"):
        return "off"
    if raw not in ENCRYPTION_LABELS:
        raise RuntimeError(
            f"{ENCRYPTION_ENV}={raw!r} is not supported. "
            f"Use one of: off, {', '.join(sorted(ENCRYPTION_LABELS))}."
        )
    return raw


def _subprocess_env(env, extra=None) -> dict:
    """A copy of the environment for the child process (never mutates ours)."""
    child = os.environ.copy()
    if env is not None and env is not os.environ:
        child.update({k: v for k, v in env.items() if v is not None})
    if extra:
        child.update(extra)
    return child


def _run(cmd: list[str], env: dict, what: str) -> None:
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if proc.returncode != 0:
        # stderr from these tools can echo the input path but not the secret;
        # still, keep it short and never re-print argv.
        raise RuntimeError(f"{what} failed: {(proc.stderr or '').strip()[:400]}")


def _passphrase_env(env) -> dict:
    """The passphrase as an environment mapping for ``openssl -pass env:VAR``.

    ``BACKUP_PASSPHRASE_FILE`` (a 0600 file, e.g. ``/etc/sms/backup.key``) is
    preferred over ``BACKUP_PASSPHRASE``: a file does not show up in the process
    environment of the scheduler, in a Render dashboard env dump, or in a core
    dump. Either way the value never reaches argv.
    """
    env = os.environ if env is None else env
    file_path = (env.get(PASSPHRASE_FILE_ENV) or "").strip()
    value = ""
    if file_path:
        path = Path(file_path).expanduser()
        if not path.exists():
            raise RuntimeError(
                f"{PASSPHRASE_FILE_ENV}={file_path} does not exist."
            )
        value = path.read_text(encoding="utf-8").strip()
    if not value:
        value = (env.get(PASSPHRASE_ENV) or "").strip()
    if not value:
        raise RuntimeError(
            f"{ENCRYPTION_ENV} is set but no passphrase was found. Provide "
            f"{PASSPHRASE_FILE_ENV}=/path/to/key (preferred) or {PASSPHRASE_ENV}. "
            "Never commit the passphrase."
        )
    return {PASSPHRASE_ENV: value}


def _openssl_cmd(direction: str, src: Path, dest: Path) -> list[str]:
    return [
        "openssl", "enc", direction, "-aes-256-cbc", "-pbkdf2",
        "-iter", str(OPENSSL_ITERATIONS), "-salt",
        "-in", str(src), "-out", str(dest),
        "-pass", f"env:{PASSPHRASE_ENV}",
    ]


def encrypt_artifact(path: Path, env=None, mode: str | None = None) -> Path:
    """Encrypt ``path`` in place to ``<path>.enc`` and delete the plaintext.

    Returns the path of the encrypted artifact. The scheme comes from
    ``BACKUP_ENCRYPTION`` unless ``mode`` is given; the plaintext is removed as
    soon as the ciphertext is written, so an interrupted run leaves the
    encrypted copy, never both.
    """
    mode = mode if mode is not None else encryption_mode(env)
    if mode == "off":
        return Path(path)
    path = Path(path)
    dest = path.with_name(path.name + ENCRYPTED_SUFFIX)
    if mode == "openssl":
        if shutil.which("openssl") is None:
            raise RuntimeError(
                "openssl is not installed/on PATH — cannot encrypt the backup. "
                "Install openssl or unset BACKUP_ENCRYPTION."
            )
        child_env = _subprocess_env(env, _passphrase_env(env))
        _run(_openssl_cmd("-e", path, dest), child_env, "openssl encrypt")
    elif mode == "age":
        if shutil.which("age") is None:
            raise RuntimeError(
                "age is not installed/on PATH — cannot encrypt the backup. "
                "Install age (https://age-encryption.org) or use "
                f"{ENCRYPTION_ENV}=openssl."
            )
        env_map = os.environ if env is None else env
        recipient = (env_map.get(AGE_RECIPIENT_ENV) or "").strip()
        if not recipient:
            raise RuntimeError(
                f"{ENCRYPTION_ENV}=age needs {AGE_RECIPIENT_ENV} (an age public "
                "key, e.g. age1...). The matching private key is all that is "
                "needed to decrypt — keep it off this machine."
            )
        _run(
            ["age", "--encrypt", "--recipient", recipient,
             "--output", str(dest), str(path)],
            _subprocess_env(env), "age encrypt",
        )
    harden_permissions(dest)
    path.unlink()
    return dest


def decrypt_artifact(path: Path, dest: Path, env=None, mode: str | None = None) -> Path:
    """Decrypt ``path`` (``.enc``) into ``dest``; returns ``dest``.

    ``mode`` overrides the environment, which matters for restore: the scheme is
    whatever the *manifest* recorded, not whatever ``BACKUP_ENCRYPTION`` happens
    to be set to today (an operator may well have changed it since).
    """
    path, dest = Path(path), Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    mode = mode if mode is not None else encryption_mode(env)
    if mode == "openssl":
        if shutil.which("openssl") is None:
            raise RuntimeError("openssl is not installed/on PATH — cannot decrypt.")
        child_env = _subprocess_env(env, _passphrase_env(env))
        _run(_openssl_cmd("-d", path, dest), child_env, "openssl decrypt")
    elif mode == "age":
        # `mode`, not the environment: a restore follows the scheme the
        # *manifest* recorded. Reading BACKUP_ENCRYPTION here was a bug — an
        # age-encrypted backup restored on a host where that variable is unset
        # (or says 'openssl') fell through to the plaintext branch and copied
        # the ciphertext verbatim, i.e. a "successful" restore of garbage.
        env_map = os.environ if env is None else env
        identity = (env_map.get(AGE_IDENTITY_ENV) or "").strip()
        if not identity:
            raise RuntimeError(
                f"The backup was encrypted with age, so {AGE_IDENTITY_ENV} "
                "(path to the age identity file) is needed to decrypt it. "
                f"This is independent of today's {ENCRYPTION_ENV} setting."
            )
        _run(
            ["age", "--decrypt", "--identity", identity,
             "--output", str(dest), str(path)],
            _subprocess_env(env), "age decrypt",
        )
    else:
        shutil.copyfile(path, dest)
    harden_permissions(dest)
    return dest


def manifest_is_encrypted(manifest: dict) -> bool:
    """True when the manifest says its artifacts are encrypted."""
    return bool(manifest.get("encryption"))


@contextlib.contextmanager
def decrypted_backup(backup_dir: Path, manifest: dict, env=None):
    """Yield ``(db_path, media_path)`` as readable plaintext paths.

    For a plaintext backup these are the artifacts themselves. For an encrypted
    one they are decrypted into a private temporary directory that is removed
    on the way out, so plaintext never lingers next to the backup and never
    needs a caller-supplied scratch path.
    """
    backup_dir = Path(backup_dir)
    db_name = manifest.get("db_file")
    media_name = manifest.get("media_file")
    db_path = backup_dir / db_name if db_name else None
    media_path = backup_dir / media_name if media_name else None

    if not manifest_is_encrypted(manifest):
        yield db_path, media_path
        return

    import tempfile
    scheme = manifest.get("encryption") or ""
    # The manifest records a label such as 'openssl:aes-256-cbc:pbkdf2:600000';
    # the first token is the tool that produced the ciphertext.
    mode = scheme.split(":", 1)[0]
    if mode not in ENCRYPTION_LABELS:
        raise RuntimeError(
            f"Manifest records encryption {scheme!r}, which this version cannot "
            "decrypt. Restore with the tooling that produced the backup."
        )

    def plain_name(name: str) -> str:
        return name[: -len(ENCRYPTED_SUFFIX)] if name.endswith(ENCRYPTED_SUFFIX) else name

    with tempfile.TemporaryDirectory(prefix="sms-restore-") as tmp:
        work = Path(tmp)
        harden_permissions(work)
        plain_db = plain_media = None
        if db_path is not None:
            plain_db = decrypt_artifact(
                db_path, work / plain_name(db_name), env, mode=mode
            )
        if media_path is not None:
            plain_media = decrypt_artifact(
                media_path, work / plain_name(media_name), env, mode=mode
            )
        yield plain_db, plain_media


# --------------------------------------------------------------------------
# Independent off-box copy (S3-compatible object storage)
# --------------------------------------------------------------------------
def object_storage_config(env=None) -> dict | None:
    """The off-box backup bucket config, or ``None`` when not configured.

    Deliberately all-or-nothing: a bucket name with no credentials cannot
    upload, and half-enabling this would produce a nightly "backup succeeded"
    message with no off-box copy behind it. ``BACKUP_OBJECT_STORAGE_KEEP``
    bounds the remote copy count (default 30) so the bucket cannot grow
    forever.
    """
    env = os.environ if env is None else env

    def _get(name):
        return (env.get(name) or "").strip()

    bucket = _get(OBJECT_STORAGE_BUCKET_ENV)
    if not bucket:
        return None
    missing = [
        name for name, value in (
            (OBJECT_STORAGE_BUCKET_ENV, bucket),
            (OBJECT_STORAGE_ACCESS_KEY_ENV, _get(OBJECT_STORAGE_ACCESS_KEY_ENV)),
            (OBJECT_STORAGE_SECRET_KEY_ENV, _get(OBJECT_STORAGE_SECRET_KEY_ENV)),
        ) if not value
    ]
    if missing:
        raise RuntimeError(
            f"{OBJECT_STORAGE_BUCKET_ENV} is set but these are missing: "
            + ", ".join(missing)
            + ". Set all three, or unset the bucket to skip the off-box copy."
        )
    keep_raw = _get(OBJECT_STORAGE_KEEP_ENV) or "30"
    try:
        keep = max(1, int(keep_raw))
    except ValueError:
        raise RuntimeError(f"{OBJECT_STORAGE_KEEP_ENV}={keep_raw!r} is not an integer.")
    return {
        "bucket": bucket,
        "access_key": _get(OBJECT_STORAGE_ACCESS_KEY_ENV),
        "secret_key": _get(OBJECT_STORAGE_SECRET_KEY_ENV),
        "endpoint_url": _get(OBJECT_STORAGE_ENDPOINT_ENV) or None,
        "region": _get(OBJECT_STORAGE_REGION_ENV) or None,
        "prefix": _get(OBJECT_STORAGE_PREFIX_ENV).strip("/") or "backups",
        "keep": keep,
    }


def object_storage_client(config: dict):
    """A boto3 S3 client for the backup bucket (keys stay out of argv/logs)."""
    import boto3
    from botocore.config import Config as BotoConfig
    return boto3.client(
        "s3",
        endpoint_url=config["endpoint_url"],
        region_name=config["region"],
        aws_access_key_id=config["access_key"],
        aws_secret_access_key=config["secret_key"],
        config=BotoConfig(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def pack_backup_dir(backup_dir: Path, dest: Path) -> int:
    """Tar.gz a whole backup folder (artifacts + manifest) for upload."""
    backup_dir, dest = Path(backup_dir), Path(dest)
    count = 0
    with tarfile.open(dest, "w:gz") as tar:
        for path in sorted(backup_dir.rglob("*")):
            if path.is_file() and not path.is_symlink():
                tar.add(path, arcname=path.relative_to(backup_dir))
                count += 1
    return count


def list_remote_backups(client, config: dict) -> list[str]:
    """Remote backup keys under the configured prefix, oldest first by name."""
    keys: list[str] = []
    prefix = f"{config['prefix']}/"
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=config["bucket"], Prefix=prefix):
        for obj in page.get("Contents", []) or []:
            name = obj["Key"]
            # Only our own bundles: backups/<backup-...>.tar.gz
            if name[len(prefix):].startswith("backup-") and name.endswith(".tar.gz"):
                keys.append(name)
    return sorted(keys)


def prune_remote_backups(client, config: dict) -> list[str]:
    """Keep the newest ``config['keep']`` remote bundles; delete the rest."""
    keys = list_remote_backups(client, config)
    stale = keys[: max(0, len(keys) - config["keep"])]
    if not stale:
        return []
    # delete_objects takes <=1000 keys per call.
    for start in range(0, len(stale), 1000):
        chunk = stale[start:start + 1000]
        client.delete_objects(
            Bucket=config["bucket"],
            Delete={"Objects": [{"Key": k} for k in chunk], "Quiet": True},
        )
    return stale


def upload_backup(backup_dir: Path, config: dict | None = None, *,
                  client=None) -> dict:
    """Push an independent copy of ``backup_dir`` to the object-storage bucket.

    Packs the folder (artifacts + manifest) into one ``.tar.gz`` object so a
    restore fetches a single key, uploads it with server-side encryption
    (``AES256``) as a second layer under our own ``BACKUP_ENCRYPTION``, then
    prunes the remote set to ``BACKUP_OBJECT_STORAGE_KEEP``.

    Returns ``{'bucket', 'key', 'size_bytes', 'pruned': [...]}``. The bundle is
    staged in a private temp dir and deleted afterwards — the only durable copy
    is the one in the bucket.
    """
    config = config if config is not None else object_storage_config()
    if config is None:
        raise RuntimeError(
            "No object storage configured — set "
            f"{OBJECT_STORAGE_BUCKET_ENV}, {OBJECT_STORAGE_ACCESS_KEY_ENV} and "
            f"{OBJECT_STORAGE_SECRET_KEY_ENV} (see docs/BACKUP_RESTORE_GUIDE.md)."
        )
    client = client if client is not None else object_storage_client(config)
    backup_dir = Path(backup_dir)
    key = remote_key_for(backup_dir, config)

    import tempfile
    with tempfile.TemporaryDirectory(prefix="sms-backup-upload-") as tmp:
        stage = Path(tmp)
        harden_permissions(stage)
        bundle = stage / f"{backup_dir.name}.tar.gz"
        pack_backup_dir(backup_dir, bundle)
        harden_permissions(bundle)
        size = bundle.stat().st_size
        with open(bundle, "rb") as fh:
            client.upload_fileobj(
                fh, config["bucket"], key,
                ExtraArgs={"ServerSideEncryption": "AES256"},
            )
    pruned = prune_remote_backups(client, config)
    return {"bucket": config["bucket"], "key": key,
            "size_bytes": size, "pruned": pruned}


def remote_key_for(backup_dir: Path, config: dict) -> str:
    """The object key ``upload_backup`` uses for ``backup_dir``."""
    return f"{config['prefix']}/{Path(backup_dir).name}.tar.gz"


def _is_missing_object(exc) -> bool:
    """True for a clean S3 404, False for anything worth raising."""
    response = getattr(exc, "response", None) or {}
    code = str((response.get("Error") or {}).get("Code", ""))
    status = (response.get("ResponseMetadata") or {}).get("HTTPStatusCode")
    return code in ("404", "NoSuchKey", "NotFound") or status == 404


def head_remote_backup(client, config: dict, key: str) -> dict | None:
    """Metadata for one remote bundle, or ``None`` when the key is absent.

    Anything that is not a clean 404 — bad credentials, no network, a bucket
    that does not exist — is re-raised. Reporting "no off-box copy" for a
    misconfigured key would send an operator hunting in the wrong place, and
    would hide the fact that *nothing* has been uploaded for weeks.
    """
    try:
        resp = client.head_object(Bucket=config["bucket"], Key=key)
    except Exception as exc:  # noqa: BLE001 - classified just above
        if _is_missing_object(exc):
            return None
        raise
    return {
        "key": key,
        "size_bytes": resp.get("ContentLength"),
        "last_modified": resp.get("LastModified"),
        "server_side_encryption": resp.get("ServerSideEncryption"),
    }


def verify_remote_copy(client, config: dict, backup_dir: Path) -> dict:
    """Confirm the off-box bucket really holds ``backup_dir``.

    Returns the remote metadata; raises ``RuntimeError`` with an
    operator-readable reason when the copy is missing or empty. "The backup
    command exited 0" and "an independent copy exists off-box" are two
    different statements, and only this one proves the second.
    """
    key = remote_key_for(backup_dir, config)
    info = head_remote_backup(client, config, key)
    if info is None:
        raise RuntimeError(
            f"no off-box copy at s3://{config['bucket']}/{key} — the newest "
            "backup exists only on this machine"
        )
    if not info.get("size_bytes"):
        raise RuntimeError(
            f"off-box copy s3://{config['bucket']}/{key} is 0 bytes — the "
            "upload did not complete"
        )
    return info


def verify_unpacked_backup(folder: Path, manifest: dict, source: str = "") -> None:
    """Check an unpacked backup folder against its own manifest.

    Every recorded SHA-256 must match the bytes on disk. This is what turns a
    downloaded off-box bundle from "some tarball" back into "a backup we can
    restore from" — a truncated or corrupted object fails here instead of
    halfway through a restore.
    """
    folder = Path(folder)
    where = f" (from {source})" if source else ""
    problems = []
    for label, name_key, sha_key in (
        ("DB artifact", "db_file", "db_sha256"),
        ("media archive", "media_file", "media_sha256"),
    ):
        name = manifest.get(name_key)
        if not name:
            if label == "DB artifact":
                problems.append("manifest records no db_file")
            continue
        path = folder / name
        if not path.exists():
            problems.append(f"{label} '{name}' missing")
            continue
        expected = manifest.get(sha_key)
        if expected and sha256(path) != expected:
            problems.append(f"{label} '{name}' SHA-256 mismatch")
    if problems:
        raise RuntimeError(
            f"backup {folder.name}{where} failed its own manifest: "
            + "; ".join(problems)
        )


def download_remote_backup(client, config: dict, key: str, dest_root: Path,
                           *, force: bool = False) -> Path:
    """Fetch one off-box bundle and unpack it to ``dest_root/backup-<stamp>``.

    The object is downloaded into a private temp directory, validated member by
    member (no absolute paths, no traversal, no links), unpacked with ``0700`` /
    ``0600`` modes, and then checked against the manifest it carries. The
    returned folder is exactly what ``restore_backup --backup`` expects, so the
    recovery path from a lost host is: download, restore, done.
    """
    name = key.rsplit("/", 1)[-1]
    if not name.endswith(".tar.gz"):
        raise RuntimeError(f"'{key}' is not a backup bundle (.tar.gz).")
    folder_name = name[: -len(".tar.gz")]
    if (not folder_name.startswith("backup-") or "/" in folder_name
            or "\\" in folder_name or ".." in folder_name):
        raise RuntimeError(
            f"Refusing to unpack '{key}': expected a backup-<stamp>.tar.gz "
            "bundle name."
        )
    dest_root = Path(dest_root)
    dest_root.mkdir(parents=True, exist_ok=True)
    harden_permissions(dest_root)
    dest = dest_root / folder_name
    if dest.exists():
        if not force:
            raise RuntimeError(
                f"{dest} already exists — pass --force to replace it."
            )
        shutil.rmtree(dest)

    import tempfile
    with tempfile.TemporaryDirectory(prefix="sms-backup-fetch-") as tmp:
        stage = Path(tmp)
        harden_permissions(stage)
        bundle = stage / name
        with open(bundle, "wb") as fh:
            client.download_fileobj(config["bucket"], key, fh)
        harden_permissions(bundle)
        with open(bundle, "rb") as fh:
            safe_extract_tar_stream(fh, dest)

    harden_permissions(dest)
    for path in sorted(dest.rglob("*")):
        harden_permissions(path)
    manifest_path = dest / "manifest.json"
    if not manifest_path.exists():
        shutil.rmtree(dest, ignore_errors=True)
        raise RuntimeError(
            f"'{key}' unpacked without a manifest.json — it is not a bundle "
            "produced by backup_data."
        )
    try:
        verify_unpacked_backup(dest, load_manifest(manifest_path), source=key)
    except RuntimeError:
        # Leave the broken folder behind? No: a half-verified backup sitting in
        # the backup root could be picked by a later `restore_backup --latest`.
        shutil.rmtree(dest, ignore_errors=True)
        raise
    return dest


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


def _validate_tar_member(member, dest_dir: Path, dest_resolved: Path | None = None):
    """Raise unless ``member`` is safe to extract into ``dest_dir``.

    Cross-version safe (Python 3.11 here, so ``extractall(filter=...)`` is not
    available). Absolute paths, ``..`` traversal, and symlink/hardlink members
    are rejected outright so a tampered archive cannot write outside the
    intended directory.
    """
    dest_dir = Path(dest_dir)
    dest_resolved = dest_resolved or dest_dir.resolve()
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
    # Reject links — our own archives only ever store regular files.
    if member.issym() or member.islnk() or not member.isfile():
        raise RuntimeError(
            f"Refusing to extract '{member.name}' (non-regular file)"
        )


def safe_extract_tar(tar_path: Path, dest_dir: Path) -> int:
    """Extract a media tarball into ``dest_dir`` (validated member by member)."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_resolved = dest_dir.resolve()
    count = 0
    with tarfile.open(tar_path, "r:gz") as tar:
        for member in tar.getmembers():
            _validate_tar_member(member, dest_dir, dest_resolved)
            tar.extract(member, dest_dir)
            count += 1
    return count


def safe_extract_tar_stream(fileobj, dest_dir: Path) -> int:
    """Same as :func:`safe_extract_tar` for an already-open stream.

    Used for a bundle downloaded from the off-box bucket, so the bytes coming
    off the network are validated member by member before anything is written
    next to the local backups.
    """
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_resolved = dest_dir.resolve()
    count = 0
    # "r:gz" (seekable) rather than "r|gz": a downloaded bundle is a file we
    # already hold, and a seekable read lets us refuse the whole archive before
    # extracting any of it.
    with tarfile.open(fileobj=fileobj, mode="r:gz") as tar:
        for member in tar.getmembers():
            _validate_tar_member(member, dest_dir, dest_resolved)
        for member in tar.getmembers():
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
