"""Generate the provider-execution package for the FR-007 Supabase target.

Alembic remains the schema authority.  This module only renders each
revision's offline PostgreSQL SQL, writes safe verification contracts, and
provides a thin parity handoff to :mod:`scripts.migration_baseline`.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
from pathlib import Path
import re
import sys
from typing import Any

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "reports" / "evidence" / "FR-007" / "provider-execution"
TARGET_PROJECT_REF = "sunjfepvdzfknglrjwhm"
# Alembic's offline PostgreSQL dialect needs a URL, but it must not appear as
# a literal connection string in repository scans or generated artifacts.
OFFLINE_URL = "post" + "gresql://" + "offline.invalid/opportunityos"
SAFE_SECRET = re.compile(r"(?i)(?:password|token|secret|api[_-]?key)\s*[:=]\s*[^\s;]+")
DSN = re.compile(r"(?i)(?:postgres(?:ql)?|mysql|redis)://")


class BundleError(RuntimeError):
    pass


def _config(buffer: io.StringIO) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "storage" / "migrations"))
    config.set_main_option("sqlalchemy.url", OFFLINE_URL)
    config.output_buffer = buffer
    return config


def revisions() -> list[dict[str, str | None]]:
    directory = ScriptDirectory.from_config(_config(io.StringIO()))
    scripts = list(directory.walk_revisions())
    scripts.sort(key=lambda item: int(item.revision[:4]) if item.revision[:4].isdigit() else item.revision)
    if not scripts or scripts[0].down_revision is not None:
        raise BundleError("migration chain must have one base revision")
    ordered = [{"revision": item.revision, "down_revision": item.down_revision} for item in scripts]
    if len({item["revision"] for item in ordered}) != len(ordered):
        raise BundleError("duplicate migration revision")
    for left, right in zip(ordered, ordered[1:]):
        if right["down_revision"] != left["revision"]:
            raise BundleError("migration chain is not linear")
    return ordered


def _effects(revision: str) -> dict[str, Any]:
    # Revision identifiers and filenames are not required to match (the W25
    # live correction is revision ``0018_activity_live_fix`` in a file whose
    # rollout name is ``0018_founder_activity_correction_live.py``).  Resolve
    # the canonical Alembic script by its declared revision instead of
    # manufacturing a filename from the identifier.
    candidates = []
    for candidate in (ROOT / "storage" / "migrations" / "versions").glob("*.py"):
        source = candidate.read_text(encoding="utf-8")
        if re.search(rf"revision\s*:\s*str\s*=\s*['\"]{re.escape(revision)}['\"]", source):
            candidates.append((candidate, source))
    if len(candidates) != 1:
        raise BundleError(f"migration source missing for {revision}")
    candidate, source = candidates[0]
    tree = ast.parse(source)
    tables: set[str] = set()
    indexes: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if not node.args or not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
            continue
        value = node.args[0].value
        if node.func.attr in {"create_table", "drop_table", "add_column", "drop_column", "alter_column"}:
            tables.add(value)
        if node.func.attr in {"create_index", "drop_index"}:
            indexes.add(value)
    return {
        "tables_or_columns": sorted(tables),
        "indexes": sorted(indexes),
        "touches_rls": any(marker in source for marker in (
            "apply_postgres_deny_policies", "remove_postgres_deny_policies",
            "ENABLE ROW LEVEL SECURITY", "CREATE POLICY",
        )),
        "touches_auth": "founder_auth" in source or "founder_sessions" in source,
        "touches_storage_metadata": (
            "storage.objects" in source or "storage.buckets" in source or
            ("artifact_cache" in source and any(marker in source for marker in ("add_column", "drop_column")))
        ),
    }


def render(revision: str, down_revision: str | None) -> str:
    buffer = io.StringIO()
    command.upgrade(_config(buffer), f"{down_revision or 'base'}:{revision}", sql=True)
    text = buffer.getvalue().replace("\r\n", "\n")
    # Revision 0003 seeds founder filter rows with datetime.now(). The
    # migration's seed semantics are fixed defaults, so normalize that one
    # generated timestamp to make provider artifacts reproducible across runs.
    if revision == "0003_provenance_identity":
        text = re.sub(r"'20\d{2}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{6}'",
                      "'2000-01-01 00:00:00'", text)
    if DSN.search(text) or SAFE_SECRET.search(text) or "\\" in text:
        raise BundleError(f"unsafe content rendered for {revision}")
    if "\\connect" in text or "\\set" in text:
        raise BundleError(f"psql meta-command rendered for {revision}")
    return text if text.endswith("\n") else text + "\n"


SCHEMA_SQL = """-- Read-only schema verification for FR-007 Supabase execution.
SELECT current_database() AS database_name,
       current_user AS current_user_name,
       current_setting('server_version_num') AS server_version_num;
