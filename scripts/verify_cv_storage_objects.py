from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


def _object_url(base_url: str, bucket: str, key: str) -> str:
    encoded_bucket = quote(bucket, safe="")
    encoded_key = "/".join(quote(part, safe="") for part in key.split("/"))
    return f"{base_url.rstrip('/')}/storage/v1/object/authenticated/{encoded_bucket}/{encoded_key}"


def verify_objects(manifest: dict, *, base_url: str, service_key: str) -> dict[str, int]:
    bucket = manifest["bucket"]
    total_downloaded = 0
    for item in manifest["objects"]:
        request = Request(
            _object_url(base_url, bucket, item["object_key"]),
            headers={
                "Authorization": f"Bearer {service_key}",
                "apikey": service_key,
                "User-Agent": "OpportunityOS-CV-Storage-Verifier/1.0",
            },
        )
        try:
            with urlopen(request, timeout=45) as response:
                payload = response.read()
        except HTTPError as exc:
            raise RuntimeError(f"private object verification returned HTTP {exc.code}") from exc
        except URLError as exc:
            raise RuntimeError("private object verification transport failed") from exc
        actual_sha = hashlib.sha256(payload).hexdigest()
        if len(payload) != item["bytes"] or actual_sha != item["sha256"]:
            raise RuntimeError(f"stored object integrity mismatch: {item['object_key']}")
        total_downloaded += len(payload)
    return {"objects_verified": len(manifest["objects"]), "bytes_downloaded": total_downloaded}


def main() -> int:
    base_url = os.environ.get("SUPABASE_URL", "").strip()
    service_key = os.environ.get("STORAGE_SERVICE_KEY", "").strip()
    if not base_url.startswith("https://") or not service_key:
        raise SystemExit("SUPABASE_URL and STORAGE_SERVICE_KEY are required")
    manifest_path = Path(__file__).resolve().parents[1] / "founder" / "cv_storage_objects.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    result = verify_objects(manifest, base_url=base_url, service_key=service_key)
    print(json.dumps({"status": "pass", **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
