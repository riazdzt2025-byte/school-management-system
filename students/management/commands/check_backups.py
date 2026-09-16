"""Django management command: ``python manage.py check_backups``.

Verifies the health of the most recent backup so any scheduler / uptime probe
(Uptime Robot, Healthchecks, GitHub Actions scheduled job, Render cron, a
cron+mail line) can be pointed at it for **failure reporting**. Exits 0 when
healthy, 1 when the newest backup is missing, corrupt, or stale.

Health rules (all must hold for the *newest* backup folder):

* a ``manifest.json`` exists and parsed,
* the recorded DB artifact exists and its SHA-256 matches ``db_sha256``,
* the recorded media archive (when there is one) exists and its SHA-256 matches
  ``media_sha256`` — a truncated photo tarball is a broken backup too,
* the backup is fresh (``--max-age-hours`` default 48; a scheduled backup that
  silently stopped producing new folders becomes stale and trips the check),
* the number of retained folders does not exceed ``--want-keep`` (above it means
  pruning is not running). Fewer than ``--want-keep`` on a fresh system is normal,
* encryption policy holds: when ``BACKUP_ENCRYPTION`` is set, the newest backup
  must actually be encrypted (a plaintext artifact is a policy failure),
* access control holds: no artifact and not the folder itself is readable by
  group/others — these files are a complete copy of the school's PII,
* with ``--check-remote``: the newest backup also exists in the off-box bucket
  and is not empty (an upload that quietly stopped is a silent loss of the only
  copy that survives losing this machine).

Usage::

    manage.py check_backups
    manage.py check_backups --max-age-hours 48 --want-keep 7
    manage.py check_backups --check-remote
    P0B_BACKUP_ROOT=/mnt/backups manage.py check_backups
"""
from pathlib import Path

from django.core.management.base import BaseCommand

from students import backup_utils as bak