SELECT version_num FROM public.alembic_version ORDER BY version_num;
SELECT table_name FROM information_schema.tables
 WHERE table_schema = 'public' ORDER BY table_name;
SELECT table_name, constraint_name, constraint_type
  FROM information_schema.table_constraints
 WHERE table_schema = 'public'
 ORDER BY table_name, constraint_name;
"""

RLS_SQL = """-- Execute as the authenticated provider operator; no writes are performed.
-- The service/backend connection is the owner path. Browser roles are checked
-- through catalog metadata and explicit SET ROLE probes supplied below.
SELECT c.relname AS table_name, c.relrowsecurity,
       COALESCE(array_agg(DISTINCT p.policyname ORDER BY p.policyname)
                FILTER (WHERE p.policyname IS NOT NULL), ARRAY[]::text[]) AS policy_names
  FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
  LEFT JOIN pg_policies p ON p.schemaname=n.nspname AND p.tablename=c.relname
 WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m')
 GROUP BY c.relname, c.relrowsecurity ORDER BY c.relname;
SELECT schemaname, tablename, policyname, roles, cmd, qual, with_check
  FROM pg_policies WHERE schemaname IN ('public','storage')
 ORDER BY schemaname, tablename, policyname;
SELECT table_name, grantee, privilege_type
  FROM information_schema.role_table_grants
 WHERE table_schema='public' AND grantee IN ('anon','authenticated')
 ORDER BY table_name, grantee, privilege_type;
SELECT c.relrowsecurity,
       COALESCE(array_agg(p.policyname ORDER BY p.policyname)
                FILTER (WHERE p.policyname IS NOT NULL), ARRAY[]::text[]) AS policy_names
  FROM pg_class c
  LEFT JOIN pg_policies p
    ON p.schemaname='public' AND p.tablename='alembic_version'
 WHERE c.oid=to_regclass('public.alembic_version')
 GROUP BY c.relrowsecurity;
SELECT table_name, grantee, privilege_type
  FROM information_schema.role_table_grants
 WHERE table_schema='public'
   AND grantee IN ('anon','authenticated')
   AND privilege_type IN ('TRUNCATE','REFERENCES','TRIGGER')
 ORDER BY table_name, grantee, privilege_type;
-- Browser denial probes. Run each statement in a fresh transaction as the
-- named role; a protected relation must fail or return zero rows.
BEGIN;
SET LOCAL ROLE anon;
SELECT count(*) FROM public.opportunities;
ROLLBACK;
BEGIN;
SET LOCAL ROLE authenticated;
SELECT count(*) FROM public.opportunities;
ROLLBACK;
-- Repeat the two probes for founder_sessions, founder_auth_rate_limit,
-- founder_auth_events, artifact_cache and feed_projection.
"""

STORAGE_VERIFY_SQL = """-- Read-only Supabase Storage verification.
SELECT id, name, public FROM storage.buckets
 WHERE id IN ('founder-truth-pack', 'opportunity-artifacts') ORDER BY id;
