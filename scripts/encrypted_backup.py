"""Authenticated encryption contract for FR-007 logical PostgreSQL backups.

The database dump is created by :mod:`scripts.db_migration_restore`.  This
module encrypts that dump before it is persisted in an Actions artifact.  The
key is supplied only through ``BACKUP_ENCRYPTION_KEY`` and is never accepted
as a command line argument or written to a manifest.

The file format is intentionally small and provider neutral::

    OPOSBK01 | 12-byte AES-GCM nonce | AES-GCM ciphertext+tag

AES-GCM authenticates the header and ciphertext.  If the optional
``cryptography`` dependency is unavailable, operations fail closed rather than
falling back to unauthenticated encryption.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import tempfile


MAGIC = b"OPOSBK01"
NONCE_BYTES = 12
KEY_ENV = "BACKUP_ENCRYPTION_KEY"
MAX_BACKUP_BYTES = 200 * 1024 * 1024


class EncryptedBackupError(Exception):
    """A safe, redacted error for encrypted backup operations."""


def _aesgcm():
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as exc:  # pragma: no cover - dependency is tested in CI
        raise EncryptedBackupError("authenticated encryption dependency unavailable") from exc
    return AESGCM


def encryption_key(environ=None) -> bytes:
    env = os.environ if environ is None else environ
    value = env.get(KEY_ENV, "")
    if len(value) != 64:
        raise EncryptedBackupError("BACKUP_ENCRYPTION_KEY must be exactly 64 hexadecimal characters")
    try:
        return bytes.fromhex(value)
    except ValueError as exc:
        raise EncryptedBackupError("BACKUP_ENCRYPTION_KEY must be hexadecimal") from exc


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _validate_paths(source, destination):
    source_path = Path(source).expanduser().resolve()
    destination_path = Path(destination).expanduser().resolve()
    if source_path == destination_path:
        raise EncryptedBackupError("encrypted backup destination must differ from plaintext input")
    if not source_path.is_file() or source_path.stat().st_size <= 0:
        raise EncryptedBackupError("plaintext backup is missing or empty")
    if source_path.stat().st_size > MAX_BACKUP_BYTES:
        raise EncryptedBackupError("backup exceeds configured size cap")
    if destination_path.exists():
        raise EncryptedBackupError("encrypted backup destination already exists")
    if not destination_path.parent.is_dir():
        raise EncryptedBackupError("encrypted backup destination directory is unavailable")
    return source_path, destination_path


def encrypt_backup(source, destination, *, environ=None, remove_plaintext=False, backup_class=None) -> dict:
    """Encrypt a dump and return a sanitized integrity manifest.

    The destination is written atomically and never overwrites an existing
    file.  ``remove_plaintext`` is opt-in so callers can verify the encrypted
    file before deleting the source; production workflows should set it.
    """
    source_path, destination_path = _validate_paths(source, destination)
    if backup_class not in (None, "founder_state", "integrity"):
        raise EncryptedBackupError("backup class is unsupported")
    AESGCM = _aesgcm()
    key = encryption_key(environ)
    nonce = secrets.token_bytes(NONCE_BYTES)
    plaintext_size = source_path.stat().st_size
    temporary = destination_path.with_name(f".{destination_path.name}.partial")
    if temporary.exists():
        raise EncryptedBackupError("temporary encrypted backup path already exists")
    try:
        plaintext = source_path.read_bytes()
        ciphertext = AESGCM(key).encrypt(nonce, plaintext, MAGIC)
        with temporary.open("xb") as stream:
            stream.write(MAGIC)
            stream.write(nonce)
            stream.write(ciphertext)
        temporary.replace(destination_path)
    except EncryptedBackupError:
        temporary.unlink(missing_ok=True)
        raise
    except Exception as exc:
        temporary.unlink(missing_ok=True)
        raise EncryptedBackupError("encrypted backup creation failed") from exc
    if remove_plaintext:
        try:
            source_path.unlink()
        except OSError as exc:
            destination_path.unlink(missing_ok=True)
            raise EncryptedBackupError("plaintext backup could not be removed") from exc
    manifest = {
        "format": 1,
        "encryption": "AES-256-GCM",
        "encrypted_size_bytes": destination_path.stat().st_size,
        "plaintext_size_bytes": plaintext_size,
        "sha256": sha256_file(destination_path),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expected_restore_type": "existing_migrated_schema" if backup_class == "founder_state" else "fresh_public_schema",
    }
    if backup_class is not None:
        manifest["backup_class"] = backup_class
    return manifest


def _read_encrypted(path):
    path = Path(path).expanduser().resolve()
    if not path.is_file() or path.stat().st_size <= len(MAGIC) + NONCE_BYTES + 16:
        raise EncryptedBackupError("encrypted backup is missing or invalid")
    payload = path.read_bytes()
    if payload[:len(MAGIC)] != MAGIC:
        raise EncryptedBackupError("encrypted backup format is unsupported")
    return path, payload[len(MAGIC):len(MAGIC) + NONCE_BYTES], payload[len(MAGIC) + NONCE_BYTES:]


def verify_backup(path, manifest, *, environ=None) -> dict:
    """Verify file checksum and authenticate/decrypt it without persisting plaintext."""
    if not isinstance(manifest, dict) or manifest.get("format") != 1:
        raise EncryptedBackupError("encrypted backup manifest contract mismatch")
    if manifest.get("encryption") != "AES-256-GCM":
        raise EncryptedBackupError("encrypted backup encryption contract mismatch")
    archive, nonce, ciphertext = _read_encrypted(path)
    expected = manifest.get("sha256")
    if not isinstance(expected, str) or len(expected) != 64 or sha256_file(archive) != expected:
        raise EncryptedBackupError("encrypted backup checksum mismatch")
    if manifest.get("encrypted_size_bytes") != archive.stat().st_size:
        raise EncryptedBackupError("encrypted backup size mismatch")
    AESGCM = _aesgcm()
    try:
        AESGCM(encryption_key(environ)).decrypt(nonce, ciphertext, MAGIC)
    except Exception as exc:
        raise EncryptedBackupError("encrypted backup authentication failed") from exc
    return {"verified": True, "sha256": expected, "encrypted_size_bytes": archive.stat().st_size}


@contextmanager
def decrypted_backup(path, manifest, *, environ=None):
    """Yield a temporary plaintext dump for ``pg_restore`` and always delete it."""
    verify_backup(path, manifest, environ=environ)
    _, nonce, ciphertext = _read_encrypted(path)
    AESGCM = _aesgcm()
    try:
        plaintext = AESGCM(encryption_key(environ)).decrypt(nonce, ciphertext, MAGIC)
    except Exception as exc:
        raise EncryptedBackupError("encrypted backup authentication failed") from exc
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(prefix="opos-backup-", suffix=".dump", delete=False) as stream:
            temp_path = Path(stream.name)
            stream.write(plaintext)
        yield temp_path
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    enc = sub.add_parser("encrypt")
    enc.add_argument("--input", required=True)
    enc.add_argument("--output", required=True)
    enc.add_argument("--manifest", required=True)
    enc.add_argument("--remove-plaintext", action="store_true")
    enc.add_argument("--backup-class", choices=("founder_state", "integrity"))
    verify = sub.add_parser("verify")
    verify.add_argument("--archive", required=True)
    verify.add_argument("--manifest", required=True)
    args = parser.parse_args(argv)
    try:
        if args.operation == "encrypt":
            manifest = encrypt_backup(args.input, args.output, remove_plaintext=args.remove_plaintext,
                                      backup_class=args.backup_class)
            manifest_path = Path(args.manifest).expanduser().resolve()
            if manifest_path.exists() or not manifest_path.parent.is_dir():
                raise EncryptedBackupError("backup manifest destination must be new and writable")
            with manifest_path.open("x", encoding="utf-8") as stream:
                json.dump(manifest, stream, sort_keys=True, separators=(",", ":"))
                stream.write("\n")
            result = {"status": "ok", "encrypted": True, "manifest": "created"}
        else:
            try:
                with Path(args.manifest).open(encoding="utf-8") as stream:
                    manifest = json.load(stream)
            except (OSError, ValueError) as exc:
                raise EncryptedBackupError("encrypted backup manifest unavailable or invalid") from exc
            result = {"status": "ok", **verify_backup(args.archive, manifest)}
        print(json.dumps(result, sort_keys=True))
        return 0
    except EncryptedBackupError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
