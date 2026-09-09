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
