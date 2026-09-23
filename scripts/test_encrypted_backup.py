import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import encrypted_backup as eb


class TestEncryptedBackup(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source.dump"
        self.encrypted = self.root / "source.dump.enc"
        self.source.write_bytes(b"synthetic pg_dump bytes; no private data")
        self.env = {eb.KEY_ENV: "ab" * 32}

    def tearDown(self):
        self.temp.cleanup()

    def test_round_trip_authenticates_and_removes_plaintext(self):
        manifest = eb.encrypt_backup(self.source, self.encrypted, environ=self.env,
                                     remove_plaintext=True)
        self.assertFalse(self.source.exists())
        self.assertEqual(eb.verify_backup(self.encrypted, manifest, environ=self.env)["verified"], True)
        with eb.decrypted_backup(self.encrypted, manifest, environ=self.env) as restored:
            self.assertEqual(restored.read_bytes(), b"synthetic pg_dump bytes; no private data")
        self.assertFalse(restored.exists())

    def test_wrong_key_and_corruption_fail_closed(self):
        manifest = eb.encrypt_backup(self.source, self.encrypted, environ=self.env)
        with self.assertRaises(eb.EncryptedBackupError):
            eb.verify_backup(self.encrypted, manifest, environ={eb.KEY_ENV: "cd" * 32})
        corrupted = self.encrypted.read_bytes()[:-1] + bytes([self.encrypted.read_bytes()[-1] ^ 1])
        self.encrypted.write_bytes(corrupted)
        with self.assertRaises(eb.EncryptedBackupError):
            eb.verify_backup(self.encrypted, manifest, environ=self.env)

    def test_key_validation_and_safe_paths(self):
        for value in ("", "00", "zz" * 32, "0" * 66):
            with self.subTest(value=value), self.assertRaises(eb.EncryptedBackupError):
                eb.encrypt_backup(self.source, self.encrypted, environ={eb.KEY_ENV: value})
        with self.assertRaises(eb.EncryptedBackupError):
            eb.encrypt_backup(self.source, self.source, environ=self.env)

    def test_manifest_contains_no_secret_or_payload(self):
        manifest = eb.encrypt_backup(self.source, self.encrypted, environ=self.env)
        rendered = json.dumps(manifest)
        self.assertNotIn(self.env[eb.KEY_ENV], rendered)
        self.assertNotIn("synthetic pg_dump bytes", rendered)
        self.assertEqual(set(manifest), {
            "format", "encryption", "encrypted_size_bytes", "plaintext_size_bytes",
            "sha256", "created_at", "expected_restore_type",
        })

    def test_backup_class_is_explicit_and_controls_restore_target_type(self):
        founder = eb.encrypt_backup(self.source, self.encrypted, environ=self.env, backup_class="founder_state")
        self.assertEqual(founder["backup_class"], "founder_state")
        self.assertEqual(founder["expected_restore_type"], "existing_migrated_schema")
        self.encrypted.unlink()
        integrity = eb.encrypt_backup(self.source, self.encrypted, environ=self.env, backup_class="integrity")
        self.assertEqual(integrity["backup_class"], "integrity")
        self.assertEqual(integrity["expected_restore_type"], "fresh_public_schema")

    def test_backup_size_cap_fails_closed(self):
        with patch.object(eb, "MAX_BACKUP_BYTES", 1):
            with self.assertRaisesRegex(eb.EncryptedBackupError, "exceeds configured size cap"):
                eb.encrypt_backup(self.source, self.encrypted, environ=self.env)


if __name__ == "__main__":
    unittest.main()
