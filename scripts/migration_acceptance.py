"""FR-007 migration acceptance report around the existing cutover harness.

Secrets are read from environment by the underlying harness. Only allowlisted
counts, hashes, states, and operational metadata enter the JSON report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import db_migration_restore as db
from scripts import migration_baseline as baseline
from scripts import production_db_preflight as preflight
from scripts import production_migration_cutover as cutover


# Capability needs are gate-level requirements, not claims that this command
# by itself closes a product gate. Ordered source/target access is separate.
GATE_NEEDS = {
    "A-0": (), "A-1": ("cloud_deployment",),
    "A-2": ("target_db", "cloud_deployment"),
    "A-3": ("target_db",), "A-4": ("target_db", "cloud_deployment"),
    "A-5": ("source_db", "target_db", "artifact_store", "cloud_deployment"),
    "A-6": ("source_db", "target_db", "cloud_deployment"),
    "A-7": ("target_db", "cloud_deployment"),
    "A-8": ("target_db", "cloud_deployment"),
    "A-9": ("source_db", "target_db"),
    "A-10": ("target_db", "cloud_deployment"),
    "A-11": ("target_db", "artifact_store", "cloud_deployment"),
    "A-12": ("target_db", "artifact_store", "cloud_deployment"),
    "A-13": ("cloud_deployment",),
    "A-14": ("cloud_deployment", "elapsed_soak_time"),
    "A-15": ("source_db", "target_db", "artifact_store"),
    "A-16": ("target_db", "artifact_store", "cloud_deployment"),
    "A-17": ("cloud_deployment",),
}
MIGRATION_GATES = ("A-6", "A-9", "A-11", "A-12", "A-15")
SCHEMA_GAPS = {"sources": "registry_is_committed_yaml_not_a_database_table",
               "source_states": "no_canonical_persisted_cadence_or_cooldown_table",
               "source_occurrences": "no_canonical_persisted_source_item_identity_table"}


def fingerprint(settings):
    identity = "\x00".join((settings["host"].lower(), settings["port"], settings["database"]))
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]


def _load_snapshot(path):
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) and value.get("format") == baseline.FORMAT else None
    except (OSError, ValueError):
        return None


def _gate_statuses(stages):
    gates = {name: {"status": "NOT_RUN", "executable_now": name in MIGRATION_GATES or name in
                    ("A-0", "A-3", "A-10"), "needs": list(needs)} for name, needs in GATE_NEEDS.items()}
    def status(name, components):
        states = [stages.get(part, "NOT_RUN") for part in components]
        if "FAIL" in states:
            gates[name]["status"] = "FAIL"
        elif "BLOCKED" in states:
            gates[name]["status"] = "BLOCKED"
        elif all(state == "NOT_RUN" for state in states):
            gates[name]["status"] = "NOT_RUN"
        else:
            # Migration checks are necessary but not sufficient for these
            # product gates; never manufacture a full gate PASS here.
            gates[name]["status"] = "PARTIAL"
    status("A-6", ("structural_parity",))
    status("A-9", ("structural_parity", "evaluation_parity", "triage_state_parity", "feed_projection_parity"))
    status("A-11", ("artifact_metadata", "artifact_body"))
    status("A-12", ("restore_import", "revision_verification", "artifact_body"))
    status("A-15", ("backup", "manifest_checksum", "restore_import", "structural_parity"))
    return gates


def assemble(raw, workspace, source=None, target=None, *, dry_run=False):
    source_snapshot = _load_snapshot(workspace / "source-baseline.json")
    target_snapshot = _load_snapshot(workspace / "target-baseline.json")
    tables = {}
    if source_snapshot and target_snapshot:
        for name in baseline.TABLES:
            source_count = source_snapshot["tables"].get(name)
            target_count = target_snapshot["tables"].get(name)
            tables[name] = {"source": source_count, "target": target_count,
                            "status": "PARTIAL" if source_count is None or target_count is None
                            else "PASS" if source_count == target_count else "FAIL"}
    manifest_path = workspace / "database.dump.manifest.json"
    checksum = None
    if manifest_path.is_file():
        try:
            checksum = db.verify_backup(workspace / "database.dump", manifest_path)["sha256"]
        except Exception:
            raw["stages"]["manifest_checksum"] = "FAIL"
            raw["status"] = "FAIL"
    stages = raw["stages"]
    gates = _gate_statuses(stages)
    critical = ("preflight", "source_baseline", "backup", "manifest_checksum",
                "fresh_target_validation", "target_migration", "restore_import",
                "revision_verification", "structural_parity", "evaluation_parity",
                "feed_projection_parity", "triage_state_parity", "artifact_metadata", "artifact_body")
    accepted = all(stages.get(name) == "PASS" for name in critical) and not raw.get("details", {}).get(
        "structural_parity", {}).get("unsupported")
    decision = "ACCEPT" if accepted else "REJECT"
    report = {"format": 1, "mode": "dry_run" if dry_run else "execute",
              "source_fingerprint": fingerprint(source) if source else None,
              "target_fingerprint": fingerprint(target) if target else None,
              "application_commit": None, "alembic_revision": {
                  "source": source_snapshot.get("alembic_revision") if source_snapshot else None,
                  "target": target_snapshot.get("alembic_revision") if target_snapshot else None},
              "backup_sha256": checksum, "stages": stages, "stage_details": raw.get("details", {}),
              "table_parity": tables,
              "evaluation_distributions": {
                  "source": source_snapshot.get("decision_distributions", {}).get("match_evaluations") if source_snapshot else None,
                  "target": target_snapshot.get("decision_distributions", {}).get("match_evaluations") if target_snapshot else None},
              "projection_counts": {
                  "source": source_snapshot.get("tables", {}).get("feed_projection") if source_snapshot else None,
                  "target": target_snapshot.get("tables", {}).get("feed_projection") if target_snapshot else None},
              "artifact_results": {name: raw.get("details", {}).get(name) for name in
                                   ("artifact_metadata", "artifact_body")},
              "unsupported_concepts": raw.get("details", {}).get("structural_parity", {}).get("unsupported", []),
              "schema_gap_explanations": SCHEMA_GAPS,
              "gates": gates, "decision": decision,
              "traffic_cutover_authorized": False,
              "rollback_decision": cutover.rollback_decision(raw)}
    try:
        report["application_commit"] = db.application_commit()
    except Exception:
        report["decision"] = "REJECT"
    return report


def run(directory, *, dry_run=False, connection_mode="unknown", artifact_backend="postgres_payload",
        confirm_restore=False, source_writes_paused=False, target_writes_disabled=False,
        allow_insecure_local=False, _test_hook=None):
    workspace = Path(directory).expanduser().resolve()
    try:
        source = db.config("source")
        target = db.target_config()
    except Exception:
        raw = cutover.report_template()
        cutover.record(raw, "preflight", "BLOCKED", {"reason": "configuration_failed"})
        raw = cutover.finish(raw)
        return assemble(raw, workspace)
    if dry_run:
        raw = cutover.report_template()
        checked = preflight.evaluate(target, connection_mode=connection_mode,
                                     allow_insecure_local=allow_insecure_local)
        cutover.record(raw, "preflight", checked["status"], checked)
        cutover.record(raw, "fresh_target_validation", checked.get("checks", {}).get("target_empty", "NOT_RUN"))
        if checked["ready"]:
            try:
                connection = db.connect(source)
                try:
                    snapshot = baseline.inspect(connection)
                finally:
                    connection.close()
                cutover.record(raw, "source_baseline", "PASS", {"revision": snapshot["alembic_revision"]})
                # Dry run does not persist a snapshot containing identity pairs.
                raw["details"]["source_baseline"]["row_count"] = snapshot["tables"]["opportunities"]
            except Exception:
                cutover.record(raw, "source_baseline", "FAIL", {"reason": "source_baseline_failed"})
        raw = cutover.finish(raw)
    else:
        raw = cutover.run(workspace, connection_mode=connection_mode, confirm_restore=confirm_restore,
                          source_writes_paused=source_writes_paused,
                          target_writes_disabled=target_writes_disabled,
                          allow_insecure_local=allow_insecure_local, artifact_backend=artifact_backend,
                          _test_hook=_test_hook)
    report = assemble(raw, workspace, source, target, dry_run=dry_run)
    if workspace.is_dir():
        path = workspace / "acceptance.json"
        if not path.exists():
            path.write_text(json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--connection-mode", choices=("direct", "pooler", "unknown"), required=True)
    parser.add_argument("--artifact-backend", default="postgres_payload")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--confirm-target-restore", action="store_true")
    parser.add_argument("--acknowledge-source-writes-paused", action="store_true")
    parser.add_argument("--acknowledge-target-writes-disabled", action="store_true")
    parser.add_argument("--allow-insecure-local", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = run(args.output_dir, dry_run=args.dry_run, connection_mode=args.connection_mode,
                     artifact_backend=args.artifact_backend, confirm_restore=args.confirm_target_restore,
                     source_writes_paused=args.acknowledge_source_writes_paused,
                     target_writes_disabled=args.acknowledge_target_writes_disabled,
                     allow_insecure_local=args.allow_insecure_local)
    except Exception:
        report = {"format": 1, "decision": "REJECT", "status": "FAIL", "reason": "acceptance_failed"}
    print(json.dumps(report, sort_keys=True))
    states = report.get("stages", {})
    return (0 if report["decision"] == "ACCEPT" else
            1 if "FAIL" in states.values() else 2 if "BLOCKED" in states.values() else 3)


if __name__ == "__main__":
    raise SystemExit(main())
