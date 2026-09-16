"""Regression tests for the backup / restore tooling (P0-8).

Guards the media archive round-trip, the cross-version-safe tar extraction, the
credential-free manifest, retention pruning, the SQLite snapshot, encryption at
rest, file-mode hardening and the off-box object-storage copy — all the pieces a
production backup depends on. Uses only temporary files and a stubbed S3 client;
nothing here touches a real database, the real MEDIA_ROOT, or a real bucket.
"""
import io
import json
import os
import shutil
import sqlite3
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase, override_settings

from students import backup_utils as bak
from students import checks

HAS_OPENSSL = shutil.which("openssl") is not None
needs_openssl = unittest.skipUnless(HAS_OPENSSL, "openssl not on PATH")

# A passphrase used only inside these tests, for throwaway files in temp dirs.
TEST_PASSPHRASE = "unit-test-only-passphrase"


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

    def _make_backup(self, root, date_str=None, db_bytes=b"real-db",
                     media_bytes=None, extra_manifest=None, mode=0o600):
        if date_str is None:
            import datetime
            date_str = datetime.datetime.now(
                datetime.timezone.utc
            ).strftime("%Y%m%dT%H%M%SZ")
        (root / f"backup-{date_str}").mkdir(parents=True)
        folder = root / f"backup-{date_str}"
        (folder / "db.sqlite3").write_bytes(db_bytes)
        import hashlib
        manifest = {
            "engine": "sqlite", "db_file": "db.sqlite3",
            "db_sha256": hashlib.sha256(db_bytes).hexdigest(),
            "media_file": None, "media_file_count": 0,
            "credentials_included": False,
        }
        if media_bytes is not None:
            (folder / "media.tar.gz").write_bytes(media_bytes)
            manifest["media_file"] = "media.tar.gz"
            manifest["media_sha256"] = hashlib.sha256(media_bytes).hexdigest()
        manifest.update(extra_manifest or {})
        (folder / "manifest.json").write_text(json.dumps(manifest))
        for path in folder.rglob("*"):
            path.chmod(mode if path.is_file() else 0o700)
        folder.chmod(0o700)
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


class PermissionHardeningTests(SimpleTestCase):
    """A backup is the whole school's PII: it must not be world-readable."""

    def test_file_becomes_0600_and_dir_0700(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "backup-x"
            folder.mkdir()
            artifact = folder / "db.sqlite3"
            artifact.write_bytes(b"data")
            artifact.chmod(0o644)
            folder.chmod(0o755)

            bak.harden_permissions(artifact)
            bak.harden_permissions(folder)

            self.assertEqual(artifact.stat().st_mode & 0o777, 0o600)
            self.assertEqual(folder.stat().st_mode & 0o777, 0o700)

    def test_world_readable_detection(self):
        if os.name != "posix":
            self.skipTest("POSIX permission bits only")
        with tempfile.TemporaryDirectory() as tmp:
            private = Path(tmp) / "private"
            private.write_bytes(b"x")
            private.chmod(0o600)
            leaked = Path(tmp) / "leaked"
            leaked.write_bytes(b"x")
            leaked.chmod(0o644)
            self.assertFalse(bak.world_readable(private))
            self.assertTrue(bak.world_readable(leaked))

    def test_new_backup_folder_is_private_from_creation(self):
        if os.name != "posix":
            self.skipTest("POSIX permission bits only")
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {bak.BACKUPS_ENV: str(tmp)}):
                folder, _ = bak.make_backup_dir()
            self.assertEqual(folder.stat().st_mode & 0o777, 0o700)

    def test_manifest_file_is_private(self):
        if os.name != "posix":
            self.skipTest("POSIX permission bits only")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            bak.write_manifest(
                path, engine="sqlite", db_file="db.sqlite3", media_file=None,
                media_count=0, db_sha="x", db_size=1,
            )
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)


