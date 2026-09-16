"""Django management command: ``python manage.py backup_data``.

Creates a timestamped backup folder under ``./backups`` (or ``$P0B_BACKUP_ROOT``)
containing:

* a consistent database snapshot (sqlite online backup, or a ``pg_dump``
  custom-format dump for Postgres),
* a ``.tar.gz`` of ``MEDIA_ROOT`` (uploaded photos / files),
* a ``manifest.json`` (engine, artifact names, SHA-256, record-independent,
  **no credentials**).

Artifacts are written ``0600`` inside a ``0700`` folder (they are a full copy of
the school's PII). With ``BACKUP_ENCRYPTION=openssl`` (or ``age``) each artifact
is encrypted at rest and the plaintext is deleted. When the
``BACKUP_OBJECT_STORAGE_*`` variables are set, an independent copy is pushed to
that bucket (server-side encrypted, pruned to ``BACKUP_OBJECT_STORAGE_KEEP``) —
the copy that survives losing the app host.

Output (progress + the final backup folder) is written to stdout and the
command exits non-zero on failure — wrap it in ``scripts/backup.sh`` to
redirect stdout/stderr into a log file for monitoring. Then prunes old
backups, keeping ``--keep`` newest (default 7).

Usage::

    python manage.py backup_data                      # default: keep 7
    python manage.py backup_data --keep 30            # keep a month of daily
    python manage.py backup_data --media-dir /tmp/m   # for the disposable drill
    python manage.py backup_data --no-upload          # skip the off-box copy
    P0B_BACKUP_ROOT=/mnt/backups python manage.py backup_data
    BACKUP_ENCRYPTION=openssl BACKUP_PASSPHRASE_FILE=/etc/sms/backup.key \
        python manage.py backup_data
"""

from django.core.management.base import BaseCommand, CommandError

from students import backup_utils as bak


