"""Provider-neutral private artifact cache and durable body storage."""
from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from sqlalchemy.orm import Session

from storage.models import ArtifactCacheRecord

MAX_CACHE_ROWS = 500
GENERATION_VERSION = "artifact-contract-v1"
BACKENDS = frozenset(("postgres_payload", "supabase_storage"))


class ArtifactStorageError(RuntimeError):
    """Safe storage failure without transport or credential text."""


def cache_key(opportunity_id: str, truth_pack_hash: str, template_id: str, artifact_kind: str) -> str:
    return hashlib.sha256("|".join((opportunity_id, truth_pack_hash, template_id, artifact_kind)).encode()).hexdigest()


def object_key_for(cache_key_value: str) -> str:
    if len(cache_key_value) != 64 or any(c not in "0123456789abcdefABCDEF" for c in cache_key_value):
        raise ArtifactStorageError("invalid canonical artifact identity")
    return f"artifacts/{cache_key_value.lower()}"


def configured_backend(environ=None) -> str:
    env = os.environ if environ is None else environ
    value = env.get("OPPORTUNITYOS_ARTIFACT_STORAGE_BACKEND", "").strip()
    cloud = env.get("OPPORTUNITYOS_ENVIRONMENT", "").lower() in {"cloud", "production", "prod"}
    if not value:
        if cloud:
            raise ArtifactStorageError("cloud artifact storage backend must be explicitly configured")
        return "postgres_payload"
    if value not in BACKENDS:
        raise ArtifactStorageError("unsupported artifact storage backend")
    return value


def validate_storage_config(environ=None) -> list[str]:
    env = os.environ if environ is None else environ
    try:
        backend = configured_backend(env)
    except ArtifactStorageError as exc:
        return [str(exc)]
    if backend == "supabase_storage":
        missing = [n for n in ("SUPABASE_STORAGE_URL", "SUPABASE_SERVICE_ROLE_KEY", "OPPORTUNITYOS_ARTIFACT_BUCKET") if not env.get(n)]
        if missing:
            return missing
        parsed = urlsplit(env["SUPABASE_STORAGE_URL"])
        if parsed.scheme != "https" or not parsed.hostname:
            return ["SUPABASE_STORAGE_URL"]
    return []