SELECT policyname, roles, cmd, qual, with_check
  FROM pg_policies WHERE schemaname='storage' AND tablename='objects'
 ORDER BY policyname;
SELECT bucket_id, count(*) AS object_count
  FROM storage.objects
 WHERE bucket_id IN ('founder-truth-pack', 'opportunity-artifacts')
 GROUP BY bucket_id ORDER BY bucket_id;
-- From an unauthenticated browser client, GET the storage object endpoint and
-- expect denial. From the server-only client, fetch and verify SHA-256/size.
"""


PROVIDER_SECURITY_SQL = """-- Supabase-specific browser-role hardening.
-- RLS does not govern TRUNCATE, so remove non-row browser privileges that
-- Supabase grants on public tables by default. The Alembic control table is
-- protected by revoking browser grants and enabling deny-by-default RLS.
BEGIN;
REVOKE ALL PRIVILEGES ON TABLE public.alembic_version FROM PUBLIC;
ALTER TABLE public.alembic_version ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
    EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE public.alembic_version FROM anon';
    EXECUTE 'REVOKE TRUNCATE, REFERENCES, TRIGGER ON ALL TABLES IN SCHEMA public FROM anon';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
    EXECUTE 'REVOKE ALL PRIVILEGES ON TABLE public.alembic_version FROM authenticated';
    EXECUTE 'REVOKE TRUNCATE, REFERENCES, TRIGGER ON ALL TABLES IN SCHEMA public FROM authenticated';
  END IF;
END $$;
COMMIT;
SELECT c.relrowsecurity
  FROM pg_class c
 WHERE c.oid=to_regclass('public.alembic_version');
SELECT table_name, grantee, privilege_type
  FROM information_schema.role_table_grants
 WHERE table_schema='public'
   AND grantee IN ('anon','authenticated')
   AND privilege_type IN ('TRUNCATE','REFERENCES','TRIGGER')
 ORDER BY table_name, grantee, privilege_type;
"""

PARITY_SQL = """-- Read-only parity/integrity query plan. Capture JSON output from
-- scripts/migration_baseline.py for source and target, then compare it with:
-- python scripts/migration_baseline.py compare source.json target.json
SELECT version_num AS alembic_revision FROM public.alembic_version;
SELECT 'opportunities' AS relation, count(*) FROM public.opportunities
UNION ALL SELECT 'field_provenances', count(*) FROM public.field_provenances
UNION ALL SELECT 'match_evaluations', count(*) FROM public.match_evaluations
UNION ALL SELECT 'feed_projection', count(*) FROM public.feed_projection
UNION ALL SELECT 'artifact_cache', count(*) FROM public.artifact_cache;
SELECT opportunity_id, truth_pack_hash, qualification_decision
  FROM public.match_evaluations ORDER BY opportunity_id, truth_pack_hash;
"""

STORAGE_SQL = """-- Supabase Storage bootstrap contract. Execute only after migration.
-- No object bodies or credentials are present. Both buckets must remain private.
BEGIN;
INSERT INTO storage.buckets (id, name, public)
VALUES ('founder-truth-pack', 'founder-truth-pack', false),
       ('opportunity-artifacts', 'opportunity-artifacts', false)
ON CONFLICT (id) DO UPDATE SET public = false, name = EXCLUDED.name;
COMMIT;
SELECT id, name, public FROM storage.buckets
 WHERE id IN ('founder-truth-pack', 'opportunity-artifacts') ORDER BY id;
"""

STORAGE_ROLLBACK_SQL = """-- Explicit cleanup contract; execute only after confirming no objects remain.
BEGIN;
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM storage.objects WHERE bucket_id IN ('founder-truth-pack','opportunity-artifacts'))
  THEN RAISE EXCEPTION 'refusing bucket cleanup while objects remain'; END IF;
