"""Regression tests for the backup / restore tooling (P0-8).

Guards the media archive round-trip, the cross-version-safe tar extraction, the
credential-free manifest, retention pruning, and the SQLite snapshot — all the
pieces a production backup depends on. Uses only temporary files.
"""
import io
import json
import os
import sqlite3
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase

from students import backup_utils as bak


class MediaRoundTripTests(SimpleTestCase):
    def test_archive_then_extract_preserves_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "media"
            (src / "student_photos").mkdir(parents=True)
            payload = b"\x89PNG\r\n\x1a\nfake-image-bytes"
            (src / "student_photos" / "photo.png").write_bytes(payload)

            tar_path = Path(tmp) / "media.tar.gz"
            present, count = bak.archive_media(src, tar_path)
            self.assertTrue(present)
            self.assertEqual(count, 1)

            dest = Path(tmp) / "restored"
            extracted = bak.safe_extract_tar(tar_path, dest)
            self.assertEqual(extracted, 1)
            restored = dest / "student_photos" / "photo.png"
            self.assertEqual(restored.read_bytes(), payload)

    def test_archive_skips_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "media"
            src.mkdir()
            (src / "real.txt").write_text("real")
            (src / "link.txt").symlink_to(src / "real.txt")

            tar_path = Path(tmp) / "media.tar.gz"
            present, count = bak.archive_media(src, tar_path)
            # Only the regular file is archived; the symlink is skipped.
            self.assertEqual(count, 1)

            with tarfile.open(tar_path, "r:gz") as tar:
                names = tar.getnames()
            self.assertNotIn("link.txt", names)
            self.assertIn("real.txt", names)


class SafeExtractTests(SimpleTestCase):
    def _tar_with_member(self, name, data=b"x"):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        buffer.seek(0)
        return buffer

    def test_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            tar_path = Path(tmp) / "bad.tar.gz"
            tar_path.write_bytes(self._tar_with_member("../../evil.txt").read())
            with self.assertRaises(RuntimeError):
                bak.safe_extract_tar(tar_path, Path(tmp) / "out")

    def test_rejects_absolute_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            tar_path = Path(tmp) / "bad.tar.gz"
            tar_path.write_bytes(self._tar_with_member("/etc/passwd").read())
            with self.assertRaises(RuntimeError):
                bak.safe_extract_tar(tar_path, Path(tmp) / "out")

    def test_rejects_symlink_member(self):
        with tempfile.TemporaryDirectory() as tmp:
            tar_path = Path(tmp) / "bad.tar.gz"
            with tarfile.open(tar_path, "w:gz") as tar:
                info = tarfile.TarInfo("link")
                info.type = tarfile.SYMTYPE
                info.linkname = "/etc/passwd"
                tar.addfile(info)
            with self.assertRaises(RuntimeError):
                bak.safe_extract_tar(tar_path, Path(tmp) / "out")


