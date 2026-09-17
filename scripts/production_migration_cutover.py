"""Explicit FR-007 migration rehearsal; never changes traffic or DNS.

The schema-bearing archive restores into an empty target. Alembic upgrade is
therefore applied only after restore, when the archive's revision is known.
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
from scripts import migration_baseline as baseline
from scripts import portability_bundle as bundle
from scripts import production_db_preflight as preflight


STAGES = ("preflight", "source_baseline", "backup", "manifest_checksum",
          "target_migration", "restore_import", "revision_verification",
          "structural_parity", "feed_projection_parity", "artifact_metadata",
          "artifact_body", "final_acceptance")
VALID = {"PASS", "PARTIAL", "NOT_RUN", "BLOCKED", "FAIL"}


def report_template():
    return {"format": 1, "stages": {name: "NOT_RUN" for name in STAGES},
            "details": {}, "status": "NOT_RUN", "rollback": "source_remains_authoritative"}


def record(report, stage, state, detail=None):
    if state not in VALID:
        raise ValueError("invalid migration state")
    report["stages"][stage] = state
    if detail is not None:
        report["details"][stage] = detail


def finish(report):
    states = {state for name, state in report["stages"].items() if name != "final_acceptance"}
    report["status"] = ("FAIL" if "FAIL" in states else "BLOCKED" if "BLOCKED" in states
                        else "PARTIAL" if "PARTIAL" in states or "NOT_RUN" in states else "PASS")
    record(report, "final_acceptance", report["status"] if report["status"] != "NOT_RUN" else "BLOCKED",
           {"traffic_cutover_authorized": False})
    return report


def rollback_decision(report, *, traffic_cutover_occurred=False):
    """Pure state decision: never changes DNS, writes, or database objects."""
    if traffic_cutover_occurred:
        return {"decision": "REVERSE_TRAFFIC_TO_SOURCE", "target": "ISOLATE",
                "source": "VERIFY_READINESS", "backup": "VERIFY_MANIFEST_BEFORE_RETRY"}
    if report["status"] in ("FAIL", "BLOCKED"):
        return {"decision": "KEEP_SOURCE_AUTHORITATIVE", "target": "ISOLATE",
                "source": "UNCHANGED", "backup": "VERIFY_MANIFEST_BEFORE_RETRY"}
    return {"decision": "AWAIT_OWNER_CUTOVER", "target": "KEEP_WRITES_DISABLED",
            "source": "AUTHORITATIVE", "backup": "PRESERVE_VERIFIED_COPY"}


def run(directory, *, connection_mode, confirm_restore=False, source_writes_paused=False,
        target_writes_disabled=False, allow_insecure_local=False, artifact_backend="postgres_payload"):
    report = report_template()
    try:
        source = db.config("source")
        target = db.target_config()
    except Exception:
        record(report, "preflight", "BLOCKED", {"reason": "configuration_failed"})
        return finish(report)
    checked = preflight.evaluate(target, connection_mode=connection_mode,
                                 allow_insecure_local=allow_insecure_local)
    record(report, "preflight", checked["status"], checked)
    if not checked["ready"]:
        return finish(report)
    if artifact_backend != "postgres_payload":
        record(report, "artifact_metadata", "PARTIAL", {"reason": "backend_unsupported"})
        record(report, "artifact_body", "BLOCKED", {"reason": "backend_unsupported"})
        return finish(report)
    if not (confirm_restore and source_writes_paused and target_writes_disabled):
        record(report, "source_baseline", "BLOCKED", {"reason": "explicit_cutover_prerequisites_missing"})
        return finish(report)
    workspace = Path(directory).expanduser().resolve()
    if not workspace.is_dir() or any(workspace.iterdir()):
        record(report, "source_baseline", "BLOCKED", {"reason": "output_directory_must_be_empty"})
        return finish(report)
    try:
        connection = db.connect(source)
        try:
            source_snapshot = baseline.inspect(connection)
        finally:
            connection.close()
        if source_snapshot["alembic_revision"] is None:
            raise db.HarnessError("source_revision_unavailable")
        (workspace / "source-baseline.json").write_text(
            json.dumps(source_snapshot, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        record(report, "source_baseline", "PASS", {"revision": source_snapshot["alembic_revision"]})
    except Exception:
        record(report, "source_baseline", "FAIL", {"reason": "source_baseline_failed"})
        return finish(report)

    archive = workspace / "database.dump"
    manifest_path = workspace / "database.dump.manifest.json"
    try:
        db.backup(source, archive)
        record(report, "backup", "PASS", {"archive": archive.name})
        manifest = db.backup_manifest(archive, source_snapshot["alembic_revision"],
                                      version=db.tool_version("pg_dump"), commit=db.application_commit())
        db.write_backup_manifest(archive, manifest)
        db.verify_backup(archive, manifest_path)
        record(report, "manifest_checksum", "PASS", {"manifest": manifest_path.name,
                                                        "checksum_verified": True})
    except Exception:
        record(report, "backup" if report["stages"]["backup"] != "PASS" else "manifest_checksum",
               "FAIL", {"reason": "backup_or_integrity_failed"})
        return finish(report)

    # The archive includes DDL and Alembic state. Running migrations on the
    # empty target now would violate the fresh-target restore contract.
    record(report, "target_migration", "NOT_RUN", {"reason": "schema_bearing_archive_restored_first"})
    try:
        db.restore(target, archive, manifest=manifest_path, confirmed=True)
        record(report, "restore_import", "PASS", {"fresh_target": True})
    except Exception:
        record(report, "restore_import", "FAIL", {"reason": "restore_failed"})
        return finish(report)
    try:
        db.migrate(target)
        revision = db.inspect(target)["alembic_revision"]
        expected_revision = source_snapshot["alembic_revision"]
        if revision != expected_revision:
            record(report, "target_migration", "FAIL", {"reason": "revision_diverged"})
            record(report, "revision_verification", "FAIL", {"revisions_match": False})
            return finish(report)
        record(report, "target_migration", "PASS", {"ordering": "after_schema_restore"})
        record(report, "revision_verification", "PASS", {"revisions_match": True})
    except Exception:
        record(report, "target_migration", "FAIL", {"reason": "migration_failed"})
        return finish(report)

    try:
        connection = db.connect(target)
        try:
            target_snapshot = baseline.inspect(connection)
        finally:
            connection.close()
        (workspace / "target-baseline.json").write_text(
            json.dumps(target_snapshot, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        differences = baseline.compare(source_snapshot, target_snapshot)
        unsupported = sorted(set(baseline.unsupported(source_snapshot)) |
                             set(baseline.unsupported(target_snapshot)))
        record(report, "structural_parity", "FAIL" if differences else "PARTIAL" if unsupported else "PASS",
               {"difference_count": len(differences), "unsupported": unsupported})
        if differences:
            return finish(report)
        feed = "feed_projection"
        if source_snapshot["tables"][feed] is None or target_snapshot["tables"][feed] is None:
            record(report, "feed_projection_parity", "PARTIAL", {"reason": "canonical_projection_unsupported"})
        else:
            matched = (source_snapshot["tables"][feed] == target_snapshot["tables"][feed]
                       and source_snapshot["decision_distributions"][feed] == target_snapshot["decision_distributions"][feed]
                       and all(source_snapshot["null_counts"][key] == target_snapshot["null_counts"][key]
                               for key in source_snapshot["null_counts"] if key.startswith(feed + ".")))
            record(report, "feed_projection_parity", "PASS" if matched else "FAIL",
                   {"count": target_snapshot["tables"][feed], "distributions_match": matched})
            if not matched:
                return finish(report)
    except Exception:
        record(report, "structural_parity", "FAIL", {"reason": "parity_inspection_failed"})
        return finish(report)

    try:
        expected = artifacts.manifest(artifacts.PostgresPayloadReader(source))
        actual = artifacts.manifest(artifacts.PostgresPayloadReader(target))
        (workspace / "artifacts.json").write_text(
            json.dumps(expected, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        metadata_match = ({row["cache_key"] for row in expected["artifacts"]} ==
                          {row["cache_key"] for row in actual["artifacts"]})
        record(report, "artifact_metadata", "PASS" if metadata_match else "FAIL",
               {"referenced": expected["referenced"], "target_referenced": actual["referenced"]})
        if not metadata_match:
            return finish(report)
        body = artifacts.verify(expected, artifacts.PostgresPayloadReader(target))
        body_state = ("FAIL" if any(body[key] for key in ("missing", "checksum_mismatch", "unexpected"))
                      else "PARTIAL" if body["metadata_only"] else "PASS")
        record(report, "artifact_body", body_state, body)
        if body_state == "FAIL":
            return finish(report)
        bundle_path = workspace / "provider-exit.json"
        bundle.create(archive, manifest_path, workspace / "artifacts.json", bundle_path)
        bundle.verify(bundle_path)
        report["details"]["provider_exit_bundle"] = {"integrity": "verified"}
    except Exception:
        record(report, "artifact_body", "FAIL", {"reason": "artifact_or_bundle_failed"})
        return finish(report)
    return finish(report)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--connection-mode", choices=("direct", "pooler", "unknown"), required=True)
    parser.add_argument("--artifact-backend", default="postgres_payload")
    parser.add_argument("--confirm-target-restore", action="store_true")
    parser.add_argument("--acknowledge-source-writes-paused", action="store_true")
    parser.add_argument("--acknowledge-target-writes-disabled", action="store_true")
    parser.add_argument("--allow-insecure-local", action="store_true")
    parser.add_argument("--allow-partial", action="store_true", help="CI fixture exit override; report stays PARTIAL")
    args = parser.parse_args(argv)
    result = run(args.output_dir, connection_mode=args.connection_mode,
                 confirm_restore=args.confirm_target_restore,
                 source_writes_paused=args.acknowledge_source_writes_paused,
                 target_writes_disabled=args.acknowledge_target_writes_disabled,
                 allow_insecure_local=args.allow_insecure_local, artifact_backend=args.artifact_backend)
    result["rollback_decision"] = rollback_decision(result)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "PASS" or args.allow_partial and result["status"] == "PARTIAL" else (
        3 if result["status"] == "PARTIAL" else 2 if result["status"] == "BLOCKED" else 1)


if __name__ == "__main__":
    raise SystemExit(main())
