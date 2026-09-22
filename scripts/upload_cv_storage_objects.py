from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class UploadObject:
    object_key: str
    payload: bytes
    content_type: str


def _safe_http_error_detail(exc: HTTPError, *, service_key: str) -> str:
    try:
        body = exc.read(4096).decode("utf-8", errors="replace")
        parsed = json.loads(body)
        if not isinstance(parsed, dict):
            return "request rejected"
        parts = [
            str(parsed[field])
            for field in ("error", "message", "statusCode")
            if parsed.get(field) is not None
        ]
        detail = ": ".join(parts) or "request rejected"
    except (AttributeError, OSError, UnicodeError, json.JSONDecodeError):
        detail = "request rejected"
    if service_key:
        detail = detail.replace(service_key, "[redacted]")
    detail = " ".join(detail.split())
    return detail[:180]


def _object_url(base_url: str, bucket: str, key: str) -> str:
    encoded_bucket = quote(bucket, safe="")
    encoded_key = "/".join(quote(part, safe="") for part in key.split("/"))
    return f"{base_url.rstrip('/')}/storage/v1/object/{encoded_bucket}/{encoded_key}"


def prepare_objects(
    manifest: dict,
    *,
    source_root: Path,
    package_zip: Path,
    base_url: str,
) -> list[UploadObject]:
    parsed_url = urlparse(base_url)
    if parsed_url.scheme != "https" or not parsed_url.hostname:
        raise ValueError("SUPABASE_URL must be an https URL")
    if parsed_url.hostname.split(".", 1)[0] != manifest.get("project_ref"):
        raise ValueError("Supabase URL does not match the canonical storage manifest")
    if manifest.get("bucket") != "founder-cv-portfolio" or manifest.get("private") is not True:
        raise ValueError("canonical private CV bucket metadata is invalid")

    source_root = source_root.resolve(strict=True)
    package_zip = package_zip.resolve(strict=True)
    objects = manifest.get("objects")
    if not isinstance(objects, list) or len(objects) != manifest.get("object_count"):
        raise ValueError("manifest object count is inconsistent")
    if len({item.get("object_key") for item in objects}) != len(objects):
        raise ValueError("manifest contains duplicate object keys")

    prepared: list[UploadObject] = []
    total_bytes = 0
    for item in objects:
        key = item.get("object_key", "")
        parts = key.split("/")
        if not key or any(part in {"", ".", ".."} for part in parts):
            raise ValueError("manifest contains an unsafe object key")

        if item.get("kind") == "canonical-source-package":
            source_path = package_zip
        else:
            relative_source = Path(item.get("source", ""))
            if relative_source.is_absolute() or ".." in relative_source.parts:
                raise ValueError("manifest contains an unsafe source path")
            source_path = (source_root / relative_source).resolve(strict=True)
            try:
                source_path.relative_to(source_root)
            except ValueError as exc:
                raise ValueError("manifest source escaped the canonical source directory") from exc

        payload = source_path.read_bytes()
        if len(payload) != item.get("bytes"):
            raise ValueError(f"canonical source size mismatch: {key}")
        if hashlib.sha256(payload).hexdigest() != item.get("sha256"):
            raise ValueError(f"canonical source checksum mismatch: {key}")
        content_type = mimetypes.guess_type(source_path.name)[0] or "application/octet-stream"
        prepared.append(UploadObject(key, payload, content_type))
        total_bytes += len(payload)

    if total_bytes != manifest.get("total_bytes"):
        raise ValueError("manifest total byte count is inconsistent")
    return prepared


def upload_objects(
    objects: list[UploadObject],
    *,
    base_url: str,
    bucket: str,
    service_key: str,
) -> dict[str, int]:
    if not service_key:
        raise ValueError("STORAGE_SERVICE_KEY is required")
    for item in objects:
        request = Request(
            _object_url(base_url, bucket, item.object_key),
            data=item.payload,
            method="POST",
            headers={
                "Authorization": f"Bearer {service_key}",
                "apikey": service_key,
                "Content-Type": item.content_type,
                "Cache-Control": "max-age=3600",
                "x-upsert": "true",
                "User-Agent": "OpportunityOS-Canonical-CV-Uploader/1.0",
            },
        )
        try:
            with urlopen(request, timeout=60) as response:
                if response.status not in (200, 201):
                    raise RuntimeError(f"private object upload returned HTTP {response.status}")
        except HTTPError as exc:
            detail = _safe_http_error_detail(exc, service_key=service_key)
            raise RuntimeError(f"private object upload returned HTTP {exc.code}: {detail}") from None
        except URLError:
            raise RuntimeError("private object upload transport failed") from None
    return {
        "objects_uploaded": len(objects),
        "bytes_uploaded": sum(len(item.payload) for item in objects),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload exact canonical CV artifacts to private Supabase Storage")
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--package-zip", required=True, type=Path)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "founder" / "cv_storage_objects.json",
    )
    args = parser.parse_args()

    base_url = os.environ.get("SUPABASE_URL", "").strip()
    service_key = os.environ.get("STORAGE_SERVICE_KEY", "").strip()
    if not service_key:
        raise SystemExit("STORAGE_SERVICE_KEY is required")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    prepared = prepare_objects(
        manifest,
        source_root=args.source_root,
        package_zip=args.package_zip,
        base_url=base_url,
    )
    result = upload_objects(
        prepared,
        base_url=base_url,
        bucket=manifest["bucket"],
        service_key=service_key,
    )
    print(json.dumps({"status": "pass", **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