class Command(BaseCommand):
    help = "Create a consistent database + media backup and prune old ones."

    def add_arguments(self, parser):
        parser.add_argument(
            "--keep", type=int, default=7,
            help="Number of newest backup folders to keep (default 7).",
        )
        parser.add_argument(
            "--media-dir", default=None,
            help="Override MEDIA_ROOT (default: settings.MEDIA_ROOT).",
        )
        parser.add_argument(
            "--backup-root", default=None,
            help="Override the backup root (default: ./backups or $P0B_BACKUP_ROOT).",
        )
        parser.add_argument(
            "--no-upload", action="store_true",
            help="Skip the off-box object-storage copy even when it is configured.",
        )

    def handle(self, *args, **options):
        if options["backup_root"]:
            import os
            os.environ[bak.BACKUPS_ENV] = options["backup_root"]

        engine = bak.db_engine()
        self.stdout.write(f"Database engine: {engine}")
        self.stdout.write(f"Database: {bak.redacted_db_name()}")
        try:
            mode = bak.encryption_mode()
        except RuntimeError as exc:
            # Fail before writing anything: an operator who asked for encryption
            # must never end up with a plaintext backup and a green exit code.
            raise CommandError(str(exc))
        self.stdout.write(
            f"Encryption: {bak.ENCRYPTION_LABELS[mode] if mode != 'off' else 'off (plaintext)'}"
        )

        backup_dir, stamp = bak.make_backup_dir()
        self.stdout.write(f"Backup folder: {backup_dir}")

        try:
            self._build_backup(backup_dir, options, mode)
        except Exception:
            # A failed backup must not leave an empty folder that could be
            # mistaken for a good one (which a restore might then pick).
            self.stdout.write(
                self.style.ERROR(
                    f"Backup FAILED — removing incomplete folder {backup_dir}"
                )
            )
            import shutil
            shutil.rmtree(backup_dir, ignore_errors=True)
            raise

        removed = bak.prune_old_backups(options["keep"], backup_dir.parent)
        self.stdout.write(
            f"Retention: keeping {max(1, options['keep'])}; removed {len(removed)}."
        )
        for name in removed:
            self.stdout.write(f"  pruned {name}")

        self._upload_offbox(backup_dir, options)

        self.stdout.write(self.style.SUCCESS(
            f"Backup complete: {backup_dir}"
        ))

    def _upload_offbox(self, backup_dir, options):
        """Push the independent copy when a bucket is configured (optional)."""
        if options.get("no_upload"):
            self.stdout.write("Off-box copy: skipped (--no-upload).")
            return
        try:
            config = bak.object_storage_config()
        except RuntimeError as exc:
            # A half-configured bucket is a configuration error, not a warning:
            # "backup succeeded" with no off-box copy is the worst outcome.
            raise CommandError(str(exc))
        if config is None:
            self.stdout.write(
                "Off-box copy: not configured (set BACKUP_OBJECT_STORAGE_BUCKET / "
                "_ACCESS_KEY / _SECRET_KEY to enable)."
            )
            return
        try:
            result = bak.upload_backup(backup_dir, config)
        except Exception as exc:  # noqa: BLE001 - report, then fail loudly
            raise CommandError(
                f"Off-box upload to {config['bucket']} failed: {exc}. The local "
                f"backup at {backup_dir} is intact but is not off-box."
            )
        self.stdout.write(
            f"  Off-box copy: s3://{result['bucket']}/{result['key']} "
            f"({result['size_bytes']} bytes, server-side encrypted)"
        )
        for key in result["pruned"]:
            self.stdout.write(f"  pruned remote {key}")

    def _build_backup(self, backup_dir, options, mode="off"):
        """Write the DB + media artifacts and manifest into ``backup_dir``."""
        engine = bak.db_engine()
        db_size = None
        db_plain_sha = None
        if engine == "sqlite":
            src = bak.sqlite_path()
            if not src.exists():
                self.stdout.write(self.style.ERROR(
                    f"SQLite database file {src} does not exist — aborting."
                ))
                raise CommandError("No SQLite database to back up.")
            db_path = backup_dir / "db.sqlite3"
            db_size = bak.backup_sqlite(src, db_path)
            db_plain_sha = bak.sha256(db_path)
            self.stdout.write(f"  SQLite snapshot: {db_path.name} ({db_size} bytes)")
        elif engine == "postgres":
            db_path = backup_dir / "db.dump"
            db_size = bak.backup_postgres(db_path)
            db_plain_sha = bak.sha256(db_path)
            self.stdout.write(f"  Postgres dump:  {db_path.name} ({db_size} bytes)")
        else:
            raise CommandError("Unsupported database engine; aborting backup.")

        media_dir = options["media_dir"] if options["media_dir"] else None
        from django.conf import settings as dj_settings
        # Fall back to MEDIA_ROOT (from settings) when no override is given.
        if media_dir is None:
            media_dir = str(dj_settings.MEDIA_ROOT)
        media_path = backup_dir / "media.tar.gz"
        media_present, media_count = bak.archive_media(media_dir, media_path)
        media_plain_sha = bak.sha256(media_path)
        self.stdout.write(
            f"  Media archive:  {media_path.name} ({media_count} file(s))"
        )
        media_backend = bak.media_backend_label()
        if getattr(dj_settings, "MEDIA_IS_REMOTE", False) and not media_present:
            # USE_S3 moved uploads into a bucket, so the local media tree is
            # legitimately empty. Say so, otherwise a 0-file archive reads like
            # a broken backup and someone goes hunting for a bug.
            self.stdout.write(
                "  Note: media lives in object storage (USE_S3), not on this disk — "
                "the bucket (with versioning) is the copy of record for uploads. "
                f"Media backend recorded in the manifest: {media_backend}."
            )

        # ---- encryption at rest (optional) --------------------------------
        encryption_label = None
        if mode != "off":
            encryption_label = bak.ENCRYPTION_LABELS[mode]
            db_path = bak.encrypt_artifact(db_path, mode=mode)
            self.stdout.write(f"  Encrypted DB:     {db_path.name}")
            if media_present:
                media_path = bak.encrypt_artifact(media_path, mode=mode)
                self.stdout.write(f"  Encrypted media:  {media_path.name}")
            else:
                # Nothing worth encrypting; drop the empty archive so the
                # manifest cannot point at a file that is not there.
                media_path.unlink(missing_ok=True)

        bak.write_manifest(
            backup_dir / "manifest.json",
            engine=engine,
            db_file=db_path.name,
            media_file=media_path.name if media_present else None,
            media_count=media_count,
            # Digests of the bytes on disk — the ciphertext when encrypted.
            db_sha=bak.sha256(db_path),
            db_size=db_size,
            media_sha=bak.sha256(media_path) if media_present else None,
            encryption=encryption_label,
            # The plaintext digests are only meaningful when the on-disk bytes
            # are ciphertext; otherwise they would duplicate db_sha256.
            db_plain_sha=db_plain_sha if encryption_label else None,
            media_plain_sha=(
                media_plain_sha if (encryption_label and media_present) else None
            ),
            media_backend=media_backend,
        )
        bak.harden_permissions(backup_dir)
