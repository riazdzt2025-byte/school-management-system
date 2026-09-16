"""Django management command: ``python manage.py fetch_backup``.

Reads the **off-box** copy back — the half of the object-storage story that an
upload-only implementation leaves untested. A bucket nobody has ever downloaded
from is an assumption, not a backup.

* ``--list`` shows the bundles the bucket holds (key, size, last modified).
* ``--latest`` (or ``--key backups/backup-<stamp>.tar.gz``) downloads one
  bundle, validates and unpacks it, and checks it against the manifest it
  carries, leaving a normal ``backup-<stamp>/`` folder that
  ``restore_backup --backup`` can use unchanged.

Nothing here writes to the database or to media: fetching is read-only. The
restore itself stays a separate, explicit, ``--yes``-gated step.

Usage::

    python manage.py fetch_backup --list
    python manage.py fetch_backup --latest
    python manage.py fetch_backup --key backups/backup-20260916T020000Z.tar.gz
    python manage.py fetch_backup --latest --dest /mnt/scratch --force

    # then, into a DISPOSABLE target first (see docs/BACKUP_RESTORE_GUIDE.md):
    DATABASE_URL=sqlite:///$PWD/.restore-drill/db.sqlite3 \\
      python manage.py restore_backup --backup backup-20260916T020000Z \\
      --media-dir $PWD/.restore-drill/media --yes --verify

The bucket is reached only through ``BACKUP_OBJECT_STORAGE_*``; the keys stay in
the boto3 client and never appear in argv, the log, or a file name.
"""
import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from students import backup_utils as bak


class Command(BaseCommand):
    help = (
        "List or download backups from the off-box object-storage bucket "
        "(read-only; restoring stays a separate, explicit step)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--list", action="store_true",
            help="List the backup bundles the bucket holds and stop.",
        )
        parser.add_argument(
            "--latest", action="store_true",
            help="Download the newest bundle in the bucket.",
        )
        parser.add_argument(
            "--key", default=None,
            help="Download one specific object key (e.g. backups/backup-<stamp>.tar.gz).",
        )
        parser.add_argument(
            "--dest", default=None,
            help="Where to unpack (default: the local backup root, so "
                 "restore_backup finds it by name).",
        )
        parser.add_argument(
            "--force", action="store_true",
            help="Replace an existing local folder of the same name.",
        )
        parser.add_argument(
            "--backup-root", default=None,
            help="Override the backup root (default ./backups or $P0B_BACKUP_ROOT).",
        )

    def handle(self, *args, **options):
        if options["backup_root"]:
            os.environ[bak.BACKUPS_ENV] = options["backup_root"]
        try:
            config = bak.object_storage_config()
        except RuntimeError as exc:
            raise CommandError(str(exc))
        if config is None:
            raise CommandError(
                "No off-box bucket is configured, so there is nothing to fetch. "
                f"Set {bak.OBJECT_STORAGE_BUCKET_ENV}, "
                f"{bak.OBJECT_STORAGE_ACCESS_KEY_ENV} and "
                f"{bak.OBJECT_STORAGE_SECRET_KEY_ENV} "
                "(see docs/BACKUP_RESTORE_GUIDE.md §4.3)."
            )
        try:
            client = bak.object_storage_client(config)
        except ImportError as exc:
            raise CommandError(
                f"boto3 is needed to reach the bucket ({exc}). It is listed in "
                "requirements.txt, so this is an environment problem, not a "
                "configuration one."
            )
        bucket = config["bucket"]
        try:
            keys = bak.list_remote_backups(client, config)
        except Exception as exc:  # noqa: BLE001 - surface the real cause
            raise CommandError(f"Could not list s3://{bucket}: {exc}")

        if options["list"] or not (options["latest"] or options["key"]):
            self._list(keys, client, config, bucket)
            return

        if options["key"] and options["latest"]:
            raise CommandError("Pass either --key or --latest, not both.")
        if options["key"]:
            key = options["key"]
            if key not in keys:
                raise CommandError(
                    f"s3://{bucket}/{key} is not in the bucket. "
                    f"Available: {', '.join(keys[-5:]) or '(none)'}"
                )
        elif not keys:
            raise CommandError(
                f"s3://{bucket}/{config['prefix']}/ holds no backup bundles — "
                "has backup_data ever run with the off-box copy configured?"
            )
        else:
            key = keys[-1]

        dest_root = Path(options["dest"]) if options["dest"] else bak.backup_root()
        self.stdout.write(f"Downloading s3://{bucket}/{key}")
        try:
            folder = bak.download_remote_backup(
                client, config, key, dest_root, force=options["force"]
            )
        except RuntimeError as exc:
            raise CommandError(str(exc))
        manifest = bak.load_manifest(folder / "manifest.json")
        self.stdout.write(self.style.SUCCESS(
            f"Fetched and verified: {folder} "
            f"(engine={manifest.get('engine')}, "
            f"encryption={manifest.get('encryption') or 'off'}, "
            f"db={manifest.get('db_file')}, media={manifest.get('media_file') or 'none'})"
        ))
        self.stdout.write(
            "Next step is NOT automatic. Drill it into a disposable target first:\n"
            f"  DATABASE_URL=sqlite:///$PWD/.restore-drill/db.sqlite3 \\\n"
            f"    python manage.py restore_backup --backup {folder.name} \\\n"
            f"    --media-dir $PWD/.restore-drill/media --yes --verify"
        )

    def _list(self, keys, client, config, bucket):
        if not keys:
            self.stdout.write(
                f"s3://{bucket}/{config['prefix']}/ holds no backup bundles."
            )
            return
        self.stdout.write(f"{len(keys)} bundle(s) in s3://{bucket}/{config['prefix']}/:")
        for key in keys:
            try:
                info = bak.head_remote_backup(client, config, key) or {}
            except Exception as exc:  # noqa: BLE001 - one bad head is not fatal
                info = {"error": str(exc)}
            size = info.get("size_bytes")
            when = info.get("last_modified")
            enc = info.get("server_side_encryption") or "-"
            self.stdout.write(
                f"  {key}  "
                f"{(str(round(size / 1024, 1)) + ' KiB') if size else '?'}  "
                f"{when.isoformat() if hasattr(when, 'isoformat') else (when or '?')}  "
                f"sse={enc}"
                + (f"  ERROR {info['error']}" if info.get("error") else "")
            )
