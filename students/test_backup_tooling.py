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
        config = {"default": {"ENGINE": "django.db.backends.postgresql",
                              "NAME": "sms_prod", "USER": "sms",
                              "PASSWORD": "SuperSecretPass123",
                              "HOST": "db.internal", "PORT": "5432"}}
        with override_settings(DATABASES=config):
            env = bak.postgres_connect_env()
            self.assertEqual(env["PGPASSWORD"], "SuperSecretPass123")
            self.assertEqual(env["PGHOST"], "db.internal")
            # ...and the human-readable label stays free of them.
            label = bak.redacted_db_name()
        self.assertEqual(label, "postgres:sms_prod@db.internal")
        self.assertNotIn("SuperSecretPass123", label)
        self.assertNotIn("postgres://", label)

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
