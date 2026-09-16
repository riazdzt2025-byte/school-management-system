"""Django management command: ``python manage.py restore_backup ``.

Restores a backup folder created by ``backup_data`` into the **currently
configured** database (from ``settings``/``DATABASE_URL``) and media directory.

This is a genuinely destructive operation when pointed at the live database —
it overwrites the current data with the backup. It therefore requires
``--yes`` and prints exactly what will be touched first.

*For the disposable restore drill*, point the command at throwaway storage::

    DATABASE_URL=sqlite:///$PWD/.restore-drill/db.sqlite3 \
      python manage.py restore_backup --backup <backup-folder> \\
      --media-dir $PWD/.restore-drill/media --yes --verify

.. Note::
   Restoring into a disposable SQLite file is intended for drills only. This
   must never be described as completing a live / production backup.
"""
import os

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connections

from students import backup_utils as bak


class Command(BaseCommand):
    help = "Restore a backup folder into the configured DB + MEDIA_ROOT."

    def add_arguments(self, parser):
        parser.add_argument(
            "--backup", required=True, dest="backup", type=str,
            help="Backup folder name or path (e.g. backup-20260909T... or a path).",
        )
        parser.add_argument(
            "--media-dir", default=None,
            help="Media destination (default: settings.MEDIA_ROOT).",
        )
        parser.add_argument(
            "--yes", action="store_true",
            help="Confirm the (destructive) restore overwrite.",
        )
        parser.add_argument(
            "--verify", action="store_true",
            help="After restore, run record/file integrity checks.",
        )
        parser.add_argument(
            "--verify-only", action="store_true",
            help="Run integrity checks without modifying the database/media.",
        )

    def handle(self, *args, **options):
        backup_dir = bak.find_backup_dir(options["backup"])
        manifest_path = backup_dir / "manifest.json"
        if not manifest_path.exists():
            raise CommandError(f"No manifest.json in {backup_dir}")

        manifest = bak.load_manifest(manifest_path)
        engine = manifest["engine"]
        db_file = manifest.get("db_file")
        media_file = manifest.get("media_file")
        self.stdout.write(f"Backup:  {backup_dir}")
        self.stdout.write(f"Engine:  {engine} ({manifest.get('database')})")
        self.stdout.write(f"DB art:  {db_file}")
        self.stdout.write(f"Media:  {media_file or '(none)'}")

        # ---- verify-only path -------------------------------------------
        if options["verify_only"]:
            self._verify(backup_dir, manifest, options)
            return

        if not options["yes"]:
            raise CommandError(
                "Refusing to restore without --yes. This overwrites the "
                "currently configured database and media directory."
            )

        # Should never include credentials.
        if manifest.get("credentials_included") is not False:
            # format < 1 files are old; treat unknown conservatively.
            self.stderr.write(
                "Warning: manifest has no 'credentials_included' marker — "
                "continuing, but confirm it was produced by backup_data."
            )

        media_dir = options["media_dir"]
        from django.conf import settings as dj_settings
        remote_media = getattr(dj_settings, "MEDIA_IS_REMOTE", False)
        if media_file and media_dir is None and remote_media:
            # Extracting photos into MEDIA_ROOT while the app reads them from a
            # bucket would look like a successful restore and change nothing.
            raise CommandError(
                "Media for this deployment lives in object storage (USE_S3), so "
                "there is no local MEDIA_ROOT to extract into. Pass --media-dir "
                "<path> to extract to a staging directory, then push it with "
                "`manage.py copy_media_to_storage`; or restore the bucket's own "
                "versioned copy. See docs/BACKUP_RESTORE_GUIDE.md."
            )

        # What is about to be replaced — the operator should see the size of the
        # data they are overwriting before it is gone (read-only; a broken
        # database, which is a legitimate reason to restore, is not fatal here).
        self._report_current_state()

        if bak.manifest_is_encrypted(manifest):
            self.stdout.write(
                f"Backup is encrypted ({manifest.get('encryption')}) — decrypting "
                "into a private temporary directory."
            )

        with bak.decrypted_backup(backup_dir, manifest) as (db_path, media_path):
            if engine == "sqlite":
                if db_path is None or not db_path.exists():
                    raise CommandError(f"DB artifact missing: {backup_dir / db_file}")
                self._restore_sqlite(db_path)
            elif engine == "postgres":
                self._restore_postgres(db_path)
            else:
                raise CommandError(f"Unsupported engine in manifest: {engine}")

            if media_path is not None:
                if media_dir is None:
                    media_dir = str(dj_settings.MEDIA_ROOT)
                extracted = bak.safe_extract_tar(media_path, media_dir)
                self.stdout.write(f"Media restored to {media_dir} ({extracted} file(s))")

        self.stdout.write(self.style.SUCCESS("Restore complete."))

        if options["verify"]:
            self._verify(backup_dir, manifest, options)

    def _report_current_state(self):
        """Print the row counts currently in the target database, if readable."""
        try:
            from django.contrib.auth import get_user_model
            from students.models import Institution, Student
            self.stdout.write(
                "Current target contents (will be replaced): "
                f"{Institution.objects.count()} institution(s), "
                f"{Student.objects.count()} student(s), "
                f"{get_user_model().objects.count()} user(s)."
            )
        except Exception as exc:  # noqa: BLE001 - an unreadable DB is fine here
            self.stdout.write(
                f"Current target contents: unreadable ({exc.__class__.__name__}) — "
                "continuing."
            )

    # ---------------------------------------------------------------- helpers
    def _restore_sqlite(self, src):
        import shutil
        dest = bak.sqlite_path()
        self.stdout.write(f"Overwriting SQLite database at {dest}")
        connections.close_all()
        shutil.copyfile(src, dest)
        self.stdout.write(f"Restored {src.name} -> {dest}")

    def _restore_postgres(self, src):
        import shutil
        import subprocess
        if shutil.which("pg_restore") is None:
            raise CommandError(
                "pg_restore is not installed/PATH. Install the PostgreSQL "
                "client tools to restore a Postgres database."
            )
        from django.conf import settings as dj_settings
        db = dj_settings.DATABASES["default"]
        self.stdout.write(
            f"Restoring Postgres database {db.get('NAME', '')}@{db.get('HOST', '')}"
        )
        connections.close_all()
        cmd = [
            "pg_restore", "--clean", "--if-exists", "--no-owner", "--no-privileges",
            "--dbname", db.get("NAME", ""), str(src),
        ]
        proc = subprocess.run(
            cmd, env=bak.postgres_connect_env(), capture_output=True, text=True,
        )
        if proc.returncode != 0:
            raise CommandError(f"pg_restore failed: {proc.stderr.strip()}")
        self.stdout.write("Postgres restore complete.")

    def _verify(self, backup_dir, manifest, options):
        ok = True
        db_file = manifest.get("db_file")
        if db_file:
            artifact = backup_dir / db_file
            expected = manifest.get("db_sha256")
            if artifact.exists() and expected:
                actual = bak.sha256(artifact)
                if actual != expected:
                    self.stdout.write(self.style.ERROR(
                        f"DB artifact SHA mismatch: {artifact.name}"
                    ))
                    ok = False
                else:
                    self.stdout.write(f"DB artifact SHA-256 OK ({artifact.name})")
            ok = self._verify_plaintext_digests(backup_dir, manifest) and ok

        # Database/schema + record integrity.
        try:
            connections.close_all()
            call_command("migrate", check=True, interactive=False, verbosity=0)
            # A successful check means no pending migrations.
            self.stdout.write("migrate --check OK (schema matches the backup)")
            self._check_models()
        except Exception as exc:  # noqa: BLE001 - report all failure shapes
            self.stdout.write(self.style.ERROR(f"DB integrity check failed: {exc}"))
            ok = False

        # Media / file integrity.
        media_file = manifest.get("media_file")
        media_dir = options.get("media_dir")
        if media_file:
            from django.conf import settings as dj_settings
            if media_dir is None and getattr(dj_settings, "MEDIA_IS_REMOTE", False):
                # Photos are served from the bucket, so the file references have
                # to be checked against the storage backend, not the local disk.
                self._check_media_files(None)
            else:
                if media_dir is None:
                    media_dir = str(dj_settings.MEDIA_ROOT)
                self._check_media_files(media_dir)
        else:
            self.stdout.write("No media in this backup (skipping file check).")

        self.stdout.write(
            self.style.SUCCESS("Verification complete.") if ok
            else self.style.ERROR("Verification FAILED.")
        )
        if not ok:
            raise SystemExit(1)

    def _check_models(self):
        """Count a few sentinel rows and confirm the app registry works."""
        from django.contrib.auth import get_user_model
        from students.models import Institution, Student
        counts = {
            "Institutions": Institution.objects.count(),
            "Users": get_user_model().objects.count(),
            "Students": Student.objects.count(),
        }
        for label, count in counts.items():
            self.stdout.write(f"  {label}: {count}")

    def _verify_plaintext_digests(self, backup_dir, manifest):
        """For an encrypted backup, prove decryption yields the recorded bytes.

        The on-disk SHA above only proves the ciphertext is intact; the manifest
        also recorded the digest of the *plaintext*, so a wrong passphrase (which
        produces garbage rather than an error for some schemes) is caught here.
        """
        if not bak.manifest_is_encrypted(manifest):
            return True
        expected_db = manifest.get("db_plain_sha256")
        expected_media = manifest.get("media_plain_sha256")
        if not expected_db and not expected_media:
            return True
        try:
            with bak.decrypted_backup(backup_dir, manifest) as (db_path, media_path):
                if expected_db and db_path is not None:
                    actual = bak.sha256(db_path)
                    if actual != expected_db:
                        self.stdout.write(self.style.ERROR(
                            "Decrypted DB digest does not match the manifest "
                            "(wrong passphrase or corrupted artifact)."
                        ))
                        return False
                    self.stdout.write("Decrypted DB digest OK")
                if expected_media and media_path is not None:
                    actual = bak.sha256(media_path)
                    if actual != expected_media:
                        self.stdout.write(self.style.ERROR(
                            "Decrypted media digest does not match the manifest."
                        ))
                        return False
                    self.stdout.write("Decrypted media digest OK")
        except Exception as exc:  # noqa: BLE001 - any failure is a failure
            self.stdout.write(self.style.ERROR(f"Decryption failed: {exc}"))
            return False
        return True

    def _check_media_files(self, media_dir):
        """Verify every ImageField/FileField reference resolves to a file.

        ``media_dir=None`` means "ask the configured storage backend" — the right
        question when uploads live in an S3-compatible bucket, where joining onto
        a local path would report every single photo as missing.
        """
        from django.apps import apps
        missing = []
        total = 0
        storage = None
        if media_dir is None:
            from django.core.files.storage import default_storage
            storage = default_storage
        for model in apps.get_models():
            for field in model._meta.get_fields():
                f = getattr(field, "field", field)
                if f.__class__.__name__ in ("ImageField", "FileField"):
                    for obj in model.objects.all().iterator():
                        path = getattr(obj, f.name, None)
                        if not path:
                            continue
                        total += 1
                        if storage is not None:
                            found = storage.exists(str(path))
                        else:
                            found = os.path.isfile(os.path.join(media_dir, str(path)))
                        if not found:
                            missing.append(f"{model.__name__}.{f.name}: {path}")
        if missing:
            self.stdout.write(self.style.ERROR(
                f"{len(missing)} referenced file(s) missing (of {total}):"
            ))
            for line in missing[:20]:
                self.stdout.write(f"    {line}")
        else:
            self.stdout.write(
                f"Media references OK ({total} file reference(s) found"
                + (", checked against the storage backend)." if storage is not None
                   else ", checked on disk).")
            )