class ManifestTests(SimpleTestCase):
    def test_manifest_never_contains_credentials(self):
        # Even when the configured DB has a password, the manifest must not.
        fake_config = {
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": "sms_prod",
                "USER": "sms_user",
                "PASSWORD": "SuperSecretPass123",
                "HOST": "db.internal",
                "PORT": "5432",
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "manifest.json"
            with mock.patch.dict("django.conf.settings.DATABASES", fake_config):
                bak.write_manifest(
                    manifest_path,
                    engine="postgres",
                    db_file="db.dump",
                    media_file="media.tar.gz",
                    media_count=3,
                    db_sha="abc123",
                    db_size=1024,
                )
            raw = manifest_path.read_text()
            self.assertNotIn("SuperSecretPass123", raw)
            self.assertNotIn("password", raw.lower())
            data = json.loads(raw)
            self.assertFalse(data["credentials_included"])
            # The redacted DB label carries neither password nor DSN.
            self.assertNotIn("postgres://", data["database"])


class RetentionTests(SimpleTestCase):
    def test_prune_keeps_newest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ["backup-20260101T000000Z", "backup-20260102T000000Z",
                         "backup-20260103T000000Z", "backup-20260104T000000Z"]:
                (root / name).mkdir()
            (root / "unrelated").mkdir()
            removed = bak.prune_old_backups(keep=2, backup_root_dir=root)
            self.assertEqual(len(removed), 2)
            self.assertEqual(len(list(root.glob("backup-*"))), 2)


class SqliteSnapshotTests(SimpleTestCase):
    def test_sqlite_snapshot_is_consistent_and_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src.sqlite3"
            conn = sqlite3.connect(src)
            conn.executescript(
                "CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT);"
                "INSERT INTO t (v) VALUES ('alpha'), ('beta');"
            )
            conn.commit()
            conn.close()

            dest = Path(tmp) / "snap.sqlite3"
            bak.backup_sqlite(src, dest)
            self.assertTrue(dest.exists())

            check = sqlite3.connect(dest)
            rows = check.execute("SELECT v FROM t ORDER BY v").fetchall()
            check.close()
            self.assertEqual(rows, [("alpha",), ("beta",)])


class CheckBackupsCommandTests(SimpleTestCase):
    """The `check_backups` failure-reporting hook (exit 0 healthy / non-zero else)."""

    def _make_backup(self, root, date_str=None, db_bytes=b"real-db"):
        if date_str is None:
            import datetime
            date_str = datetime.datetime.now(
                datetime.timezone.utc
            ).strftime("%Y%m%dT%H%M%SZ")
        (root / f"backup-{date_str}").mkdir(parents=True)
        folder = root / f"backup-{date_str}"
        (folder / "db.sqlite3").write_bytes(db_bytes)
        import hashlib
        sha = hashlib.sha256(db_bytes).hexdigest()
        import json
        (folder / "manifest.json").write_text(json.dumps({
            "engine": "sqlite", "db_file": "db.sqlite3", "db_sha256": sha,
            "media_file": None, "media_file_count": 0, "credentials_included": False,
        }))
        return folder

    def _run(self, *args):
        from django.core.management import call_command
        try:
            call_command("check_backups", "--backup-root", str(args[0]),
                         *args[1:], verbosity=0)
            return 0  # healthy: no SystemExit raised
        except SystemExit as exc:
            return exc.code

    def test_healthy_returns_0(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._make_backup(Path(tmp))
            code = self._run(Path(tmp))
            self.assertEqual(code, 0)

    def test_stale_returns_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._make_backup(Path(tmp))
            code = self._run(Path(tmp), "--max-age-hours", "0")
            self.assertNotEqual(code, 0)

    def test_corrupt_sha_returns_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = self._make_backup(Path(tmp), db_bytes=b"real-db")
            # Corrupt the DB artifact after the manifest recorded its SHA.
            (folder / "db.sqlite3").write_bytes(b"tampered")
            code = self._run(Path(tmp))
            self.assertNotEqual(code, 0)

    def test_no_backup_root_returns_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "nothing"
            empty.mkdir()
            code = self._run(empty)
            self.assertNotEqual(code, 0)

    def test_fewer_than_want_keep_is_still_healthy(self):
        # A single fresh backup does NOT trip `--want-keep` (ramp-up is normal).
        with tempfile.TemporaryDirectory() as tmp:
            self._make_backup(Path(tmp))
            code = self._run(Path(tmp), "--want-keep", "7")
            self.assertEqual(code, 0)

    def test_more_than_want_keep_is_broken_retention(self):
        # More retention folders than requested means pruning is not running.
        with tempfile.TemporaryDirectory() as tmp:
            self._make_backup(Path(tmp), db_bytes=b"b1")
            self._make_backup(Path(tmp), date_str="20260102T000000Z", db_bytes=b"b2")
            code = self._run(Path(tmp), "--want-keep", "1")
            self.assertNotEqual(code, 0)
