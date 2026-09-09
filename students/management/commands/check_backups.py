"""Django management command: ``python manage.py check_backups``.

Verifies the health of the most recent backup so any scheduler / uptime probe
(Uptime Robot, Healthchecks, GitHub Actions scheduled job, Render cron, a
cron+mail line) can be pointed at it for **failure reporting**. Exits 0 when
healthy, 1 when the newest backup is missing, corrupt, or stale.

Health rules (all must hold for the *newest* backup folder):

* a ``manifest.json`` exists and parsed,
* the recorded DB artifact exists and its SHA-256 matches ``db_sha256``,
* the backup is fresh (``--max-age-hours`` default 48; a scheduled backup that
  silently stopped producing new folders becomes stale and trips the check),
* the number of retained folders does not exceed ``--want-keep`` (above it means
  pruning is not running). Fewer than ``--want-keep`` on a fresh system is normal.

Usage::

    manage.py check_backups
    manage.py check_backups --max-age-hours 48 --want-keep 7
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

        if errors:
            for e in errors:
                self.stdout.write(self.style.ERROR(f"  {e}"))
            self.stdout.write(self.style.ERROR(
                "check_backups FAILED (see above)."
            ))
            raise SystemExit(1)

        count_col = sum(1 for d in folders if (d / "manifest.json").exists())
        self.stdout.write(self.style.SUCCESS(
            f"check_backups OK: newest backup {newest.name} (engine="
            f"{bak.load_manifest(newest / 'manifest.json').get('engine')}, "
            f"{count_col} manifest(s), {len(folders)} folder(s))."
        ))
