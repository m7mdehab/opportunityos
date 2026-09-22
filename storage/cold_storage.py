"""Lossless, content-addressed cold source storage for Storage V2.

The database stores only the identity/checksum/object pointer.  Bytes live in
the already-provisioned private Supabase Storage bucket when configured.  A
small PostgreSQL fallback is retained for local/disposable tests and for
recovery before the bucket is available; hosted configuration is fail-closed
and must use private object storage.
"""
from __future__ import annotations

import hashlib
import json
import os
import zlib
from datetime import date, datetime
from enum import Enum
from typing import Any, Mapping

from api.artifact_cache import ArtifactStorageError, SupabaseStorageClient

ARCHIVE_VERSION = "v2"


def _json_default(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Enum):
        return str(value.value)
    raise TypeError(f"unsupported cold archive JSON value: {type(value).__name__}")


def archive_key(content_hash: str, opportunity_id: str | None = None) -> str:
    if len(content_hash) != 64 or any(c not in "0123456789abcdefABCDEF" for c in content_hash):
        raise ValueError("invalid content hash")
    normalized_hash = content_hash.lower()
    if opportunity_id is None:
        return f"cold-opportunities/{normalized_hash}.json.zlib"
    # The canonical content hash intentionally excludes source identity so
    # cross-source duplicates can still be grouped. Include a short identity
    # digest in the object path to prevent two distinct source records with
    # identical normalized content from colliding in Storage.
    identity_digest = hashlib.sha256(opportunity_id.encode("utf-8")).hexdigest()[:16]
    return f"cold-opportunities/{normalized_hash}/{identity_digest}.json.zlib"


def pack(payload: Mapping[str, Any]) -> tuple[bytes, str, int]:
    raw = json.dumps(
        dict(payload), ensure_ascii=False, separators=(",", ":"), sort_keys=True,
        default=_json_default,
    ).encode("utf-8")
    compressed = zlib.compress(raw, level=9)
    return compressed, hashlib.sha256(compressed).hexdigest(), len(raw)


def unpack(compressed: bytes, expected_sha256: str, *, opportunity_id: str, content_hash: str) -> dict[str, Any]:
    if hashlib.sha256(compressed).hexdigest() != expected_sha256:
        raise RuntimeError("cold archive checksum verification failed")
    try:
        payload = json.loads(zlib.decompress(compressed).decode("utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("cold archive payload is corrupt") from exc
    if not isinstance(payload, dict) or payload.get("opportunity_id") != opportunity_id or payload.get("content_hash") != content_hash:
        raise RuntimeError("cold archive identity verification failed")
    return payload


def hosted_storage_configured(environ=None) -> bool:
    env = os.environ if environ is None else environ
    return bool(env.get("STORAGE_SERVICE_KEY") or env.get("SUPABASE_SERVICE_ROLE_KEY"))


def client_from_env() -> SupabaseStorageClient:
    env = os.environ
    base = env.get("SUPABASE_STORAGE_URL") or env.get("SUPABASE_URL")
    key = env.get("SUPABASE_SERVICE_ROLE_KEY") or env.get("STORAGE_SERVICE_KEY")
    # Reuse the already-provisioned private artifact bucket by default.  A
    # fresh bucket would add an avoidable operational dependency during
    # emergency recovery; callers may still override it explicitly.
    bucket = env.get("STORAGE_PRIVATE_BUCKET") or env.get("OPPORTUNITYOS_ARTIFACT_BUCKET") or "opportunity-artifacts"
    if not base or not key:
        raise ArtifactStorageError("private cold storage configuration is incomplete")
    return SupabaseStorageClient(base_url=base, service_key=key, bucket=bucket)


def put(
    compressed: bytes,
    content_hash: str,
    *,
    opportunity_id: str | None = None,
    client: SupabaseStorageClient | None = None,
) -> tuple[str, str, int]:
    key = archive_key(content_hash, opportunity_id)
    storage = client or client_from_env()
    storage.upload(key, compressed)
    return key, hashlib.sha256(compressed).hexdigest(), len(compressed)


def get(object_key: str, expected_sha256: str, *, client: SupabaseStorageClient | None = None) -> bytes:
    storage = client or client_from_env()
    body = storage.get(object_key)
    if hashlib.sha256(body).hexdigest() != expected_sha256:
        raise RuntimeError("cold archive checksum verification failed")
    return body


def delete(object_key: str, *, client: SupabaseStorageClient | None = None) -> None:
    (client or client_from_env()).delete(object_key)