class Command(BaseCommand):
    help = (
        "Verify the newest backup (manifest, DB SHA, freshness, retention). "
        "Exit 0 = healthy, non-zero = stale/corrupt. Point any alerting hook at it."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--max-age-hours", type=float, default=48,
            help="Max age (hours) of the newest backup before it's stale (default 48).",
        )
        parser.add_argument(
            "--want-keep", type=int, default=None,
            help="Expected number of retained backup folders (optional).",
        )
        parser.add_argument(
            "--backup-root", default=None,
            help="Override the backup root (default ./backups or $P0B_BACKUP_ROOT).",
        )
        parser.add_argument(
            "--skip-permission-check", action="store_true",
            help="Do not fail on world/group-readable backup files (not recommended).",
        )
        parser.add_argument(
            "--check-remote", action="store_true",
            help="Also require the newest backup to exist in the off-box bucket "
                 "(BACKUP_OBJECT_STORAGE_*). Without this, an upload that quietly "
                 "stopped still reports a healthy backup.",
        )

    def handle(self, *args, **options):
        if options["backup_root"]:
            import os
            os.environ[bak.BACKUPS_ENV] = options["backup_root"]

        root = bak.backup_root()
        if not root.exists():
            self.stdout.write(self.style.ERROR(f"No backup root at {root}"))
            raise SystemExit(1)

        folders = sorted(
            (d for d in root.iterdir() if d.is_dir() and d.name.startswith("backup-")),
            key=lambda d: d.name,
        )
        if not folders:
            self.stdout.write(self.style.ERROR(
                f"No backup folders found under {root}"
            ))
            raise SystemExit(1)

        newest = folders[-1]
        errors = []
        manifest_path = newest / "manifest.json"
        if not manifest_path.exists():
            errors.append(f"{newest.name}: missing manifest.json")
        else:
            manifest = bak.load_manifest(manifest_path)
            db_file = manifest.get("db_file")
            expected_sha = manifest.get("db_sha256")
            artifact = newest / db_file if db_file else None
            if not artifact or not artifact.exists():
                errors.append(f"{newest.name}: DB artifact '{db_file}' missing")
            elif expected_sha and bak.sha256(artifact) != expected_sha:
                errors.append(f"{newest.name}: DB artifact SHA mismatch")

            # The media archive is part of the backup too — a truncated photo
            # tarball is as much a broken backup as a truncated dump.
            media_file = manifest.get("media_file")
            media_sha = manifest.get("media_sha256")
            if media_file and media_sha:
                media_artifact = newest / media_file
                if not media_artifact.exists():
                    errors.append(f"{newest.name}: media artifact '{media_file}' missing")
                elif bak.sha256(media_artifact) != media_sha:
                    errors.append(f"{newest.name}: media artifact SHA mismatch")

            # Encryption compliance: if the deployment asked for encryption, a
            # plaintext backup is a policy failure even though it is "readable".
            try:
                required = bak.encryption_mode()
            except RuntimeError as exc:
                errors.append(f"encryption config invalid: {exc}")
                required = "off"
            if required != "off" and not bak.manifest_is_encrypted(manifest):
                errors.append(
                    f"{newest.name}: BACKUP_ENCRYPTION={required} but the backup is "
                    "plaintext (encryption is not being applied)"
                )

        # Access control: these files are the whole school's PII.
        if not options["skip_permission_check"]:
            offenders = [
                p.name for p in newest.rglob("*")
                if p.is_file() and bak.world_readable(p)
            ]
            if bak.world_readable(newest):
                offenders.insert(0, newest.name + "/")
            if offenders:
                errors.append(
                    f"{newest.name}: world/group-readable ({', '.join(offenders[:5])}) — "
                    "chmod 600 the artifacts and 700 the folder"
                )

        # Freshness
        from django.utils import timezone
        import datetime
        try:
            raw = newest.name[len("backup-"):]
            created = datetime.datetime.strptime(raw.split("-")[0], "%Y%m%dT%H%M%SZ")
            created = created.replace(tzinfo=datetime.timezone.utc)
            age_hours = (timezone.now() - created).total_seconds() / 3600.0
            if age_hours > options["max_age_hours"]:
                errors.append(
                    f"{newest.name}: stale ({age_hours:.1f}h > {options['max_age_hours']}h)"
                )
        except ValueError:
            errors.append(f"{newest.name}: cannot parse timestamp")

        if options["want_keep"] is not None:
            # A healthy prune must keep the newest N; if we ever have MORE than
            # N folders, pruning is broken (not running / failing). Fewer than N
            # on a fresh system is normal ramp-up and is not an error.
            if len(folders) > options["want_keep"]:
                errors.append(
                    f"retention broken: {len(folders)} > {options['want_keep']} folders "
                    "(pruning not keeping up)"
                )

        # Off-box copy (only when asked for: it is a network call).
        remote_line = None
        if options["check_remote"]:
            remote_line, remote_errors = self._check_remote(newest)
            errors.extend(remote_errors)

        if errors:
            for e in errors:
                self.stdout.write(self.style.ERROR(f"  {e}"))
            self.stdout.write(self.style.ERROR(
                "check_backups FAILED (see above)."
            ))
            raise SystemExit(1)

        count_col = sum(1 for d in folders if (d / "manifest.json").exists())
        newest_manifest = bak.load_manifest(newest / "manifest.json")
        enc = newest_manifest.get("encryption") or "off"
        self.stdout.write(self.style.SUCCESS(
            f"check_backups OK: newest backup {newest.name} (engine="
            f"{newest_manifest.get('engine')}, encryption={enc}, "
            f"{count_col} manifest(s), {len(folders)} folder(s))."
        ))
        if remote_line:
            self.stdout.write(self.style.SUCCESS(f"  {remote_line}"))

    def _check_remote(self, newest):
        """Require an off-box copy of ``newest``; return (ok_line, errors).

        An upload that quietly stopped (rotated key, renamed bucket, expired
        credential) leaves a perfectly healthy-looking local backup, which is
        exactly the failure this gate exists to catch. A half-configured bucket
        is an error rather than a skip: asking for the gate and not getting it
        must not read as "all good".
        """
        try:
            config = bak.object_storage_config()
        except RuntimeError as exc:
            return None, [f"--check-remote: {exc}"]
        if config is None:
            return None, [
                "--check-remote was requested but no off-box bucket is "
                f"configured (set {bak.OBJECT_STORAGE_BUCKET_ENV}, "
                f"{bak.OBJECT_STORAGE_ACCESS_KEY_ENV} and "
                f"{bak.OBJECT_STORAGE_SECRET_KEY_ENV}, or drop the flag)"
            ]
        try:
            client = bak.object_storage_client(config)
            info = bak.verify_remote_copy(client, config, newest)
        except Exception as exc:  # noqa: BLE001 - any failure is a failure
            return None, [f"--check-remote: {exc}"]
        size = info.get("size_bytes")
        when = info.get("last_modified")
        return (
            f"off-box copy OK: s3://{config['bucket']}/{info['key']} "
            f"({size} bytes"
            + (f", uploaded {when.isoformat()}" if hasattr(when, "isoformat") else "")
            + ")",
            [],
        )
