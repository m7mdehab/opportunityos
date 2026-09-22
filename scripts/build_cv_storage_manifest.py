from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


def _record(source: Path, relative_source: str, object_key: str, kind: str, expected: str | None = None) -> dict[str, Any]:
    payload = source.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if expected and digest != expected:
        raise ValueError(f"canonical checksum mismatch for {relative_source}")
    if len(payload) > 10 * 1024 * 1024:
        raise ValueError(f"object exceeds the configured private-bucket limit: {relative_source}")
    return {
        "object_key": object_key,
        "source": relative_source.replace("\\", "/"),
        "kind": kind,
        "bytes": len(payload),
        "sha256": digest,
    }


def build_manifest(source_root: Path, package_zip: Path, repo_root: Path) -> dict[str, Any]:
    portfolio = yaml.safe_load((repo_root / "founder" / "cv_portfolio.yaml").read_text(encoding="utf-8"))
    source_root = source_root.resolve()
    cv_dir = source_root / "CVs"
    support_dir = source_root / "Supporting_Documents"
    entries: list[dict[str, Any]] = []

    for variant in portfolio["variants"]:
        pdf = _record(
            cv_dir / variant["filename"],
            f"CVs/{variant['filename']}",
            variant["object_path"],
            "canonical-pdf",
            variant["sha256"],
        )
        docx = _record(
            cv_dir / variant["docx_filename"],
            f"CVs/{variant['docx_filename']}",
            variant["docx_object_path"],
            "canonical-editable-docx",
            variant["docx_sha256"],
        )
        entries.extend((pdf, docx))

    support_files = sorted(path for path in support_dir.iterdir() if path.is_file())
    if len(support_files) != 11:
        raise ValueError(f"expected 11 canonical supporting documents, found {len(support_files)}")
    entries.append(_record(
        source_root / "MANIFEST.md",
        "MANIFEST.md",
        "2026/system/MANIFEST.md",
        "portfolio-manifest",
    ))
    for path in support_files:
        relative = f"Supporting_Documents/{path.name}"
        entries.append(_record(
            path,
            relative,
            f"2026/system/Supporting_Documents/{path.name}",
            "supporting-document",
        ))

    package_name = portfolio["source_pack"]["filename"]
    if package_zip.name != package_name:
        raise ValueError("source package filename does not match the canonical CV manifest")
    entries.append(_record(
        package_zip,
        package_name,
        f"2026/system/{package_name}",
        "canonical-source-package",
        portfolio["source_pack"]["sha256"],
    ))

    keys = [entry["object_key"] for entry in entries]
    if len(entries) != 31 or len(set(keys)) != len(keys):
        raise ValueError("canonical private portfolio must contain exactly 31 unique objects")
    return {
        "format_version": 1,
        "bucket": portfolio["storage"]["bucket"],
        "project_ref": "sunjfepvdzfknglrjwhm",
        "private": True,
        "object_count": len(entries),
        "total_bytes": sum(entry["bytes"] for entry in entries),
        "objects": entries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the hash manifest for the canonical private CV portfolio")
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--package-zip", required=True, type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    manifest = build_manifest(args.source_root, args.package_zip, args.repo_root)
    target = args.repo_root / "founder" / "cv_storage_objects.json"
    target.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "validated",
        "object_count": manifest["object_count"],
        "total_bytes": manifest["total_bytes"],
        "canonical_pdfs": sum(item["kind"] == "canonical-pdf" for item in manifest["objects"]),
        "editable_docx": sum(item["kind"] == "canonical-editable-docx" for item in manifest["objects"]),
        "supporting_documents": sum(item["kind"] == "supporting-document" for item in manifest["objects"]),
        "source_package_sha256": next(item["sha256"] for item in manifest["objects"] if item["kind"] == "canonical-source-package"),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
