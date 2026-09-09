"""Django management command: ``python manage.py backup_data``.

Creates a timestamped backup folder under ``./backups`` (or ``$P0B_BACKUP_ROOT``)
containing:

* a consistent database snapshot (sqlite online backup, or a ``pg_dump``
  custom-format dump for Postgres),
* a ``.tar.gz`` of ``MEDIA_ROOT`` (uploaded photos / files),
* a ``manifest.json`` (engine, artifact names, SHA-256, record-independent,
  **no credentials**).

Output (progress + the final backup folder) is written to stdout and the
command exits non-zero on failure — wrap it in ``scripts/backup.sh`` to
redirect stdout/stderr into a log file for monitoring. Then prunes old
backups, keeping ``--keep`` newest (default 7).

Usage::

    python manage.py backup_data                      # default: keep 7
    python manage.py backup_data --keep 30            # keep a month of daily
    python manage.py backup_data --media-dir /tmp/m   # for the disposable drill
    P0B_BACKUP_ROOT=/mnt/backups python manage.py backup_data
"""
import json

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

    def handle(self, *args, **options):
        if options["backup_root"]:
            import os
            os.environ[bak.BACKUPS_ENV] = options["backup_root"]

        engine = bak.db_engine()
        self.stdout.write(f"Database engine: {engine}")
        self.stdout.write(f"Database: {bak.redacted_db_name()}")

        backup_dir, stamp = bak.make_backup_dir()
        self.stdout.write(f"Backup folder: {backup_dir}")

        try:
            self._build_backup(backup_dir, options)
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

        self.stdout.write(self.style.SUCCESS(
            f"Backup complete: {backup_dir}"
        ))

    def _build_backup(self, backup_dir, options):
        """Write the DB + media artifacts and manifest into ``backup_dir``."""
        engine = bak.db_engine()
        db_artifact, db_sha, db_size = None, None, None
        if engine == "sqlite":
            src = bak.sqlite_path()
            if not src.exists():
                self.stdout.write(self.style.ERROR(
                    f"SQLite database file {src} does not exist — aborting."
                ))
                raise CommandError("No SQLite database to back up.")
            dest = backup_dir / "db.sqlite3"
            db_size = bak.backup_sqlite(src, dest)
            db_artifact = dest.name
            db_sha = bak.sha256(dest)
            self.stdout.write(f"  SQLite snapshot: {dest.name} ({db_size} bytes)")
        elif engine == "postgres":
            dest = backup_dir / "db.dump"
            db_size = bak.backup_postgres(dest)
            db_artifact = dest.name
            db_sha = bak.sha256(dest)
            self.stdout.write(f"  Postgres dump:  {dest.name} ({db_size} bytes)")
        else:
            raise CommandError("Unsupported database engine; aborting backup.")

        media_dir = options["media_dir"] if options["media_dir"] else None
        # Fall back to MEDIA_ROOT (from settings) when no override is given.
        if media_dir is None:
            from django.conf import settings as dj_settings
            media_dir = str(dj_settings.MEDIA_ROOT)
        media_file = "media.tar.gz"
        media_present, media_count = bak.archive_media(media_dir, backup_dir / media_file)
        self.stdout.write(
            f"  Media archive:  {media_file} ({media_count} file(s))"
        )

        bak.write_manifest(
            backup_dir / "manifest.json",
            engine=engine,
            db_file=db_artifact,
            media_file=media_file if media_present else None,
            media_count=media_count,
            db_sha=db_sha,
            db_size=db_size,
        )
