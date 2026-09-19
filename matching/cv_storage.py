"""Fetch and verify Founder-approved fixed CV PDFs."""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
from typing import Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from .cv_selector import CVVariant

class CVStorageError(RuntimeError):
    """Fixed-CV bytes could not be retrieved or verified."""

def verify_cv_bytes(variant: CVVariant, payload: bytes) -> bytes:
    if not payload:
        raise CVStorageError(f"fixed CV object is empty: {variant.filename}")
    if not payload.startswith(b"%PDF-"):
        raise CVStorageError(f"fixed CV object is not a PDF: {variant.filename}")
    digest = hashlib.sha256(payload).hexdigest()
    if digest != variant.sha256:
        raise CVStorageError(
            f"fixed CV integrity mismatch for {variant.filename}: expected {variant.sha256}, got {digest}"
        )
    return payload

def _local_cv_bytes(variant: CVVariant, directory: str) -> bytes:
    root = Path(directory).resolve()
    candidate = (root / variant.filename).resolve()
    if root not in candidate.parents:
        raise CVStorageError("fixed CV path escaped configured directory")
    try:
        return verify_cv_bytes(variant, candidate.read_bytes())
    except OSError as exc:
        raise CVStorageError(f"fixed CV is unavailable locally: {variant.filename}") from exc

def _supabase_cv_bytes(
    variant: CVVariant, *, base_url: str, service_key: str,
    bucket: str, timeout_seconds: float,
) -> bytes:
    base = base_url.rstrip("/")
    object_path = "/".join(quote(part, safe="") for part in variant.object_path.split("/"))
    bucket_path = quote(bucket, safe="")
    url = f"{base}/storage/v1/object/authenticated/{bucket_path}/{object_path}"
    request = Request(url, headers={
        "Authorization": f"Bearer {service_key}",
        "apikey": service_key,
        "User-Agent": "OpportunityOS-FixedCV/1.0",
    })
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = response.read()
    except HTTPError as exc:
        raise CVStorageError(f"fixed CV provider returned HTTP {exc.code}: {variant.filename}") from exc
    except URLError as exc:
        raise CVStorageError(f"fixed CV provider is unreachable: {variant.filename}") from exc
    except Exception as exc:
        raise CVStorageError(f"fixed CV retrieval failed: {variant.filename}") from exc
    return verify_cv_bytes(variant, payload)

def fetch_cv_bytes(
    variant: CVVariant, *, environ: Mapping[str, str] | None = None,
    timeout_seconds: float = 30.0,
) -> bytes:
    """Retrieve exact approved bytes. There is no generated-CV fallback."""
    env = os.environ if environ is None else environ
    local_dir = env.get("OPPORTUNITYOS_CV_DIR", "").strip()
    if local_dir:
        return _local_cv_bytes(variant, local_dir)

    base_url = (
        env.get("OPPORTUNITYOS_SUPABASE_URL", "").strip()
        or env.get("NEXT_PUBLIC_DATA_API_URL", "").strip()
    )
    service_key = env.get("STORAGE_SERVICE_KEY", "").strip()
    bucket = env.get("STORAGE_CV_BUCKET", "").strip() or "founder-cv-portfolio"

    if not base_url:
        raise CVStorageError(
            "fixed CV storage is not configured: OPPORTUNITYOS_SUPABASE_URL or NEXT_PUBLIC_DATA_API_URL is required"
        )
    if not base_url.startswith("https://"):
        raise CVStorageError("fixed CV Supabase URL must use HTTPS")
    if not service_key:
        raise CVStorageError("fixed CV storage is not configured: STORAGE_SERVICE_KEY is required")
    return _supabase_cv_bytes(
        variant, base_url=base_url, service_key=service_key,
        bucket=bucket, timeout_seconds=timeout_seconds,
    )
