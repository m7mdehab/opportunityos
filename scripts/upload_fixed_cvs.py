"""Upload the six Founder-approved fixed CV PDFs to private Supabase Storage.

Usage:
  python scripts/upload_fixed_cvs.py --dir "C:/path/to/cvs"

Required environment:
  OPPORTUNITYOS_SUPABASE_URL (or NEXT_PUBLIC_DATA_API_URL)
  STORAGE_SERVICE_KEY

The script validates every local SHA-256 before upload and downloads every
object after upload to prove the stored bytes still match the locked portfolio.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from matching.cv_selector import PORTFOLIO
from matching.cv_storage import CVStorageError, verify_cv_bytes


def _url(base_url: str, bucket: str, object_path: str, authenticated: bool) -> str:
    path = "/".join(quote(part, safe="") for part in object_path.split("/"))
    bucket_part = quote(bucket, safe="")
    middle = "authenticated/" if authenticated else ""
    return f"{base_url.rstrip('/')}/storage/v1/object/{middle}{bucket_part}/{path}"


def upload_one(
    source: Path, variant, *, base_url: str, service_key: str, bucket: str
) -> None:
    local = verify_cv_bytes(variant, source.read_bytes())
    upload = Request(
        _url(base_url, bucket, variant.object_path, False),
        data=local,
        method="POST",
        headers={
            "Authorization": f"Bearer {service_key}",
            "apikey": service_key,
            "Content-Type": "application/pdf",
            "x-upsert": "true",
            "User-Agent": "OpportunityOS-FixedCV-Uploader/1.0",
        },
    )
    try:
        with urlopen(upload, timeout=60) as response:
            response.read()
    except HTTPError as exc:
        raise CVStorageError(f"upload failed for {variant.filename}: HTTP {exc.code}") from exc
    except URLError as exc:
        raise CVStorageError(f"upload transport failed for {variant.filename}") from exc

    verify = Request(
        _url(base_url, bucket, variant.object_path, True),
        headers={
            "Authorization": f"Bearer {service_key}",
            "apikey": service_key,
            "User-Agent": "OpportunityOS-FixedCV-Uploader/1.0",
        },
    )
    try:
        with urlopen(verify, timeout=60) as response:
            remote = response.read()
    except HTTPError as exc:
        raise CVStorageError(f"verification download failed for {variant.filename}: HTTP {exc.code}") from exc
    except URLError as exc:
        raise CVStorageError(f"verification transport failed for {variant.filename}") from exc
    verify_cv_bytes(variant, remote)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Upload and verify the six locked OpportunityOS CVs")
    parser.add_argument("--dir", required=True, help="Directory containing the six final PDF filenames")
    parser.add_argument("--bucket", default=os.getenv("STORAGE_CV_BUCKET", "founder-cv-portfolio"))
    args = parser.parse_args(argv)

    base_url = (
        os.getenv("OPPORTUNITYOS_SUPABASE_URL", "").strip()
        or os.getenv("NEXT_PUBLIC_DATA_API_URL", "").strip()
    )
    service_key = os.getenv("STORAGE_SERVICE_KEY", "").strip()
    if not base_url or not base_url.startswith("https://"):
        parser.error("set OPPORTUNITYOS_SUPABASE_URL to the HTTPS Supabase project URL")
    if not service_key:
        parser.error("set STORAGE_SERVICE_KEY to a server-side Supabase service key")

    root = Path(args.dir)
    missing = [item.filename for item in PORTFOLIO if not (root / item.filename).is_file()]
    if missing:
        parser.error("missing required CV files: " + ", ".join(missing))

    for variant in PORTFOLIO:
        upload_one(root / variant.filename, variant, base_url=base_url, service_key=service_key, bucket=args.bucket)
        print(f"PASS {variant.variant}: {variant.filename} [{variant.sha256[:12]}...]")

    print(f"PASS uploaded and byte-verified {len(PORTFOLIO)} fixed CVs to {args.bucket}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