@needs_openssl
class EncryptionAtRestTests(SimpleTestCase):
    """BACKUP_ENCRYPTION=openssl must round-trip and never leave plaintext."""

    ENV = {bak.ENCRYPTION_ENV: "openssl", bak.PASSPHRASE_ENV: TEST_PASSPHRASE}

    def _artifact(self, tmp, payload=b"sqlite-format-3\x00payload"):
        path = Path(tmp) / "db.sqlite3"
        path.write_bytes(payload)
        return path, payload

    def test_round_trip_returns_the_original_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, payload = self._artifact(tmp)
            enc = bak.encrypt_artifact(path, env=self.ENV)
            self.assertTrue(enc.name.endswith(bak.ENCRYPTED_SUFFIX))
            self.assertNotEqual(enc.read_bytes(), payload)
            out = bak.decrypt_artifact(enc, Path(tmp) / "plain.sqlite3", env=self.ENV)
            self.assertEqual(out.read_bytes(), payload)

    def test_plaintext_is_deleted_after_encryption(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, _ = self._artifact(tmp)
            bak.encrypt_artifact(path, env=self.ENV)
            self.assertFalse(path.exists(), "plaintext artifact left on disk")

    def test_ciphertext_is_private(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, _ = self._artifact(tmp)
            enc = bak.encrypt_artifact(path, env=self.ENV)
            self.assertEqual(enc.stat().st_mode & 0o777, 0o600)

    def test_wrong_passphrase_cannot_decrypt(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, _ = self._artifact(tmp)
            enc = bak.encrypt_artifact(path, env=self.ENV)
            wrong = {bak.ENCRYPTION_ENV: "openssl",
                     bak.PASSPHRASE_ENV: "not-the-passphrase"}
            with self.assertRaises(RuntimeError):
                bak.decrypt_artifact(enc, Path(tmp) / "out", env=wrong)

    def test_missing_passphrase_names_the_variables(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, _ = self._artifact(tmp)
            env = {bak.ENCRYPTION_ENV: "openssl"}
            with self.assertRaises(RuntimeError) as ctx:
                bak.encrypt_artifact(path, env=env)
            self.assertIn(bak.PASSPHRASE_FILE_ENV, str(ctx.exception))
            self.assertIn(bak.PASSPHRASE_ENV, str(ctx.exception))

    def test_passphrase_file_is_used_and_never_printed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, payload = self._artifact(tmp)
            key = Path(tmp) / "backup.key"
            key.write_text(TEST_PASSPHRASE + "\n")
            key.chmod(0o600)
            env = {bak.ENCRYPTION_ENV: "openssl",
                   bak.PASSPHRASE_FILE_ENV: str(key)}
            enc = bak.encrypt_artifact(path, env=env)
            out = bak.decrypt_artifact(enc, Path(tmp) / "out", env=env)
            self.assertEqual(out.read_bytes(), payload)

    def test_unknown_scheme_is_rejected_not_silently_ignored(self):
        with self.assertRaises(RuntimeError):
            bak.encryption_mode({bak.ENCRYPTION_ENV: "rot13"})

    def test_off_is_the_default(self):
        self.assertEqual(bak.encryption_mode({}), "off")
        for value in ("", "off", "none", "false", "0"):
            self.assertEqual(bak.encryption_mode({bak.ENCRYPTION_ENV: value}), "off")

    def test_missing_tool_is_an_error_not_a_plaintext_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, _ = self._artifact(tmp)
            env = {bak.ENCRYPTION_ENV: "age", bak.AGE_RECIPIENT_ENV: "age1xxx"}
            with mock.patch("shutil.which", return_value=None):
                with self.assertRaises(RuntimeError):
                    bak.encrypt_artifact(path, env=env)
            self.assertTrue(path.exists(), "artifact should be untouched on failure")


class DecryptedBackupTests(SimpleTestCase):
    """`decrypted_backup` is what a restore reads, encrypted or not."""

    def test_plaintext_manifest_yields_the_artifacts_themselves(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "db.sqlite3").write_bytes(b"db")
            (folder / "media.tar.gz").write_bytes(b"media")
            manifest = {"db_file": "db.sqlite3", "media_file": "media.tar.gz",
                        "encryption": None}
            with bak.decrypted_backup(folder, manifest) as (db, media):
                self.assertEqual(db, folder / "db.sqlite3")
                self.assertEqual(media, folder / "media.tar.gz")

    def test_encrypted_manifest_yields_the_original_bytes(self):
        env = {bak.ENCRYPTION_ENV: "openssl", bak.PASSPHRASE_ENV: TEST_PASSPHRASE}
        if not HAS_OPENSSL:
            self.skipTest("openssl not on PATH")
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "db.sqlite3").write_bytes(b"db-bytes")
            (folder / "media.tar.gz").write_bytes(b"media-bytes")
            db_enc = bak.encrypt_artifact(folder / "db.sqlite3", env=env)
            media_enc = bak.encrypt_artifact(folder / "media.tar.gz", env=env)
            manifest = {
                "db_file": db_enc.name, "media_file": media_enc.name,
                "encryption": bak.ENCRYPTION_LABELS["openssl"],
            }
            with mock.patch.dict(os.environ, env):
                with bak.decrypted_backup(folder, manifest) as (db, media):
                    self.assertEqual(db.read_bytes(), b"db-bytes")
                    self.assertEqual(media.read_bytes(), b"media-bytes")
                    # The plaintext lives in a temp dir, not beside the backup.
                    self.assertNotIn(str(folder), str(db))
            self.assertFalse((folder / "db.sqlite3").exists())

    def test_unknown_scheme_label_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            manifest = {"db_file": "db.sqlite3.enc", "media_file": None,
                        "encryption": "rot13:whatever"}
            with self.assertRaises(RuntimeError):
                with bak.decrypted_backup(folder, manifest):
                    pass


class ManifestEncryptionFieldsTests(SimpleTestCase):
    def test_records_scheme_and_plain_digest_without_the_passphrase(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            with mock.patch.dict(os.environ,
                                 {bak.ENCRYPTION_ENV: "openssl",
                                  bak.PASSPHRASE_ENV: TEST_PASSPHRASE}):
                bak.write_manifest(
                    path, engine="sqlite", db_file="db.sqlite3.enc",
                    media_file="media.tar.gz.enc", media_count=2,
                    db_sha="cipher-sha", db_size=10,
                    encryption=bak.ENCRYPTION_LABELS["openssl"],
                    db_plain_sha="plain-sha", media_plain_sha="plain-media-sha",
                    media_sha="cipher-media-sha", media_backend="filesystem",
                )
            data = json.loads(path.read_text())
            self.assertEqual(data["format"], 2)
            self.assertEqual(data["encryption"], "openssl:aes-256-cbc:pbkdf2:600000")
            self.assertEqual(data["db_plain_sha256"], "plain-sha")
            self.assertEqual(data["media_sha256"], "cipher-media-sha")
            self.assertEqual(data["media_backend"], "filesystem")
            self.assertNotIn(TEST_PASSPHRASE, path.read_text())
            self.assertFalse(data["credentials_included"])

    def test_plaintext_manifest_has_no_encryption_label(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            bak.write_manifest(
                path, engine="sqlite", db_file="db.sqlite3", media_file=None,
                media_count=0, db_sha="sha", db_size=1,
            )
            data = json.loads(path.read_text())
            self.assertIsNone(data["encryption"])
            self.assertFalse(bak.manifest_is_encrypted(data))


class ObjectStorageConfigTests(SimpleTestCase):
    """The off-box copy is opt-in, and half-configured means an error."""

    def test_unset_bucket_means_no_offbox_copy(self):
        self.assertIsNone(bak.object_storage_config({}))

    def test_partial_config_names_every_missing_variable(self):
        env = {bak.OBJECT_STORAGE_BUCKET_ENV: "sms-backups"}
        with self.assertRaises(RuntimeError) as ctx:
            bak.object_storage_config(env)
        message = str(ctx.exception)
        self.assertIn(bak.OBJECT_STORAGE_ACCESS_KEY_ENV, message)
        self.assertIn(bak.OBJECT_STORAGE_SECRET_KEY_ENV, message)

    def test_only_the_absent_variable_is_named(self):
        env = {bak.OBJECT_STORAGE_BUCKET_ENV: "sms-backups",
               bak.OBJECT_STORAGE_ACCESS_KEY_ENV: "AKIA"}
        with self.assertRaises(RuntimeError) as ctx:
            bak.object_storage_config(env)
        message = str(ctx.exception)
        self.assertIn(bak.OBJECT_STORAGE_SECRET_KEY_ENV, message)
        self.assertNotIn(bak.OBJECT_STORAGE_ACCESS_KEY_ENV, message)

    def test_full_config_defaults_prefix_and_keep(self):
        config = bak.object_storage_config({
            bak.OBJECT_STORAGE_BUCKET_ENV: "sms-backups",
            bak.OBJECT_STORAGE_ACCESS_KEY_ENV: "AKIA",
            bak.OBJECT_STORAGE_SECRET_KEY_ENV: "secret",
            bak.OBJECT_STORAGE_ENDPOINT_ENV: "https://acct.r2.cloudflarestorage.com",
            bak.OBJECT_STORAGE_REGION_ENV: "auto",
        })
        self.assertEqual(config["prefix"], "backups")
        self.assertEqual(config["keep"], 30)
        self.assertEqual(config["endpoint_url"],
                         "https://acct.r2.cloudflarestorage.com")

    def test_bad_keep_value_is_rejected(self):
        env = {bak.OBJECT_STORAGE_BUCKET_ENV: "b",
               bak.OBJECT_STORAGE_ACCESS_KEY_ENV: "a",
               bak.OBJECT_STORAGE_SECRET_KEY_ENV: "s",
               bak.OBJECT_STORAGE_KEEP_ENV: "many"}
        with self.assertRaises(RuntimeError):
            bak.object_storage_config(env)


class FakeS3Client:
    """Minimal stand-in for a boto3 S3 client — no network, no bucket."""

    def __init__(self, existing_keys=()):
        self.keys = list(existing_keys)
        self.uploads = []
        self.deleted = []

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        return self

    def paginate(self, Bucket=None, Prefix=None):
        yield {"Contents": [{"Key": k} for k in self.keys if k.startswith(Prefix)]}

    def upload_fileobj(self, fh, bucket, key, ExtraArgs=None):
        self.uploads.append({"bucket": bucket, "key": key, "extra": ExtraArgs,
                             "bytes": fh.read()})
        self.keys.append(key)

    def delete_objects(self, Bucket=None, Delete=None):
        for obj in Delete["Objects"]:
            self.deleted.append(obj["Key"])
            if obj["Key"] in self.keys:
                self.keys.remove(obj["Key"])


class ObjectStorageUploadTests(SimpleTestCase):
    def _config(self, keep=2):
        return {"bucket": "sms-backups", "access_key": "AKIA", "secret_key": "s",
                "endpoint_url": None, "region": None, "prefix": "backups",
                "keep": keep}

    def _backup_dir(self, tmp, name="backup-20260101T000000Z"):
        folder = Path(tmp) / name
        folder.mkdir()
        (folder / "db.sqlite3").write_bytes(b"db")
        (folder / "manifest.json").write_text('{"engine": "sqlite"}')
        return folder

    def test_upload_packs_the_folder_and_encrypts_server_side(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = self._backup_dir(tmp)
            client = FakeS3Client()
            result = bak.upload_backup(folder, self._config(), client=client)
            self.assertEqual(result["key"], "backups/backup-20260101T000000Z.tar.gz")
            self.assertEqual(client.uploads[0]["extra"],
                             {"ServerSideEncryption": "AES256"})
            # The bundle contains the artifacts AND the manifest.
            with tarfile.open(fileobj=io.BytesIO(client.uploads[0]["bytes"])) as tar:
                names = sorted(tar.getnames())
            self.assertEqual(names, ["db.sqlite3", "manifest.json"])

    def test_upload_prunes_the_remote_set_to_keep(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = self._backup_dir(tmp, "backup-20260103T000000Z")
            client = FakeS3Client([
                "backups/backup-20260101T000000Z.tar.gz",
                "backups/backup-20260102T000000Z.tar.gz",
                "backups/some-other-file.txt",  # not ours: must be ignored
            ])
            result = bak.upload_backup(folder, self._config(keep=2), client=client)
            self.assertEqual(result["pruned"],
                             ["backups/backup-20260101T000000Z.tar.gz"])
            self.assertIn("backups/some-other-file.txt", client.keys)

    def test_no_pruning_when_under_the_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = self._backup_dir(tmp)
            client = FakeS3Client()
            result = bak.upload_backup(folder, self._config(keep=5), client=client)
            self.assertEqual(result["pruned"], [])

    def test_staging_bundle_does_not_survive_the_upload(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = self._backup_dir(tmp)
            before = set(Path(tempfile.gettempdir()).glob("sms-backup-upload-*"))
            bak.upload_backup(folder, self._config(), client=FakeS3Client())
            after = set(Path(tempfile.gettempdir()).glob("sms-backup-upload-*"))
            self.assertEqual(before, after, "staging directory was left behind")

    def test_credentials_go_to_the_client_constructor_not_to_argv(self):
        config = self._config()
        with mock.patch("boto3.client") as client:
            bak.object_storage_client(config)
        kwargs = client.call_args.kwargs
        self.assertEqual(kwargs["aws_access_key_id"], "AKIA")
        self.assertEqual(kwargs["aws_secret_access_key"], "s")
        # The only positional argument is the service name; the credentials are
        # kwargs to a library call, never an argv that `ps` could capture.
        self.assertEqual(client.call_args.args, ("s3",))

    def test_upload_without_config_explains_what_to_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = self._backup_dir(tmp)
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop(bak.OBJECT_STORAGE_BUCKET_ENV, None)
                with self.assertRaises(RuntimeError) as ctx:
                    bak.upload_backup(folder)
            self.assertIn(bak.OBJECT_STORAGE_BUCKET_ENV, str(ctx.exception))


class BackupDataCommandTests(SimpleTestCase):
    """End-to-end `backup_data` against a disposable sqlite file.

    The configured database is patched to a throwaway file in a temp dir, so
    this exercises the real command — engine detection, snapshot, media archive,
    encryption, manifest, permissions, pruning — without touching the project
    database or MEDIA_ROOT.
    """

    def _disposable_db(self, tmp):
        db = Path(tmp) / "src.sqlite3"
        conn = sqlite3.connect(db)
        conn.executescript("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT);"
                           "INSERT INTO t (v) VALUES ('alpha');")
        conn.commit()
        conn.close()
        return db

    def _settings(self, db):
        return {"default": {"ENGINE": "django.db.backends.sqlite3",
                            "NAME": str(db)}}

    def _media(self, tmp):
        media = Path(tmp) / "media"
        (media / "student_photos").mkdir(parents=True)
        (media / "student_photos" / "p.png").write_bytes(b"\x89PNG\r\n\x1a\nphoto")
        return media

    def _run_backup(self, tmp, env_extra=None):
        db = self._disposable_db(tmp)
        media = self._media(tmp)
        backups = Path(tmp) / "backups"
        env = {bak.BACKUPS_ENV: str(backups),
               bak.OBJECT_STORAGE_BUCKET_ENV: ""}
        env.update(env_extra or {})
        from django.core.management import call_command
        with mock.patch.dict(os.environ, env):
            with override_settings(DATABASES=self._settings(db)):
                call_command("backup_data", keep=2, media_dir=str(media),
                             backup_root=str(backups), verbosity=0)
        folders = sorted(p for p in backups.iterdir() if p.is_dir())
        return db, folders[-1]

    def test_plaintext_backup_is_complete_and_private(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, folder = self._run_backup(tmp)
            self.assertTrue((folder / "db.sqlite3").exists())
            self.assertTrue((folder / "media.tar.gz").exists())
            self.assertEqual((folder / "db.sqlite3").stat().st_mode & 0o777, 0o600)
            manifest = bak.load_manifest(folder / "manifest.json")
            self.assertEqual(manifest["db_file"], "db.sqlite3")
            self.assertEqual(manifest["db_sha256"], bak.sha256(folder / "db.sqlite3"))
            self.assertEqual(manifest["media_sha256"],
                             bak.sha256(folder / "media.tar.gz"))
            self.assertEqual(manifest["media_file_count"], 1)
            self.assertEqual(manifest["media_backend"], "filesystem")
            self.assertIsNone(manifest["encryption"])

    @needs_openssl
    def test_encrypted_backup_records_plain_digest_and_leaves_no_plaintext(self):
        env = {bak.ENCRYPTION_ENV: "openssl", bak.PASSPHRASE_ENV: TEST_PASSPHRASE}
        with tempfile.TemporaryDirectory() as tmp:
            _, folder = self._run_backup(tmp, env)
            self.assertTrue((folder / "db.sqlite3.enc").exists())
            self.assertTrue((folder / "media.tar.gz.enc").exists())
            self.assertFalse((folder / "db.sqlite3").exists())
            self.assertFalse((folder / "media.tar.gz").exists())
            manifest = bak.load_manifest(folder / "manifest.json")
            self.assertEqual(manifest["db_file"], "db.sqlite3.enc")
            self.assertEqual(manifest["db_sha256"],
                             bak.sha256(folder / "db.sqlite3.enc"))
            # The plaintext digest is what proves a later decryption produced
            # the snapshot itself, and not merely some file.
            with mock.patch.dict(os.environ, env):
                with bak.decrypted_backup(folder, manifest) as (plain_db, _):
                    self.assertEqual(bak.sha256(plain_db),
                                     manifest["db_plain_sha256"])
            self.assertEqual(manifest["encryption"],
                             bak.ENCRYPTION_LABELS["openssl"])
            self.assertNotIn(TEST_PASSPHRASE, (folder / "manifest.json").read_text())

    @needs_openssl
    def test_encrypted_backup_passes_the_health_gate(self):
        env = {bak.ENCRYPTION_ENV: "openssl", bak.PASSPHRASE_ENV: TEST_PASSPHRASE}
        with tempfile.TemporaryDirectory() as tmp:
            _, folder = self._run_backup(tmp, env)
            from django.core.management import call_command
            with mock.patch.dict(os.environ, env):
                call_command("check_backups", backup_root=str(folder.parent),
                             max_age_hours=1, verbosity=0)

    def test_missing_database_fails_and_leaves_no_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            backups = Path(tmp) / "backups"
            env = {bak.BACKUPS_ENV: str(backups),
                   bak.OBJECT_STORAGE_BUCKET_ENV: ""}
            from django.core.management import call_command
            from django.core.management.base import CommandError
            missing = self._settings(Path(tmp) / "does-not-exist.sqlite3")
            with mock.patch.dict(os.environ, env):
                with override_settings(DATABASES=missing):
                    with self.assertRaises(CommandError):
                        call_command("backup_data", backup_root=str(backups),
                                     media_dir=str(tmp), verbosity=0)
            leftovers = [p for p in backups.iterdir() if p.is_dir()]
            self.assertEqual(leftovers, [], "a failed backup left a folder behind")


class CheckBackupsPolicyTests(SimpleTestCase):
    """The health gate also enforces encryption policy and file modes."""

    def _make_backup(self, root, **kwargs):
        import datetime
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y%m%dT%H%M%SZ")
        folder = root / f"backup-{stamp}"
        folder.mkdir(parents=True)
        import hashlib
        db_bytes = kwargs.get("db_bytes", b"real-db")
        (folder / "db.sqlite3").write_bytes(db_bytes)
        manifest = {
            "engine": "sqlite", "db_file": "db.sqlite3",
            "db_sha256": hashlib.sha256(db_bytes).hexdigest(),
            "media_file": None, "media_file_count": 0,
            "credentials_included": False,
        }
        if kwargs.get("encryption"):
            manifest["encryption"] = kwargs["encryption"]
        if kwargs.get("media_bytes") is not None:
            (folder / "media.tar.gz").write_bytes(kwargs["media_bytes"])
            manifest["media_file"] = "media.tar.gz"
            manifest["media_sha256"] = hashlib.sha256(
                kwargs["media_bytes"]).hexdigest()
        (folder / "manifest.json").write_text(json.dumps(manifest))
        mode = kwargs.get("mode", 0o600)
        for path in folder.rglob("*"):
            path.chmod(mode)
        folder.chmod(0o700)
        return folder

    def _run(self, root, env=None, **flags):
        from django.core.management import call_command
        with mock.patch.dict(os.environ, env or {}):
            try:
                call_command("check_backups", backup_root=str(root),
                             verbosity=0, **flags)
                return 0
            except SystemExit as exc:
                return exc.code

    def test_world_readable_artifacts_fail_the_gate(self):
        if os.name != "posix":
            self.skipTest("POSIX permission bits only")
        with tempfile.TemporaryDirectory() as tmp:
            self._make_backup(Path(tmp), mode=0o644)
            self.assertNotEqual(self._run(Path(tmp)), 0)

    def test_private_artifacts_pass_the_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._make_backup(Path(tmp))
            self.assertEqual(self._run(Path(tmp)), 0)

    def test_permission_check_can_be_skipped(self):
        if os.name != "posix":
            self.skipTest("POSIX permission bits only")
        with tempfile.TemporaryDirectory() as tmp:
            self._make_backup(Path(tmp), mode=0o644)
            self.assertEqual(
                self._run(Path(tmp), skip_permission_check=True), 0)

    def test_plaintext_backup_fails_when_encryption_is_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._make_backup(Path(tmp))
            code = self._run(Path(tmp), env={bak.ENCRYPTION_ENV: "openssl"})
            self.assertNotEqual(code, 0)

    def test_encrypted_backup_satisfies_the_encryption_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._make_backup(
                Path(tmp), encryption=bak.ENCRYPTION_LABELS["openssl"])
            code = self._run(Path(tmp), env={bak.ENCRYPTION_ENV: "openssl"})
            self.assertEqual(code, 0)

    def test_media_sha_mismatch_fails_the_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = self._make_backup(Path(tmp), media_bytes=b"photos")
            (folder / "media.tar.gz").write_bytes(b"truncated")
            self.assertNotEqual(self._run(Path(tmp)), 0)

    def test_media_sha_match_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._make_backup(Path(tmp), media_bytes=b"photos")
            self.assertEqual(self._run(Path(tmp)), 0)

    def test_invalid_encryption_setting_fails_loudly(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._make_backup(Path(tmp))
            code = self._run(Path(tmp), env={bak.ENCRYPTION_ENV: "rot13"})
            self.assertNotEqual(code, 0)


class EngineHandlingTests(SimpleTestCase):
    """Backups must match the real engine — and refuse anything else."""

    def test_sqlite_is_detected_from_settings(self):
        with override_settings(DATABASES={"default": {
                "ENGINE": "django.db.backends.sqlite3", "NAME": "/tmp/x.sqlite3"}}):
            self.assertEqual(bak.db_engine(), "sqlite")

    def test_postgres_is_detected_from_settings(self):
        with override_settings(DATABASES={"default": {
                "ENGINE": "django.db.backends.postgresql", "NAME": "sms"}}):
            self.assertEqual(bak.db_engine(), "postgres")

    def test_unknown_engine_is_unknown_not_sqlite(self):
        with override_settings(DATABASES={"default": {
                "ENGINE": "django.db.backends.mysql", "NAME": "sms"}}):
            self.assertEqual(bak.db_engine(), "unknown")

    def test_postgres_without_client_tools_says_what_to_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch("shutil.which", return_value=None):
                with self.assertRaises(RuntimeError) as ctx:
                    bak.backup_postgres(Path(tmp) / "db.dump")
            self.assertIn("pg_dump", str(ctx.exception))

    def test_credentials_go_to_the_child_environment_not_argv(self):
        params = {"dbname": "sms_prod", "user": "sms",
                  "password": "SuperSecretPass123", "host": "db.internal",
                  "port": 5432}
        with mock.patch.object(bak, "_pg_connection_params", return_value=params):
            env = bak.postgres_connect_env()
            self.assertEqual(env["PGPASSWORD"], "SuperSecretPass123")
            self.assertEqual(env["PGHOST"], "db.internal")
            # The password reaches the child through its environment only —
            # never a command line that `ps` or a log could capture.
            self.assertNotIn("SuperSecretPass123", " ".join(
                bak._openssl_cmd("-e", Path("a"), Path("b"))))

    def test_backup_data_refuses_an_unsupported_engine(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {bak.BACKUPS_ENV: str(tmp)}):
                with override_settings(DATABASES={"default": {
                        "ENGINE": "django.db.backends.mysql", "NAME": "sms"}}):
                    with self.assertRaises(CommandError):
                        call_command("backup_data", backup_root=str(tmp),
                                     verbosity=0)
            self.assertEqual(
                [p for p in Path(tmp).iterdir() if p.is_dir()], [],
                "a refused backup left a folder behind")


class PostgresConnectionEnvTests(SimpleTestCase):
    """pg_dump must be pointed at the server Django actually uses.

    Regression: `_postgres_params` used to read ``settings.DATABASES['HOST']``
    and default it to ``localhost``. A ``DATABASE_URL`` such as
    ``postgres://user@/dbname?host=/var/run/postgresql`` leaves HOST empty and
    carries the socket directory in OPTIONS, so the dump silently targeted
    ``localhost`` — a different server from the one holding the data. (Proven
    end to end by `scripts/backup_smoke_test.sh --postgres` against a real
    server; these tests pin the mapping itself.)

    ``override_settings(DATABASES=...)`` cannot drive this: Django caches the
    connection object and does not rebuild it, and dropping it here would
    destroy the in-memory test database for every later test. So the connection
    params — the value Django itself connects with — are supplied directly.
    """

    def _env_for(self, params):
        with mock.patch.object(bak, "_pg_connection_params", return_value=params):
            return bak._postgres_params()

    def test_params_come_from_the_live_connection_object(self):
        from django.db import connections
        wrapper = connections["default"]
        with mock.patch.object(
            type(wrapper), "get_connection_params",
            return_value={"dbname": "sms", "host": "/sock"},
        ) as mocked:
            self.assertEqual(bak._pg_connection_params(),
                             {"dbname": "sms", "host": "/sock"})
        mocked.assert_called_once_with()

    def test_socket_directory_becomes_pghost(self):
        env = self._env_for({"dbname": "sms_prod", "user": "sms",
                             "password": "pw", "host": "/var/run/postgresql"})
        self.assertEqual(env["PGHOST"], "/var/run/postgresql")
        self.assertEqual(env["PGDATABASE"], "sms_prod")
        self.assertEqual(env["PGUSER"], "sms")
        self.assertEqual(env["PGPASSWORD"], "pw")

    def test_blank_host_is_never_invented_as_localhost(self):
        env = self._env_for({"dbname": "sms_prod", "host": ""})
        self.assertNotIn("PGHOST", env)
        self.assertNotIn("localhost", env.values())

    def test_missing_host_is_omitted_too(self):
        env = self._env_for({"dbname": "sms_prod", "user": "sms"})
        self.assertNotIn("PGHOST", env)

    def test_explicit_host_and_port_are_used(self):
        env = self._env_for({"dbname": "sms_prod", "host": "db.internal",
                             "port": 5433})
        self.assertEqual(env["PGHOST"], "db.internal")
        self.assertEqual(env["PGPORT"], "5433")

    def test_client_side_kwargs_are_not_exported(self):
        env = self._env_for({"dbname": "sms", "host": "/var/run/postgresql",
                             "client_encoding": "UTF8", "cursor_factory": object})
        # psycopg2-only settings have no libpq environment equivalent.
        self.assertNotIn("PGCLIENTENCODING", env)
        self.assertFalse(any("CURSOR" in k for k in env))

    def test_sslmode_travels_to_the_child_process(self):
        env = self._env_for({"dbname": "sms", "sslmode": "require"})
        self.assertEqual(env["PGSSLMODE"], "require")

    def test_no_password_is_omitted_rather_than_sent_empty(self):
        env = self._env_for({"dbname": "sms", "password": ""})
        self.assertNotIn("PGPASSWORD", env)


class RedactedDbLabelTests(SimpleTestCase):
    """The label printed/logged identifies the target without leaking creds."""

    def test_socket_directory_is_shown_not_a_blank_host(self):
        with mock.patch.object(bak, "_pg_connection_params",
                               return_value={"dbname": "sms", "host": "/tmp/pg"}):
            with override_settings(DATABASES={"default": {
                    "ENGINE": "django.db.backends.postgresql",
                    "NAME": "sms", "HOST": ""}}):
                self.assertEqual(bak.redacted_db_name(), "postgres:sms@/tmp/pg")

    def test_falls_back_to_settings_when_params_are_unavailable(self):
        with mock.patch.object(bak, "_pg_connection_params",
                               side_effect=RuntimeError("no connection")):
            with override_settings(DATABASES={"default": {
                    "ENGINE": "django.db.backends.postgresql",
                    "NAME": "sms", "HOST": "db.internal"}}):
                self.assertEqual(bak.redacted_db_name(),
                                 "postgres:sms@db.internal")

    def test_no_password_or_dsn_ever_appears(self):
        with mock.patch.object(bak, "_pg_connection_params",
                               return_value={"dbname": "sms",
                                             "password": "SuperSecretPass123",
                                             "host": "db.internal"}):
            with override_settings(DATABASES={"default": {
                    "ENGINE": "django.db.backends.postgresql",
                    "NAME": "sms", "HOST": "db.internal",
                    "PASSWORD": "SuperSecretPass123"}}):
                label = bak.redacted_db_name()
        self.assertEqual(label, "postgres:sms@db.internal")
        self.assertNotIn("SuperSecretPass123", label)
        self.assertNotIn("postgres://", label)


# --------------------------------------------------------------------------
# Regression: an age-encrypted backup must be decrypted with age, whatever
# BACKUP_ENCRYPTION happens to be set to on the host doing the restore. The
# manifest is the source of truth, not today's environment.
# --------------------------------------------------------------------------
class AgeDecryptionDispatchTests(SimpleTestCase):
    """`decrypt_artifact(mode='age')` used to consult the environment instead.

    With BACKUP_ENCRYPTION unset (or 'openssl') on the restoring host, the age
    branch was skipped and the plaintext fallback copied the *ciphertext*
    verbatim — a restore that reported success and produced garbage.
    """

    def _cipher(self, tmp, name="db.dump.enc"):
        path = Path(tmp) / name
        path.write_bytes(b"age-ciphertext-not-a-database")
        return path

    def test_age_mode_is_honoured_when_the_environment_says_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            cipher = self._cipher(tmp)
            out = Path(tmp) / "db.dump"
            env = {bak.ENCRYPTION_ENV: "off"}
            with self.assertRaises(RuntimeError) as ctx:
                bak.decrypt_artifact(cipher, out, env=env, mode="age")
            self.assertIn(bak.AGE_IDENTITY_ENV, str(ctx.exception))
            self.assertFalse(
                out.exists(),
                "the ciphertext was copied out as if it were the plaintext",
            )

    def test_age_mode_is_honoured_when_the_environment_says_openssl(self):
        with tempfile.TemporaryDirectory() as tmp:
            cipher = self._cipher(tmp)
            with self.assertRaises(RuntimeError) as ctx:
                bak.decrypt_artifact(cipher, Path(tmp) / "out",
                                     env={bak.ENCRYPTION_ENV: "openssl",
                                          bak.PASSPHRASE_ENV: TEST_PASSPHRASE},
                                     mode="age")
            self.assertIn(bak.AGE_IDENTITY_ENV, str(ctx.exception))

    def test_identity_file_goes_to_age_as_a_path_not_as_a_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            cipher = self._cipher(tmp)
            identity = Path(tmp) / "backup.age"
            identity.write_text("AGE-SECRET-KEY-1QQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQ\n")
            seen = {}

            def fake_run(cmd, env, what):
                seen["cmd"], seen["env"] = cmd, env

            with mock.patch.object(bak, "_run", side_effect=fake_run):
                bak.decrypt_artifact(
                    cipher, Path(tmp) / "out",
                    env={bak.AGE_IDENTITY_ENV: str(identity)}, mode="age",
                )
            self.assertEqual(seen["cmd"][:3], ["age", "--decrypt", "--identity"])
            self.assertIn(str(identity), seen["cmd"])
            # The secret material itself is never an argv element (`ps`-visible).
            self.assertNotIn("AGE-SECRET-KEY-1QQQ", " ".join(seen["cmd"]))

    def test_decrypted_backup_refuses_an_age_manifest_without_an_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "backup-20260101T000000Z"
            folder.mkdir()
            self._cipher(folder)
            manifest = {"db_file": "db.dump.enc", "media_file": None,
                        "encryption": bak.ENCRYPTION_LABELS["age"]}
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop(bak.ENCRYPTION_ENV, None)
                os.environ.pop(bak.AGE_IDENTITY_ENV, None)
                with self.assertRaises(RuntimeError):
                    with bak.decrypted_backup(folder, manifest) as paths:
                        self.fail(f"expected a refusal, got {paths}")

    def test_manifest_scheme_decides_not_the_environment(self):
        """`decrypted_backup` parses the label; openssl still round-trips."""
        if not HAS_OPENSSL:
            self.skipTest("openssl not on PATH")
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "backup-20260101T000000Z"
            folder.mkdir()
            payload = b"SQLite format 3\x00 fake snapshot"
            plain = folder / "db.sqlite3"
            plain.write_bytes(payload)
            env = {bak.ENCRYPTION_ENV: "openssl", bak.PASSPHRASE_ENV: TEST_PASSPHRASE}
            cipher = bak.encrypt_artifact(plain, env=env)
            manifest = {"db_file": cipher.name, "media_file": None,
                        "encryption": bak.ENCRYPTION_LABELS["openssl"]}
            # The environment now says "off" — the manifest must still win.
            with mock.patch.dict(os.environ, {bak.ENCRYPTION_ENV: "off"}):
                with bak.decrypted_backup(folder, manifest, env=env) as (db_path, _):
                    self.assertEqual(Path(db_path).read_bytes(), payload)


class SqliteSidecarTests(SimpleTestCase):
    """A restore must not leave the old database's journal/WAL state behind.

    Reproduced before the fix: restoring a snapshot whose only row was ``NEW``
    over a WAL-mode database with a stale ``-wal`` made the next reader see the
    OLD rows, with ``PRAGMA integrity_check`` reporting ``ok`` — a restore that
    succeeded, verified, and restored nothing.
    """

    def _crashed_wal_database(self, path, rows=("OLD",)):
        """Leave ``path`` plus a stale ``-wal``/``-shm``, as a crash would."""
        path = Path(path)
        conn = sqlite3.connect(path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE t (v TEXT)")
        for row in rows:
            conn.execute("INSERT INTO t (v) VALUES (?)", (row,))
        conn.commit()
        # A second open connection stops the WAL being checkpointed and deleted
        # when the first one closes, so the snapshot below is the crashed state.
        holder = sqlite3.connect(path)
        holder.execute("SELECT * FROM t").fetchall()
        snapshot = {}
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(str(path) + suffix)
            if candidate.exists():
                snapshot[candidate] = candidate.read_bytes()
        conn.close()
        holder.close()
        for candidate, data in snapshot.items():
            candidate.write_bytes(data)
        return sorted(p.name for p in snapshot)

    def _snapshot_with(self, tmp, row="NEW", name="snapshot.sqlite3"):
        src = Path(tmp) / name
        conn = sqlite3.connect(src)
        conn.execute("CREATE TABLE t (v TEXT)")
        conn.execute("INSERT INTO t (v) VALUES (?)", (row,))
        conn.commit()
        conn.close()
        return src

    def _rows(self, path):
        conn = sqlite3.connect(Path(path))
        try:
            return [r[0] for r in conn.execute("SELECT v FROM t")]
        finally:
            conn.close()

    def _rows_or_error(self, path):
        try:
            return self._rows(path)
        except sqlite3.Error as exc:
            return f"{type(exc).__name__}: {exc}"

    def test_stale_wal_is_removed_and_the_snapshot_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "dst.sqlite3"
            created = self._crashed_wal_database(dest)
            self.assertIn("dst.sqlite3-wal", created)
            # No read here on purpose: opening the crashed database would
            # replay (and so clear) the very WAL this test is about.
            self.assertTrue(Path(str(dest) + "-wal").exists())

            src = self._snapshot_with(tmp)
            size, removed = bak.replace_sqlite_database(src, dest)

            self.assertIn("dst.sqlite3-wal", removed)
            self.assertEqual(size, dest.stat().st_size)
            self.assertEqual(bak.sha256(dest), bak.sha256(src))
            # The point of the whole test: the reader sees the restored data.
            self.assertEqual(self._rows(dest), ["NEW"])

    def test_a_naive_copy_replays_the_stale_wal_and_restores_nothing(self):
        """The hazard the fix exists for, kept as an executable record.

        This is the *old* behaviour — copy the main file, leave the sidecars —
        asserted to be wrong, so the bug cannot come back quietly.
        """
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "dst.sqlite3"
            self._crashed_wal_database(dest, ("OLD",))
            src = self._snapshot_with(tmp, row="NEW")

            shutil.copyfile(src, dest)          # what the code used to do

            seen = self._rows_or_error(dest)
            self.assertNotEqual(
                seen, ["NEW"],
                "the stale WAL was not replayed — the hazard this guards is gone; "
                "this assertion can be retired",
            )

    def test_stale_rollback_journal_is_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "dst.sqlite3"
            self._snapshot_with(tmp, row="OLD", name="dst.sqlite3")
            Path(str(dest) + "-journal").write_bytes(b"\x00" * 64)
            src = self._snapshot_with(tmp, name="src.sqlite3")

            _, removed = bak.replace_sqlite_database(src, dest)

            self.assertEqual(removed, ["dst.sqlite3-journal"])
            self.assertFalse(Path(str(dest) + "-journal").exists())
            self.assertEqual(self._rows(dest), ["NEW"])

    def test_no_sidecars_is_not_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "dst.sqlite3"
            self._snapshot_with(tmp, row="OLD", name="dst.sqlite3")
            src = self._snapshot_with(tmp, name="src.sqlite3")
            size, removed = bak.replace_sqlite_database(src, dest)
            self.assertEqual(removed, [])
            self.assertGreater(size, 0)
            self.assertEqual(self._rows(dest), ["NEW"])

    def test_only_the_target_sidecars_are_touched(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = self._snapshot_with(tmp, name="src.sqlite3")
            src_wal = Path(str(src) + "-wal")
            src_wal.write_bytes(b"backup-side-state")
            dest = Path(tmp) / "dst.sqlite3"
            bak.replace_sqlite_database(src, dest)
            self.assertTrue(src_wal.exists(),
                            "the snapshot's own sidecar was deleted")

    def test_restored_database_is_private(self):
        if os.name != "posix":
            self.skipTest("POSIX permission bits only")
        with tempfile.TemporaryDirectory() as tmp:
            src = self._snapshot_with(tmp)
            dest = Path(tmp) / "dst.sqlite3"
            bak.replace_sqlite_database(src, dest)
            self.assertEqual(dest.stat().st_mode & 0o777, 0o600)
            self.assertFalse(bak.world_readable(dest))

    def test_missing_snapshot_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                bak.replace_sqlite_database(Path(tmp) / "nope.sqlite3",
                                            Path(tmp) / "dst.sqlite3")

    def test_sidecar_names_are_exactly_the_sqlite_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "db.sqlite3"
            names = sorted(p.name for p in bak.sqlite_sidecars(db))
            self.assertEqual(
                names, ["db.sqlite3-journal", "db.sqlite3-shm", "db.sqlite3-wal"])


class RestoreCommandSidecarTests(SimpleTestCase):
    """The `restore_backup` command itself must clear the sidecars."""

    def test_command_removes_a_stale_wal_and_restores_the_snapshot(self):
        from django.core.management import call_command
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            # 1. a real backup folder holding a snapshot with the NEW row
            src = tmp / "src.sqlite3"
            conn = sqlite3.connect(src)
            conn.execute("CREATE TABLE t (v TEXT)")
            conn.execute("INSERT INTO t (v) VALUES ('NEW')")
            conn.commit()
            conn.close()
            folder = tmp / "backups" / "backup-20260101T000000Z"
            folder.mkdir(parents=True)
            artifact = folder / "db.sqlite3"
            bak.backup_sqlite(src, artifact)
            bak.write_manifest(
                folder / "manifest.json", engine="sqlite",
                db_file=artifact.name, media_file=None, media_count=0,
                db_sha=bak.sha256(artifact), db_size=artifact.stat().st_size,
                media_backend="filesystem",
            )
            # 2. a target database that died mid-write (stale -wal/-shm)
            dest = tmp / "live.sqlite3"
            conn = sqlite3.connect(dest)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("CREATE TABLE t (v TEXT)")
            conn.execute("INSERT INTO t (v) VALUES ('OLD')")
            conn.commit()
            holder = sqlite3.connect(dest)
            holder.execute("SELECT * FROM t").fetchall()
            crashed = {p: p.read_bytes()
                       for p in (dest, Path(str(dest) + "-wal"),
                                 Path(str(dest) + "-shm")) if p.exists()}
            conn.close()
            holder.close()
            for path, data in crashed.items():
                path.write_bytes(data)
            self.assertTrue(Path(str(dest) + "-wal").exists())

            settings_db = {"default": {"ENGINE": "django.db.backends.sqlite3",
                                       "NAME": str(dest)}}
            out = io.StringIO()
            with override_settings(DATABASES=settings_db):
                call_command("restore_backup", backup=str(folder),
                             media_dir=str(tmp / "restored-media"),
                             yes=True, verbosity=1, stdout=out)
            logged = out.getvalue()
            self.assertIn("stale SQLite sidecar", logged)
            self.assertFalse(Path(str(dest) + "-wal").exists())
            conn = sqlite3.connect(dest)
            try:
                rows = [r[0] for r in conn.execute("SELECT v FROM t")]
            finally:
                conn.close()
            self.assertEqual(rows, ["NEW"])


class FakeClientError(Exception):
    """Stand-in for ``botocore.exceptions.ClientError`` (shape, not import)."""

    def __init__(self, code="404", status=404):
        super().__init__(code)
        self.response = {"Error": {"Code": code},
                         "ResponseMetadata": {"HTTPStatusCode": status}}


class FakeS3ClientWithObjects(FakeS3Client):
    """The upload stub plus the read side (head/download) a fetch needs."""

    def __init__(self, objects=None):
        objects = dict(objects or {})
        super().__init__(existing_keys=list(objects))
        self.objects = objects
        self.heads = []
        self.downloads = []

    def upload_fileobj(self, fh, bucket, key, ExtraArgs=None):
        data = fh.read()
        self.uploads.append({"bucket": bucket, "key": key, "extra": ExtraArgs,
                             "bytes": data})
        self.objects[key] = data
        if key not in self.keys:
            self.keys.append(key)

    def head_object(self, Bucket=None, Key=None):
        self.heads.append(Key)
        if Key not in self.objects:
            raise FakeClientError()
        return {"ContentLength": len(self.objects[Key]),
                "LastModified": bak.now_utc(),
                "ServerSideEncryption": "AES256"}

    def download_fileobj(self, Bucket, Key, Fileobj):
        self.downloads.append(Key)
        if Key not in self.objects:
            raise FakeClientError()
        Fileobj.write(self.objects[Key])


def _backup_folder(root, name="backup-20260101T000000Z", db_bytes=b"real-db",
                   media_bytes=None, mode=0o600):
    """A minimal, valid backup folder (artifacts + a manifest that matches)."""
    import datetime
    import hashlib
    if name is None:
        name = "backup-" + datetime.datetime.now(
            datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    folder = Path(root) / name
    folder.mkdir(parents=True)
    (folder / "db.sqlite3").write_bytes(db_bytes)
    manifest = {
        "format": 2, "engine": "sqlite", "db_file": "db.sqlite3",
        "db_sha256": hashlib.sha256(db_bytes).hexdigest(),
        "db_size_bytes": len(db_bytes), "media_file": None,
        "media_file_count": 0, "media_sha256": None, "encryption": None,
        "credentials_included": False,
    }
    if media_bytes is not None:
        (folder / "media.tar.gz").write_bytes(media_bytes)
        manifest["media_file"] = "media.tar.gz"
        manifest["media_file_count"] = 1
        manifest["media_sha256"] = hashlib.sha256(media_bytes).hexdigest()
    (folder / "manifest.json").write_text(json.dumps(manifest, sort_keys=True))
    for path in folder.rglob("*"):
        path.chmod(mode)
    folder.chmod(0o700)
    return folder


OFFBOX_ENV = {
    bak.OBJECT_STORAGE_BUCKET_ENV: "sms-drill-backups",
    bak.OBJECT_STORAGE_ACCESS_KEY_ENV: "drill-access-key",
    bak.OBJECT_STORAGE_SECRET_KEY_ENV: "drill-secret-key",
}
OFFBOX_CONFIG = {"bucket": "sms-drill-backups", "access_key": "drill-access-key",
                 "secret_key": "drill-secret-key", "endpoint_url": None,
                 "region": None, "prefix": "backups", "keep": 30}


class RemoteCopyVerificationTests(SimpleTestCase):
    """`--check-remote`: an upload that quietly stopped must fail the gate."""

    def test_an_uploaded_bundle_is_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = _backup_folder(tmp)
            client = FakeS3ClientWithObjects()
            bak.upload_backup(folder, OFFBOX_CONFIG, client=client)
            info = bak.verify_remote_copy(client, OFFBOX_CONFIG, folder)
            self.assertEqual(info["key"], f"backups/{folder.name}.tar.gz")
            self.assertGreater(info["size_bytes"], 0)

    def test_a_missing_bundle_is_reported_not_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = _backup_folder(tmp)
            client = FakeS3ClientWithObjects()
            with self.assertRaises(RuntimeError) as ctx:
                bak.verify_remote_copy(client, OFFBOX_CONFIG, folder)
            self.assertIn("no off-box copy", str(ctx.exception))
            self.assertIn(folder.name, str(ctx.exception))

    def test_an_empty_object_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = _backup_folder(tmp)
            key = bak.remote_key_for(folder, OFFBOX_CONFIG)
            client = FakeS3ClientWithObjects({key: b""})
            with self.assertRaises(RuntimeError) as ctx:
                bak.verify_remote_copy(client, OFFBOX_CONFIG, folder)
            self.assertIn("0 bytes", str(ctx.exception))

    def test_a_credentials_error_is_not_reported_as_a_missing_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = _backup_folder(tmp)
            client = FakeS3ClientWithObjects()
            client.head_object = mock.Mock(
                side_effect=FakeClientError("AccessDenied", 403))
            with self.assertRaises(FakeClientError):
                bak.verify_remote_copy(client, OFFBOX_CONFIG, folder)

    def test_check_remote_passes_when_the_copy_exists(self):
        from django.core.management import call_command
        with tempfile.TemporaryDirectory() as tmp:
            folder = _backup_folder(tmp, name=None)
            client = FakeS3ClientWithObjects()
            bak.upload_backup(folder, OFFBOX_CONFIG, client=client)
            out = io.StringIO()
            with mock.patch.dict(os.environ, OFFBOX_ENV):
                with mock.patch.object(bak, "object_storage_client",
                                       return_value=client):
                    try:
                        call_command("check_backups", backup_root=str(tmp),
                                     max_age_hours=1, check_remote=True,
                                     verbosity=0, stdout=out)
                        code = 0
                    except SystemExit as exc:
                        code = exc.code
            self.assertEqual(code, 0, out.getvalue())
            self.assertIn("off-box copy OK", out.getvalue())

    def test_check_remote_fails_when_the_copy_is_missing(self):
        from django.core.management import call_command
        with tempfile.TemporaryDirectory() as tmp:
            _backup_folder(tmp, name=None)
            client = FakeS3ClientWithObjects()
            out = io.StringIO()
            with mock.patch.dict(os.environ, OFFBOX_ENV):
                with mock.patch.object(bak, "object_storage_client",
                                       return_value=client):
                    try:
                        call_command("check_backups", backup_root=str(tmp),
                                     max_age_hours=1, check_remote=True,
                                     verbosity=0, stdout=out)
                        code = 0
                    except SystemExit as exc:
                        code = exc.code
            self.assertNotEqual(code, 0)
            self.assertIn("no off-box copy", out.getvalue())

    def test_check_remote_without_a_bucket_fails_loudly(self):
        from django.core.management import call_command
        with tempfile.TemporaryDirectory() as tmp:
            _backup_folder(tmp, name=None)
            out = io.StringIO()
            with mock.patch.dict(os.environ, {bak.OBJECT_STORAGE_BUCKET_ENV: ""}):
                try:
                    call_command("check_backups", backup_root=str(tmp),
                                 max_age_hours=1, check_remote=True,
                                 verbosity=0, stdout=out)
                    code = 0
                except SystemExit as exc:
                    code = exc.code
            self.assertNotEqual(code, 0)
            self.assertIn(bak.OBJECT_STORAGE_BUCKET_ENV, out.getvalue())

    def test_the_bucket_is_not_contacted_without_the_flag(self):
        from django.core.management import call_command
        with tempfile.TemporaryDirectory() as tmp:
            _backup_folder(tmp, name=None)
            client = FakeS3ClientWithObjects()
            with mock.patch.dict(os.environ, OFFBOX_ENV):
                with mock.patch.object(bak, "object_storage_client",
                                       return_value=client):
                    try:
                        call_command("check_backups", backup_root=str(tmp),
                                     max_age_hours=1, verbosity=0,
                                     stdout=io.StringIO())
                        code = 0
                    except SystemExit as exc:
                        code = exc.code
            self.assertEqual(code, 0)
            self.assertEqual(client.heads, [])


class FetchBackupTests(SimpleTestCase):
    """Download + unpack + verify: the restore path from a lost host."""

    def _uploaded(self, tmp, **kwargs):
        folder = _backup_folder(tmp, **kwargs)
        client = FakeS3ClientWithObjects()
        result = bak.upload_backup(folder, OFFBOX_CONFIG, client=client)
        return folder, client, result["key"]

    def test_download_round_trips_a_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, client, key = self._uploaded(tmp)
            dest_root = Path(tmp) / "fetched"
            folder = bak.download_remote_backup(client, OFFBOX_CONFIG, key,
                                                dest_root)
            self.assertEqual(folder, dest_root / src.name)
            self.assertEqual((folder / "db.sqlite3").read_bytes(),
                             (src / "db.sqlite3").read_bytes())
            self.assertEqual(bak.load_manifest(folder / "manifest.json"),
                             bak.load_manifest(src / "manifest.json"))
            self.assertEqual(client.downloads, [key])

    def test_downloaded_artifacts_are_private(self):
        if os.name != "posix":
            self.skipTest("POSIX permission bits only")
        with tempfile.TemporaryDirectory() as tmp:
            _, client, key = self._uploaded(tmp)
            folder = bak.download_remote_backup(client, OFFBOX_CONFIG, key,
                                                Path(tmp) / "fetched")
            self.assertEqual(folder.stat().st_mode & 0o777, 0o700)
            for path in folder.rglob("*"):
                if path.is_file():
                    self.assertEqual(path.stat().st_mode & 0o777, 0o600,
                                     f"{path.name} is not 0600")

    def test_a_corrupt_bundle_is_refused_and_not_left_behind(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder, client, key = self._uploaded(tmp)
            # Repack the same bundle with a database that does not match the
            # manifest digest it carries — what a truncated upload looks like.
            tampered = Path(tmp) / "tampered"
            shutil.copytree(folder, tampered)
            (tampered / "db.sqlite3").write_bytes(b"half-written")
            bundle = Path(tmp) / "bundle.tar.gz"
            bak.pack_backup_dir(tampered, bundle)
            client.objects[key] = bundle.read_bytes()

            dest_root = Path(tmp) / "fetched"
            with self.assertRaises(RuntimeError) as ctx:
                bak.download_remote_backup(client, OFFBOX_CONFIG, key, dest_root)
            self.assertIn("SHA-256 mismatch", str(ctx.exception))
            self.assertFalse((dest_root / folder.name).exists(),
                             "a bundle that failed verification was left behind")

    def test_a_bundle_without_a_manifest_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            bare = Path(tmp) / "bare" / "backup-20260102T000000Z"
            bare.mkdir(parents=True)
            (bare / "db.sqlite3").write_bytes(b"x")
            bundle = Path(tmp) / "bare.tar.gz"
            bak.pack_backup_dir(bare, bundle)
            client = FakeS3ClientWithObjects(
                {"backups/backup-20260102T000000Z.tar.gz": bundle.read_bytes()})
            with self.assertRaises(RuntimeError) as ctx:
                bak.download_remote_backup(
                    client, OFFBOX_CONFIG,
                    "backups/backup-20260102T000000Z.tar.gz", Path(tmp) / "out")
            self.assertIn("manifest.json", str(ctx.exception))

    def test_an_existing_folder_is_not_clobbered_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, client, key = self._uploaded(tmp)
            dest_root = Path(tmp) / "fetched"
            bak.download_remote_backup(client, OFFBOX_CONFIG, key, dest_root)
            marker = dest_root / src.name / "do-not-touch"
            marker.write_text("keep me")
            with self.assertRaises(RuntimeError) as ctx:
                bak.download_remote_backup(client, OFFBOX_CONFIG, key, dest_root)
            self.assertIn("--force", str(ctx.exception))
            self.assertTrue(marker.exists())
            bak.download_remote_backup(client, OFFBOX_CONFIG, key, dest_root,
                                       force=True)
            self.assertFalse(marker.exists())
            self.assertTrue((dest_root / src.name / "db.sqlite3").exists())

    def test_a_key_that_is_not_a_bundle_is_refused(self):
        client = FakeS3ClientWithObjects()
        for bad in ("backups/../../etc/passwd.tar.gz", "backups/notes.tar.gz",
                    "backups/backup-20260101T000000Z.zip"):
            with self.subTest(key=bad), self.assertRaises(RuntimeError):
                bak.download_remote_backup(client, OFFBOX_CONFIG, bad,
                                           Path(tempfile.gettempdir()) / "nope")

    def test_command_lists_the_bucket(self):
        from django.core.management import call_command
        with tempfile.TemporaryDirectory() as tmp:
            src, client, key = self._uploaded(tmp)
            out = io.StringIO()
            with mock.patch.dict(os.environ, OFFBOX_ENV):
                with mock.patch.object(bak, "object_storage_client",
                                       return_value=client):
                    call_command("fetch_backup", list=True, backup_root=str(tmp),
                                 verbosity=0, stdout=out)
            self.assertIn(key, out.getvalue())
            self.assertIn("1 bundle(s)", out.getvalue())
            self.assertEqual(client.downloads, [])

    def test_command_downloads_the_latest(self):
        from django.core.management import call_command
        with tempfile.TemporaryDirectory() as tmp:
            _backup_folder(tmp, name="backup-20260101T000000Z")
            older = _backup_folder(tmp, name="backup-20251231T000000Z")
            client = FakeS3ClientWithObjects()
            for folder in (older, Path(tmp) / "backup-20260101T000000Z"):
                bak.upload_backup(folder, OFFBOX_CONFIG, client=client)
            dest = Path(tmp) / "fetched"
            out = io.StringIO()
            with mock.patch.dict(os.environ, OFFBOX_ENV):
                with mock.patch.object(bak, "object_storage_client",
                                       return_value=client):
                    call_command("fetch_backup", latest=True, dest=str(dest),
                                 verbosity=0, stdout=out)
            self.assertEqual(client.downloads,
                             ["backups/backup-20260101T000000Z.tar.gz"])
            self.assertTrue((dest / "backup-20260101T000000Z" / "db.sqlite3").exists())
            self.assertIn("restore_backup", out.getvalue())

    def test_command_without_a_bucket_says_what_to_set(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {bak.OBJECT_STORAGE_BUCKET_ENV: ""}):
                with self.assertRaises(CommandError) as ctx:
                    call_command("fetch_backup", latest=True,
                                 backup_root=str(tmp), verbosity=0)
            self.assertIn(bak.OBJECT_STORAGE_BUCKET_ENV, str(ctx.exception))

    def test_command_reports_an_empty_bucket(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError
        with tempfile.TemporaryDirectory() as tmp:
            client = FakeS3ClientWithObjects()
            with mock.patch.dict(os.environ, OFFBOX_ENV):
                with mock.patch.object(bak, "object_storage_client",
                                       return_value=client):
                    with self.assertRaises(CommandError) as ctx:
                        call_command("fetch_backup", latest=True,
                                     backup_root=str(tmp), verbosity=0)
            self.assertIn("holds no backup bundles", str(ctx.exception))


class DataSafetyCheckTests(SimpleTestCase):
    """The design rules from docs/DATA_SAFETY_STATUS.md §2, enforced by `check`."""

    def test_one_database_is_silent(self):
        one = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
        with override_settings(DATABASES=one):
            self.assertEqual([c.id for c in checks.check_single_writable_database()], [])

    def test_a_second_database_warns(self):
        two = {
            "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"},
            "analytics": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"},
        }
        with override_settings(DATABASES=two):
            ids = [c.id for c in checks.check_single_writable_database()]
        self.assertEqual(ids, ["students.W015"])

    def test_backups_inside_media_root_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            media = Path(tmp) / "media"
            backups = media / "backups"
            backups.mkdir(parents=True)
            with mock.patch.dict(os.environ, {bak.BACKUPS_ENV: str(backups)}):
                with override_settings(MEDIA_ROOT=str(media),
                                       STATIC_ROOT=str(Path(tmp) / "staticfiles")):
                    ids = [c.id for c in
                           checks.check_backup_root_not_web_served()]
            self.assertEqual(ids, ["students.E013"])

    def test_backups_inside_static_root_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            static = Path(tmp) / "staticfiles"
            backups = static / "backups"
            backups.mkdir(parents=True)
            with mock.patch.dict(os.environ, {bak.BACKUPS_ENV: str(backups)}):
                with override_settings(MEDIA_ROOT=str(Path(tmp) / "media"),
                                       STATIC_ROOT=str(static)):
                    ids = [c.id for c in
                           checks.check_backup_root_not_web_served()]
            self.assertEqual(ids, ["students.E013"])

    def test_backups_outside_every_served_tree_is_silent(self):
        with tempfile.TemporaryDirectory() as tmp:
            backups = Path(tmp) / "backups"
            backups.mkdir()
            with mock.patch.dict(os.environ, {bak.BACKUPS_ENV: str(backups)}):
                with override_settings(MEDIA_ROOT=str(Path(tmp) / "media"),
                                       STATIC_ROOT=str(Path(tmp) / "staticfiles")):
                    ids = [c.id for c in
                           checks.check_backup_root_not_web_served()]
            self.assertEqual(ids, [])

    def test_an_ephemeral_backup_root_warns_only_on_a_deployment(self):
        from school_system import settings as project_settings
        ephemeral = str(Path(project_settings.BASE_DIR) / "backups")
        with mock.patch.dict(os.environ, {bak.BACKUPS_ENV: ephemeral}):
            with override_settings(DEBUG=False):
                self.assertEqual(
                    [c.id for c in checks.check_backup_root_durable()],
                    ["students.W014"])
            with override_settings(DEBUG=True):
                self.assertEqual(
                    [c.id for c in checks.check_backup_root_durable()], [])

    def test_a_persistent_backup_root_is_silent(self):
        with mock.patch.dict(os.environ, {bak.BACKUPS_ENV: "/data/backups"}):
            with override_settings(DEBUG=False):
                self.assertEqual(
                    [c.id for c in checks.check_backup_root_durable()], [])

    def test_the_new_checks_are_registered_where_they_belong(self):
        from django.core.checks.registry import registry
        self.assertIn(checks.check_single_writable_database,
                      registry.registered_checks)
        self.assertIn(checks.check_backup_root_not_web_served,
                      registry.deployment_checks)
        self.assertIn(checks.check_backup_root_durable,
                      registry.deployment_checks)
