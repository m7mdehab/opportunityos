"""Manifest-only provider-exit contract; never copies private backup bytes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

from scripts import db_migration_restore as db
from scripts import artifact_integrity


CONFIG_CONTRACT = {
    "required_runtime_names": ["OPPORTUNITYOS_DB_URL", "OPPORTUNITYOS_FOUNDER_PASSWORD",
                               "OPPORTUNITYOS_SESSION_SECRET"],
    "optional_runtime_names": ["OPPORTUNITYOS_HIGH_FIT_THRESHOLD",
                               "OPPORTUNITYOS_TRUTH_PACK_PATH",
                               "OPPORTUNITYOS_FORCE_SECURE_COOKIES"],
    "provider_credentials": "inject separately; values excluded",
    "private_truth": "transfer through separately approved encrypted procedure",
}


def create(backup, backup_manifest, artifact_manifest, output):
    paths = [Path(p).expanduser().resolve() for p in (backup, backup_manifest, artifact_manifest)]
    destination = Path(output).expanduser().resolve()
    if (destination.exists() or not destination.parent.is_dir()
            or any(not path.is_file() or path.parent != destination.parent for path in paths)
            or len({path.name for path in paths}) != 3):
        raise db.HarnessError("bundle files must be distinct and colocated in an existing directory")
    backup_info = db.verify_backup(paths[0], paths[1])
    with paths[2].open(encoding="utf-8") as stream:
        artifacts = json.load(stream)
    artifact_integrity.validate_manifest(artifacts)
    bundle = {"format": 1, "schema": "public",
              "alembic_revision": backup_info.get("alembic_revision"),
              "application_commit": backup_info.get("application_commit"),
              "config_contract": CONFIG_CONTRACT,
              "files": {kind: {"name": path.name, "size_bytes": path.stat().st_size,
                               "sha256": db.file_sha256(path)}
                        for kind, path in zip(("postgres_backup", "backup_manifest", "artifact_manifest"), paths)}}
    if not bundle["alembic_revision"] or not re.fullmatch(r"[0-9a-f]{40}", str(bundle["application_commit"])):
        raise db.HarnessError("bundle revision contract incomplete")
    with destination.open("x", encoding="utf-8") as stream:
        json.dump(bundle, stream, sort_keys=True, separators=(",", ":"))
        stream.write("\n")
    return bundle


def verify(bundle_path):
    path = Path(bundle_path).expanduser().resolve()
    with path.open(encoding="utf-8") as stream:
        bundle = json.load(stream)
    if (not isinstance(bundle, dict) or bundle.get("format") != 1
            or bundle.get("config_contract") != CONFIG_CONTRACT
            or set(bundle.get("files", {})) != {"postgres_backup", "backup_manifest", "artifact_manifest"}):
        raise db.HarnessError("provider-exit bundle contract mismatch")
    resolved = {}
    for kind, entry in bundle["files"].items():
        if (not isinstance(entry, dict) or not isinstance(entry.get("name"), str)
                or Path(entry["name"]).name != entry["name"]
                or not isinstance(entry.get("size_bytes"), int)
                or not re.fullmatch(r"[0-9a-f]{64}", str(entry.get("sha256")))):
            raise db.HarnessError("provider-exit file entry invalid")
        file = path.parent / entry["name"]
        if not file.is_file() or file.stat().st_size != entry["size_bytes"] or db.file_sha256(file) != entry["sha256"]:
            raise db.HarnessError("provider-exit file integrity mismatch")
        resolved[kind] = file
    info = db.verify_backup(resolved["postgres_backup"], resolved["backup_manifest"])
    if (info.get("alembic_revision") != bundle.get("alembic_revision")
            or info.get("application_commit") != bundle.get("application_commit")):
        raise db.HarnessError("provider-exit revision mismatch")
    with resolved["artifact_manifest"].open(encoding="utf-8") as stream:
        artifact_integrity.validate_manifest(json.load(stream))
    return bundle


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    export = sub.add_parser("create")
    export.add_argument("--backup", required=True)
    export.add_argument("--backup-manifest", required=True)
    export.add_argument("--artifact-manifest", required=True)
    export.add_argument("--output", required=True)
    check = sub.add_parser("verify")
    check.add_argument("--bundle", required=True)
    args = parser.parse_args(argv)
    try:
        if args.operation == "create":
            create(args.backup, args.backup_manifest, args.artifact_manifest, args.output)
        else:
            verify(args.bundle)
        print('{"status":"pass"}')
        return 0
    except (Exception, KeyboardInterrupt):
        print('{"status":"error","reason":"provider-exit bundle invalid"}', file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
