"""Copy existing local uploads into the configured remote storage.

Turning on ``USE_S3`` fixes the future but not the past: photos already sitting
in ``MEDIA_ROOT`` on a container that is about to be replaced still need to be
moved into the bucket. This does that, one way, without touching the source
files, so it is safe to re-run — and safe to run from a one-off shell
(``render.sh`` / ``manage.py shell``) before the next deploy wipes the disk.

Only the key names are shared between the two storages: a file at
``<MEDIA_ROOT>/student_photos/x.jpg`` is written to ``<AWS_LOCATION>/
student_photos/x.jpg`` in the bucket, which is where ``photo.url`` already
points.
"""
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError


def iter_media_files(media_root: Path):
    """Regular files under ``media_root``, as ``(source_path, relative_name)``.

    Symlinks and directories are skipped — a symlink under an upload directory
    is a read-anything primitive, and this command runs with the app's own
    credentials against a bucket.
    """
    media_root = Path(media_root)
    if not media_root.exists():
        return
    for path in sorted(media_root.rglob("*")):
        if path.is_file() and not path.is_symlink():
            yield path, path.relative_to(media_root).as_posix()


class Command(BaseCommand):
    help = (
        "Copy files from MEDIA_ROOT into the configured media storage "
        "(object storage once USE_S3 is set). Existing, same-size files are "
        "skipped, so the command is idempotent."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--media-root",
            default=None,
            help="Source directory to read (defaults to settings.MEDIA_ROOT).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List what would be copied or skipped; write nothing.",
        )

    def handle(self, *args, **options):
        if not getattr(settings, "MEDIA_IS_REMOTE", False):
            raise CommandError(
                "Media storage is the local filesystem, so there is nothing to copy "
                "into. Set USE_S3=True (plus the AWS_* variables) to enable object "
                "storage — see docs/FREE_TIER_MEDIA_STORAGE.md."
            )

        media_root = Path(options["media_root"] or settings.MEDIA_ROOT)
        if not media_root.exists():
            self.stdout.write(f"No media directory at {media_root} — nothing to do.")
            return

        copied = skipped = failed = 0
        for source, name in iter_media_files(media_root):
            expected_size = source.stat().st_size
            try:
                already_there = default_storage.exists(name)
                same_size = already_there and default_storage.size(name) == expected_size
            except Exception as exc:  # network/permission — report and continue
                failed += 1
                self.stderr.write(self.style.ERROR(f"  ? {name}: cannot check storage ({exc})"))
                continue
            if same_size:
                if options["dry_run"]:
                    self.stdout.write(f"  = {name} (already in storage)")
                skipped += 1
                continue
            # Either missing (+) or present with a different size (~): a stale
            # copy. save() never overwrites — it hands out a random-suffixed
            # name instead — so delete first to keep the key the app expects.
            label = "~" if already_there else "+"
            self.stdout.write(
                f"  {label} {name} ({expected_size} bytes)"
                + ("  [dry run]" if options["dry_run"] else "")
            )
            if options["dry_run"]:
                continue
            try:
                with source.open("rb") as fh:
                    if already_there:
                        default_storage.delete(name)
                    default_storage.save(name, File(fh))
            except Exception as exc:
                failed += 1
                self.stderr.write(self.style.ERROR(f"  ! {name}: copy failed ({exc})"))
                continue
            copied += 1

        self.stdout.write(self.style.SUCCESS(
            f"Done: {copied} copied, {skipped} already present, {failed} failed."
        ))
        if failed:
            raise CommandError(f"{failed} file(s) did not make it into storage — re-run to retry.")