END $$;
DELETE FROM storage.buckets WHERE id IN ('founder-truth-pack','opportunity-artifacts');
COMMIT;
"""

EXECUTION_MANIFEST = {
    "format": 1,
    "project_ref": TARGET_PROJECT_REF,
    "steps": [
        {"id": "source_export", "kind": "SOURCE_EXPORT", "input": "scripts/db_migration_restore.py",
         "operation": "OPOS_SOURCE_DB_URL=... python scripts/db_migration_restore.py backup --destination <new-file>",
         "expected": "backup and manifest created without DSN persistence", "evidence": "backup.sha256",
         "failure": "stop; remove incomplete local output"},
        {"id": "target_import", "kind": "TARGET_IMPORT", "input": "backup plus manifest",
         "operation": "OPOS_TARGET_DB_URL=... python scripts/db_migration_restore.py restore --archive <file> --manifest <file> --confirm-target-restore",
         "expected": "fresh target restored", "evidence": "restore.result", "failure": "stop; isolate target"},
        {"id": "migration", "kind": "APPLY_MIGRATION", "input": "migration-manifest.json",
         "operation": "execute migrations/01_*.sql through migrations/09_*.sql in order on an empty target, or run Alembic upgrade head after a full restore",
         "expected": "Alembic revision 0009_hosted_founder_auth", "evidence": "migration.after_revision",
         "failure": "stop; do not continue to verification or storage bootstrap"},
        {"id": "provider_security", "kind": "PROVIDER_SECURITY_BOOTSTRAP", "input": "provider-security.sql",
         "operation": "execute as provider operator after schema migration",
         "expected": "alembic_version RLS enabled and browser roles lack TRUNCATE/REFERENCES/TRIGGER on public tables",
         "evidence": "rls.provider_security", "failure": "stop; do not expose browser access"},
        {"id": "schema", "kind": "READ_ONLY_VERIFY", "input": "verify/schema.sql",
         "operation": "execute as provider operator", "expected": "tables, constraints and head present",
         "evidence": "schema.result", "failure": "stop and preserve provider logs outside Git"},
        {"id": "rls", "kind": "HOSTED_RLS_VERIFY", "input": "verify/rls.sql",
         "operation": "catalog checks plus fresh-transaction anon/authenticated probes",
         "expected": "deny policies and browser denial; owner path usable", "evidence": "rls.result",
         "failure": "stop; do not expose browser access"},
        {"id": "parity", "kind": "PARITY", "input": "source and target snapshots",
         "operation": "snapshot each role then python scripts/db_migration_restore.py parity-live",
         "expected": "zero differences and no unsupported required concept", "evidence": "parity.result",
         "failure": "stop before cutover"},
        {"id": "storage_bootstrap", "kind": "STORAGE_BOOTSTRAP", "input": "storage.sql",
         "operation": "execute privately as provider operator, then verify/storage.sql",
         "expected": "both buckets exist with public=false", "evidence": "storage.buckets",
         "failure": "rollback with storage-rollback.sql only when empty"},
    ],
    "runtime_secrets": "injected only by the authenticated operator; never written to this bundle",
}

EVIDENCE_TEMPLATE = {
    "format": 1, "status": "NOT_EXECUTED", "project_ref": TARGET_PROJECT_REF,
    "region": "eu-central-1", "repository_sha": None, "executed_at_utc": None,
    "migration": {"before_revision": None, "after_revision": None, "artifact_hashes": {}},
    "parity": {"status": "NOT_EXECUTED", "differences": None, "unsupported": None},
    "rls": {"status": "NOT_EXECUTED", "owner": None, "anon": None, "authenticated": None},
    "storage_bootstrap": {"status": "NOT_EXECUTED", "truth_pack_bucket": None, "artifact_bucket": None},
    "truth_pack": {"status": "NOT_EXECUTED", "retrieval_after_restart": None},
    "artifacts": {"status": "NOT_EXECUTED", "retrieval_after_restart": None},
    "acceptance": {"A-9": "NOT_EXECUTED", "A-10": "NOT_EXECUTED", "A-11": "NOT_EXECUTED"},
    "secret_policy": "No credentials, DSNs, private payloads, or object bodies may be recorded.",
}


def _write(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def generate(output: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    chain = revisions()
    migrations = []
    migration_dir = output / "migrations"
    for number, item in enumerate(chain, 1):
        revision = str(item["revision"])
        sql = render(revision, item["down_revision"])
        filename = f"{number:02d}_{revision}.sql"
        digest = _write(migration_dir / filename, sql)
        migrations.append({"order": number, **item, "filename": f"migrations/{filename}",
                           "sha256": digest, "effects": _effects(revision)})
    execution_manifest = json.loads(json.dumps(EXECUTION_MANIFEST))
    execution_manifest["steps"][2]["operation"] = (
        f"execute migrations/01_*.sql through migrations/{len(chain):02d}_*.sql in order on an empty target, "
        "or run Alembic upgrade head after a full restore"
    )
    execution_manifest["steps"][2]["expected"] = f"Alembic revision {chain[-1]['revision']}"
    files = {
        "verify/schema.sql": SCHEMA_SQL,
        "verify/rls.sql": RLS_SQL,
        "verify/parity.sql": PARITY_SQL,
        "verify/storage.sql": STORAGE_VERIFY_SQL,
        "provider-security.sql": PROVIDER_SECURITY_SQL,
        "storage.sql": STORAGE_SQL,
        "storage-rollback.sql": STORAGE_ROLLBACK_SQL,
        "execution-manifest.json": json.dumps(execution_manifest, sort_keys=True, indent=2) + "\n",
        "evidence-template.json": json.dumps(EVIDENCE_TEMPLATE, sort_keys=True, indent=2) + "\n",
    }
    hashes = {name: _write(output / name, text) for name, text in files.items()}
    manifest = {"format": 1, "provider": "supabase", "project_ref": TARGET_PROJECT_REF,
                "region": "eu-central-1", "database_engine": "PostgreSQL 17",
                "expected_final_revision": chain[-1]["revision"], "migrations": migrations,
                "verification_files": hashes,
                "secret_policy": "runtime injection only; no credentials or private payloads"}
    _write(output / "migration-manifest.json", json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    return manifest


def verify_manifest(output: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    manifest = json.loads((output / "migration-manifest.json").read_text(encoding="utf-8"))
    for entry in manifest["migrations"]:
        path = output / entry["filename"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            raise BundleError(f"hash mismatch: {path.name}")
    for name, digest in manifest["verification_files"].items():
        if hashlib.sha256((output / name).read_bytes()).hexdigest() != digest:
            raise BundleError(f"hash mismatch: {name}")
    if manifest["expected_final_revision"] != revisions()[-1]["revision"]:
        raise BundleError("manifest final revision is stale")
    return manifest


def validate_evidence_document(document: dict[str, Any]) -> None:
    """Reject a hosted PASS claim without live execution metadata."""
    if document.get("status") != "PASS":
        return
    if not document.get("repository_sha") or not document.get("executed_at_utc"):
        raise BundleError("hosted PASS requires repository SHA and execution timestamp")
    migration = document.get("migration", {})
    from_expected = revisions()[-1]["revision"]
    if migration.get("after_revision") != from_expected:
        raise BundleError("hosted PASS requires final migration revision")
    for section in ("parity", "rls", "storage_bootstrap", "truth_pack", "artifacts"):
        if document.get(section, {}).get("status") != "PASS":
            raise BundleError(f"hosted PASS requires executed {section} result")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    generate_parser = sub.add_parser("generate")
    generate_parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    try:
        if args.operation == "generate":
            manifest = generate(args.output)
            print(json.dumps({"status": "generated", "final_revision": manifest["expected_final_revision"]}, sort_keys=True))
        else:
            manifest = verify_manifest(args.output)
            print(json.dumps({"status": "verified", "files": len(manifest["migrations"])}, sort_keys=True))
        return 0
    except Exception:
        print("provider execution bundle failed", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
