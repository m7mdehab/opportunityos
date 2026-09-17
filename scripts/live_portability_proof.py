"""Execute a sanitized FR-007 PostgreSQL portability proof in one command.

Requires two explicitly configured, distinct databases. The target public
schema must be empty. Reports never contain DSNs or database row contents.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import artifact_integrity as artifacts
from scripts import db_migration_restore as db
from scripts import portability_bundle as bundle


STAGES = (
    "backup_creation", "manifest_creation", "checksum_verification",
    "restore", "migration_revision", "structural_parity",
    "artifact_metadata", "artifact_body", "provider_exit_bundle",
)


def run(directory, *, confirmed=False):
    report = {"format": 1, "stages": {stage: "NOT_RUN" for stage in STAGES},
              "details": {}, "status": "NOT_RUN", "summary": "Proof not started"}
    def perform(name, action):
        try:
            state, detail = action()
            if state not in ("PASS", "PARTIAL", "FAIL"):
                raise ValueError("invalid proof state")
            report["stages"][name] = state
            report["details"][name] = detail
            return state != "FAIL"
        except db.HarnessError as exc:
            report["stages"][name] = "FAIL"
            report["details"][name] = {"reason": str(exc)}
            return False
        except Exception:
            report["stages"][name] = "FAIL"
            report["details"][name] = {"reason": "operation_failed"}
            return False

    if not confirmed:
        report["stages"]["restore"] = "FAIL"
        report["details"]["restore"] = {"reason": "explicit_restore_confirmation_required"}
        return finalize(report)
    workspace = Path(directory).expanduser().resolve()
    if not workspace.is_dir() or any(workspace.iterdir()):
        report["stages"]["backup_creation"] = "FAIL"
        report["details"]["backup_creation"] = {"reason": "output_directory_must_be_empty"}
        return finalize(report)
    try:
        source = db.config("source")
        target = db.target_config()
        source_state = db.inspect(source)
        db.inspect(target, require_empty=True)
        if source_state["alembic_revision"] is None:
            raise db.HarnessError("source revision unavailable")
    except Exception:
        report["stages"]["backup_creation"] = "FAIL"
        report["details"]["backup_creation"] = {"reason": "configuration_or_preflight_failed"}
        return finalize(report)

    archive = workspace / "database.dump"
    backup_manifest_path = workspace / "database.dump.manifest.json"
    artifact_manifest_path = workspace / "artifacts.json"
    bundle_path = workspace / "provider-exit.json"

    if perform("backup_creation", lambda: (db.backup(source, archive) or "PASS", {"archive": archive.name})):
        def make_manifest():
            info = db.backup_manifest(archive, source_state["alembic_revision"],
                                      version=db.tool_version("pg_dump"),
                                      commit=db.application_commit())
            db.write_backup_manifest(archive, info)
            return "PASS", {"manifest": backup_manifest_path.name}
        perform("manifest_creation", make_manifest)
    if report["stages"]["manifest_creation"] == "PASS":
        perform("checksum_verification", lambda: (
            db.verify_backup(archive, backup_manifest_path) and "PASS",
            {"checksum": "verified"}))
    if report["stages"]["checksum_verification"] == "PASS":
        perform("restore", lambda: (
            db.restore(target, archive, manifest=backup_manifest_path, confirmed=True) or "PASS",
            {"target": "fresh_public_schema"}))
    if report["stages"]["restore"] == "PASS":
        def revision():
            db.migrate(target)
            target_state = db.inspect(target)
            matched = target_state["alembic_revision"] == source_state["alembic_revision"]
            return ("PASS" if matched else "FAIL",
                    {"revisions_match": matched})
        perform("migration_revision", revision)
    if report["stages"]["migration_revision"] == "PASS":
        def parity():
            result = db.parity_live(source, target)
            state = "FAIL" if result["differences"] else "PARTIAL" if result["unsupported"] else "PASS"
            return state, {"difference_count": len(result["differences"]),
                           "unsupported": result["unsupported"]}
        perform("structural_parity", parity)

    expected = None
    if report["stages"]["restore"] == "PASS":
        def metadata():
            nonlocal expected
            expected = artifacts.manifest(artifacts.PostgresPayloadReader(source))
            artifacts.validate_manifest(expected)
            with artifact_manifest_path.open("x", encoding="utf-8") as stream:
                json.dump(expected, stream, sort_keys=True, separators=(",", ":"))
                stream.write("\n")
            actual = artifacts.manifest(artifacts.PostgresPayloadReader(target))
            source_keys = {item["cache_key"] for item in expected["artifacts"]}
            target_keys = {item["cache_key"] for item in actual["artifacts"]}
            matched = source_keys == target_keys
            return ("PASS" if matched else "FAIL",
                    {"referenced": len(source_keys), "target_metadata": len(target_keys),
                     "missing_metadata": len(source_keys - target_keys),
                     "unexpected_metadata": len(target_keys - source_keys)})
        perform("artifact_metadata", metadata)
    if expected is not None:
        def bodies():
            result = artifacts.verify(expected, artifacts.PostgresPayloadReader(target))
            state = ("FAIL" if result["missing"] or result["checksum_mismatch"] or result["unexpected"]
                     else "PARTIAL" if result["metadata_only"] else "PASS")
            return state, result
        perform("artifact_body", bodies)
    if (report["stages"]["checksum_verification"] == "PASS"
            and artifact_manifest_path.is_file()):
        def provider_exit():
            bundle.create(archive, backup_manifest_path, artifact_manifest_path, bundle_path)
            bundle.verify(bundle_path)
            return "PASS", {"bundle": bundle_path.name, "integrity": "verified"}
        perform("provider_exit_bundle", provider_exit)
    return finalize(report)


def finalize(report):
    states = set(report["stages"].values())
    report["status"] = "FAIL" if "FAIL" in states else "PARTIAL" if "PARTIAL" in states or "NOT_RUN" in states else "PASS"
    report["summary"] = ", ".join(f"{stage}={state}" for stage, state in report["stages"].items())
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--confirm-target-restore", action="store_true")
    parser.add_argument("--allow-partial", action="store_true",
                        help="Return zero for explicit PARTIAL proof in disposable CI only")
    args = parser.parse_args(argv)
    report = run(args.output_dir, confirmed=args.confirm_target_restore)
    print(json.dumps(report, sort_keys=True))
    if report["status"] == "PASS" or (report["status"] == "PARTIAL" and args.allow_partial):
        return 0
    return 3 if report["status"] == "PARTIAL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