class SupabaseStorageClient:
    """Injectable server-side transport for a private Supabase Storage bucket."""

    def __init__(self, base_url=None, service_key=None, bucket=None, transport=None, timeout=10):
        self.base_url = base_url or os.environ.get("SUPABASE_STORAGE_URL", "")
        self.service_key = service_key or os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        self.bucket = bucket or os.environ.get("OPPORTUNITYOS_ARTIFACT_BUCKET", "")
        self.transport = transport
        self.timeout = timeout
        if not self.base_url or not self.service_key or not self.bucket:
            raise ArtifactStorageError("Supabase private storage configuration is incomplete")
        parsed = urlsplit(self.base_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ArtifactStorageError("Supabase storage URL must use HTTPS")

    def _url(self, key):
        return self.base_url.rstrip("/") + "/storage/v1/object/" + quote(self.bucket, safe="") + "/" + quote(key, safe="/")

    def _request(self, method, key, body=None):
        if self.transport is not None:
            try:
                return getattr(self.transport, method.lower())(key, body)
            except Exception as exc:
                raise ArtifactStorageError(f"private artifact {method.lower()} failed") from exc
        request = Request(self._url(key), data=body, method=method, headers={
            "Authorization": f"Bearer {self.service_key}", "apikey": self.service_key,
            "Content-Type": "application/octet-stream", "x-upsert": "false"})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return response.read()
        except Exception as exc:
            raise ArtifactStorageError(f"private artifact {method.lower()} failed") from exc

    def upload(self, key, body):
        self._request("POST", key, body)

    def get(self, key):
        result = self._request("GET", key)
        if not isinstance(result, (bytes, bytearray)):
            raise ArtifactStorageError("private artifact retrieval returned invalid bytes")
        return bytes(result)

    def delete(self, key):
        self._request("DELETE", key)


def _client(client=None):
    return client if client is not None else SupabaseStorageClient()


def _backend_for_row(row):
    return getattr(row, "storage_backend", None) or "postgres_payload"


def _verify_external(row, body):
    expected_size = getattr(row, "size_bytes", None)
    expected_hash = getattr(row, "payload_sha256", None)
    if expected_size is None or not expected_hash:
        raise ArtifactStorageError("external artifact metadata is incomplete")
    if len(body) != expected_size or hashlib.sha256(body).hexdigest() != expected_hash:
        raise ArtifactStorageError("external artifact checksum mismatch")
    return body


def get(session: Session, opportunity_id: str, truth_pack_hash: str, template_id: str, artifact_kind: str, *, storage_client=None):
    key = cache_key(opportunity_id, truth_pack_hash, template_id, artifact_kind)
    row = session.query(ArtifactCacheRecord).filter_by(cache_key=key).first()
    if row is None:
        return None
    backend = _backend_for_row(row)
    if backend == "postgres_payload":
        if row.payload is None:
            raise ArtifactStorageError("postgres artifact body is unavailable")
        return row.content_type, bytes(row.payload)
    if backend != "supabase_storage" or not row.object_key:
        raise ArtifactStorageError("artifact storage metadata is invalid")
    return row.content_type, _verify_external(row, _client(storage_client).get(row.object_key))


def _delete_external(row, client):
    if _backend_for_row(row) == "supabase_storage" and row.object_key:
        client.delete(row.object_key)


def store(session: Session, opportunity_id: str, truth_pack_hash: str, template_id: str,
          artifact_kind: str, content_type: str, payload: bytes, *, storage_client=None) -> None:
    key = cache_key(opportunity_id, truth_pack_hash, template_id, artifact_kind)
    if session.query(ArtifactCacheRecord).filter_by(cache_key=key).first() is not None:
        return
    backend = configured_backend()
    client = _client(storage_client) if backend == "supabase_storage" else None
    stale = session.query(ArtifactCacheRecord).filter(
        ArtifactCacheRecord.opportunity_id == opportunity_id,
        ArtifactCacheRecord.artifact_kind == artifact_kind,
        ArtifactCacheRecord.template_id == template_id,
        ArtifactCacheRecord.truth_pack_hash != truth_pack_hash).all()
    for row in stale:
        _delete_external(row, client)
    for row in stale:
        session.delete(row)
    body = bytes(payload)
    object_key = None
    uploaded = False
    if backend == "supabase_storage":
        object_key = object_key_for(key)
        client.upload(object_key, body)
        uploaded = True
    session.add(ArtifactCacheRecord(
        cache_key=key, opportunity_id=opportunity_id, truth_pack_hash=truth_pack_hash,
        template_id=template_id, artifact_kind=artifact_kind, content_type=content_type,
        payload=body if backend == "postgres_payload" else None, storage_backend=backend,
        object_key=object_key, payload_sha256=hashlib.sha256(body).hexdigest(), size_bytes=len(body),
        generation_version=GENERATION_VERSION, created_at=datetime.now(timezone.utc)))
    try:
        session.commit()
    except Exception as exc:
        session.rollback()
        if uploaded:
            try:
                client.delete(object_key)
            except Exception as cleanup_exc:
                raise ArtifactStorageError("artifact metadata failed and compensating cleanup failed") from cleanup_exc
        raise ArtifactStorageError("artifact metadata persistence failed") from exc
    total = session.query(ArtifactCacheRecord).count()
    if total > MAX_CACHE_ROWS:
        victims = session.query(ArtifactCacheRecord).order_by(ArtifactCacheRecord.created_at.asc()).limit(total - MAX_CACHE_ROWS).all()
        for victim in victims:
            _delete_external(victim, client)
        for victim in victims:
            session.delete(victim)
        session.commit()


def docx_kind(kind: str) -> str:
    return kind


def pdf_kind(kind: str) -> str:
    return f"{kind}-pdf"
