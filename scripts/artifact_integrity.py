"""Provider-neutral artifact body inventory and retrieval verification.

Only the current canonical PostgreSQL payload backend is implemented. An
external object store has no canonical location column yet and is unsupported.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import db_migration_restore as db


KEY = re.compile(r"^[0-9a-fA-F]{64}$")


class UnsupportedBackend(db.HarnessError):
    pass


class PostgresPayloadReader:
    def __init__(self, settings):
        self.settings = settings

    def inventory(self):
        connection = db.connect(self.settings)
        cursor = connection.cursor()
        try:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            cursor.execute("SELECT column_name FROM information_schema.columns "
                           "WHERE table_schema='public' AND table_name='artifact_cache'")
            columns = {row[0] for row in cursor.fetchall()}
            if not {"cache_key", "payload"} <= columns:
                raise UnsupportedBackend("canonical artifact payload columns unavailable")
            cursor.execute("SELECT cache_key, payload FROM public.artifact_cache ORDER BY cache_key")
            rows = []
            while True:
                chunk = cursor.fetchmany(128)
                if not chunk:
                    break
                for key, payload in chunk:
                    if not isinstance(key, str) or not KEY.fullmatch(key):
                        raise db.HarnessError("invalid artifact identity metadata")
                    if payload is None or len(payload) == 0:
                        rows.append({"cache_key": key.lower(), "sha256": None,
                                     "size_bytes": None, "body_status": "metadata_only"})
                    else:
                        body = bytes(payload)
                        rows.append({"cache_key": key.lower(), "sha256": hashlib.sha256(body).hexdigest(),
                                     "size_bytes": len(body), "body_status": "retrievable"})
            cursor.execute("ROLLBACK")
            return rows
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()
            connection.close()


def manifest(reader):
    rows = reader.inventory()
    return {"format": 1, "backend": "postgres_payload", "referenced": len(rows),
            "retrievable": sum(row["body_status"] == "retrievable" for row in rows),
            "metadata_only": sum(row["body_status"] == "metadata_only" for row in rows),
            "artifacts": rows}


def validate_manifest(expected):
    if (not isinstance(expected, dict)
            or set(expected) != {"format", "backend", "referenced", "retrievable", "metadata_only", "artifacts"}
            or expected["format"] != 1 or expected["backend"] != "postgres_payload"
            or not isinstance(expected["artifacts"], list)):
        raise db.HarnessError("artifact manifest contract mismatch")
    seen = set()
    retrievable = metadata_only = 0
    for entry in expected["artifacts"]:
        if (not isinstance(entry, dict)
                or set(entry) != {"cache_key", "sha256", "size_bytes", "body_status"}
                or not isinstance(entry["cache_key"], str)
                or not KEY.fullmatch(entry["cache_key"])
                or entry["cache_key"] in seen):
            raise db.HarnessError("artifact manifest identity invalid")
        seen.add(entry["cache_key"])
        if entry["body_status"] == "retrievable":
            if (not isinstance(entry["sha256"], str)
                    or not KEY.fullmatch(entry["sha256"])
                    or not isinstance(entry["size_bytes"], int)
                    or entry["size_bytes"] <= 0):
                raise db.HarnessError("artifact body checksum invalid")
            retrievable += 1
        elif entry["body_status"] == "metadata_only":
            if entry["sha256"] is not None or entry["size_bytes"] is not None:
                raise db.HarnessError("metadata-only artifact contract invalid")
            metadata_only += 1
        else:
            raise db.HarnessError("artifact body status invalid")
    if (expected["referenced"] != len(seen) or expected["retrievable"] != retrievable
            or expected["metadata_only"] != metadata_only):
        raise db.HarnessError("artifact manifest counts mismatch")


def verify(expected, reader):
    validate_manifest(expected)
    actual = {row["cache_key"]: row for row in reader.inventory()}
    seen = set()
    counts = {"referenced": len(expected["artifacts"]), "retrievable": 0,
              "missing": 0, "checksum_mismatch": 0, "metadata_only": 0,
              "unexpected": 0}
    for entry in expected["artifacts"]:
        key = entry["cache_key"]
        seen.add(key)
        row = actual.get(key)
        if row is None:
            counts["missing"] += 1
        elif row["body_status"] == "metadata_only":
            if entry["body_status"] == "retrievable":
                counts["missing"] += 1
            else:
                counts["metadata_only"] += 1
        elif (entry.get("sha256") is not None and
              (row["sha256"] != entry["sha256"] or row["size_bytes"] != entry.get("size_bytes"))):
            counts["checksum_mismatch"] += 1
        elif entry["body_status"] == "metadata_only":
            counts["checksum_mismatch"] += 1
        else:
            counts["retrievable"] += 1
    counts["unexpected"] = len(set(actual) - seen)
    return counts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    inv = sub.add_parser("manifest")
    inv.add_argument("--role", choices=("source", "target"), required=True)
    inv.add_argument("--output", required=True)
    inv.add_argument("--backend", default="postgres_payload")
    check = sub.add_parser("verify")
    check.add_argument("--role", choices=("source", "target"), required=True)
    check.add_argument("--manifest", required=True)
    check.add_argument("--backend", default="postgres_payload")
    args = parser.parse_args(argv)
    try:
        if args.backend != "postgres_payload":
            raise UnsupportedBackend("external artifact location contract unavailable")
        settings = db.config("source") if args.role == "source" else db.target_config()
        reader = PostgresPayloadReader(settings)
        if args.operation == "manifest":
            result = manifest(reader)
            path = Path(args.output).expanduser().resolve()
            if path.exists() or not path.parent.is_dir():
                raise db.HarnessError("artifact manifest destination must be new")
            with path.open("x", encoding="utf-8") as stream:
                json.dump(result, stream, sort_keys=True, separators=(",", ":"))
                stream.write("\n")
            summary = {key: result[key] for key in ("referenced", "retrievable", "metadata_only")}
        else:
            with Path(args.manifest).open(encoding="utf-8") as stream:
                expected = json.load(stream)
            summary = verify(expected, reader)
        status = "unknown" if summary.get("metadata_only", 0) else "pass"
        if summary.get("missing", 0) or summary.get("checksum_mismatch", 0) or summary.get("unexpected", 0):
            status = "mismatch"
        print(json.dumps({"status": status, **summary}, sort_keys=True))
        return 1 if status == "mismatch" else 3 if status == "unknown" else 0
    except UnsupportedBackend:
        print('{"status":"unsupported","reason":"artifact backend or canonical location unavailable"}', file=sys.stderr)
        return 3
    except (Exception, KeyboardInterrupt):
        print('{"status":"error","reason":"artifact verification failed"}', file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
