"""Read-only live proof for the single-Founder PostgREST JWT claim contract."""
from __future__ import annotations

import json
import os
import uuid

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text


def main() -> None:
    database_url = os.environ.get("OPPORTUNITYOS_DB_URL")
    if not database_url:
        raise SystemExit("OPPORTUNITYOS_DB_URL is required")
    config = Config("alembic.ini")
    expected_head = ScriptDirectory.from_config(config).get_current_head()
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                revision = connection.execute(
                    text("SELECT version_num FROM public.alembic_version LIMIT 1")
                ).scalar_one()
                founder_uid = connection.execute(
                    text("SELECT supabase_user_id FROM public.founder_identity WHERE id='singleton'")
                ).scalar_one_or_none()
                if revision != expected_head:
                    raise AssertionError("live database is not at the repository migration head")
                if not founder_uid:
                    raise AssertionError("single Founder Auth subject is not bound")

                connection.execute(text("SET LOCAL ROLE authenticated"))
                connection.execute(text("SELECT set_config('request.jwt.claim.sub', '', true)"))
                connection.execute(
                    text("SELECT set_config('request.jwt.claims', :claims, true)"),
                    {"claims": json.dumps({"sub": founder_uid, "role": "authenticated"})},
                )
                founder_ok = bool(
                    connection.execute(text("SELECT public.opos_is_founder()")).scalar_one()
                )
                founder_rows = int(connection.execute(text(
                    "SELECT count(*) FROM public.founder_feed_activity "
                    "WHERE is_stale=false AND visible=true"
                )).scalar_one())
                if not founder_ok or founder_rows <= 0:
                    raise AssertionError("authenticated Founder claims do not expose the current feed")

                connection.execute(
                    text("SELECT set_config('request.jwt.claims', :claims, true)"),
                    {"claims": json.dumps({"sub": str(uuid.uuid4()), "role": "authenticated"})},
                )
                nonfounder_ok = bool(
                    connection.execute(text("SELECT public.opos_is_founder()")).scalar_one()
                )
                nonfounder_rows = int(connection.execute(text(
                    "SELECT count(*) FROM public.founder_feed_activity "
                    "WHERE is_stale=false AND visible=true"
                )).scalar_one())
                if nonfounder_ok or nonfounder_rows != 0:
                    raise AssertionError("non-Founder JWT claims unexpectedly expose Founder feed rows")

                connection.execute(
                    text("SELECT set_config('request.jwt.claim.sub', :uid, true)"),
                    {"uid": founder_uid},
                )
                legacy_claim_ok = bool(
                    connection.execute(text("SELECT public.opos_is_founder()")).scalar_one()
                )
                if not legacy_claim_ok:
                    raise AssertionError("legacy PostgREST subject claim is no longer supported")
            finally:
                transaction.rollback()
    finally:
        engine.dispose()

    print(json.dumps({
        "status": "PASS",
        "revision": str(revision),
        "founder_json_claim": "PASS",
        "founder_visible_feed_rows": founder_rows,
        "nonfounder_json_claim": "DENIED",
        "nonfounder_visible_feed_rows": nonfounder_rows,
        "legacy_subject_claim": "PASS",
        "database_mutations": "none",
    }, sort_keys=True))


if __name__ == "__main__":
    main()
