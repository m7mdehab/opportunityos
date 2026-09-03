"""Tests for scripts/backup_restore.py.

Two-database approach: OPPORTUNITYOS_DB_URL names the "source" PostgreSQL
database; a second, distinct database on the same server
("opportunityos_restore_test") is dropped and recreated at class setup and
used as the restore target, then dropped again at teardown. Two databases
on one server were chosen over two schemas because CREATE DATABASE / DROP
DATABASE plus a plain sqlalchemy.url swap is the simplest way to guarantee
the restore path (which runs a real Alembic upgrade against the target URL)
exercises a target that starts with no schema at all, matching a real
disaster-recovery restore.

Fails (does not skip) when CI is truthy and OPPORTUNITYOS_DB_URL is missing
or not a PostgreSQL URL: a real PostgreSQL DSN is required in CI for this
module. Outside CI, when no PostgreSQL DSN is configured, the integration
test class is skipped with a visible reason.

The BackupCompletenessError test does not require PostgreSQL at all: the
completeness check runs before scripts.backup_restore.dump_database opens
any database connection, so it is exercised unconditionally.
"""
import os
import json
import unittest
import tempfile
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import create_engine, text, MetaData, Column, String
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic import command as alembic_command

from storage.engine import get_engine, get_session_factory
from storage.repository import StorageRepository
from storage.models import (
    Base,
    OpportunityRecord,
    FounderFeedbackRecord,
    MatchEvaluationRecord,
    SourcePollRunRecord,
    FounderOpportunityViewRecord,
    FounderTriageStateRecord,
    FounderFilterSettingRecord,
)
import scripts.backup_restore as backup_restore
from scripts.backup_restore import (
    dump_database,
    restore_database,
    BackupCompletenessError,
    ALEMBIC_INI_PATH,
)

TARGET_DB_NAME = "opportunityos_restore_test"


def _replace_db_name(url: str, db_name: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, "/" + db_name, parts.query, parts.fragment))


class TestBackupCompleteness(unittest.TestCase):
    """dump_database's completeness check, exercised without any database
    connection (it runs before the dump opens one)."""

    def test_dump_database_raises_when_mapping_disagrees_with_metadata(self):
        original_map = dict(backup_restore.DUMP_SECTION_TABLE_MAP)
        try:
            # Simulate a model table (e.g. a newly added one) missing from
            # the dump map, without touching the models themselves.
            patched_map = dict(original_map)
            del patched_map["opportunities"]
            backup_restore.DUMP_SECTION_TABLE_MAP = patched_map

            with self.assertRaises(BackupCompletenessError):
                dump_database("postgresql+psycopg2://unused/unused", os.devnull)
        finally:
            backup_restore.DUMP_SECTION_TABLE_MAP = original_map

    def test_dump_database_raises_when_mapping_names_unknown_table(self):
        original_map = dict(backup_restore.DUMP_SECTION_TABLE_MAP)
        try:
            patched_map = dict(original_map)
            patched_map["not_a_real_section"] = "not_a_real_table"
            backup_restore.DUMP_SECTION_TABLE_MAP = patched_map

            with self.assertRaises(BackupCompletenessError):
                dump_database("postgresql+psycopg2://unused/unused", os.devnull)
        finally:
            backup_restore.DUMP_SECTION_TABLE_MAP = original_map


class TestRestoreCompleteness(unittest.TestCase):
    """restore_database's completeness check, exercised without any database
    connection (it runs before the restore touches Alembic or the DB at
    all -- see _check_restore_completeness, called before _upgrade_to_head)."""

    @staticmethod
    def _write_dump(sections: dict) -> str:
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        payload = {"timestamp": "2026-01-01T00:00:00Z"}
        payload.update(sections)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        return path

    def test_restore_database_raises_when_dump_missing_a_known_section(self):
        sections = {key: [] for key in backup_restore.DUMP_SECTION_TABLE_MAP}
        del sections["opportunities"]
        path = self._write_dump(sections)
        try:
            with self.assertRaises(BackupCompletenessError):
                restore_database(path, "postgresql+psycopg2://unused/unused")
        finally:
            os.remove(path)

    def test_restore_database_raises_when_dump_has_an_unknown_section(self):
        sections = {key: [] for key in backup_restore.DUMP_SECTION_TABLE_MAP}
        sections["not_a_real_section"] = []
        path = self._write_dump(sections)
        try:
            with self.assertRaises(BackupCompletenessError):
                restore_database(path, "postgresql+psycopg2://unused/unused")
        finally:
            os.remove(path)


class TestBackupRestorePostgres(unittest.TestCase):
    """Full backup/restore round-trip against two real PostgreSQL databases
    on the same server."""

    @classmethod
    def setUpClass(cls):
        source_url = os.environ.get("OPPORTUNITYOS_DB_URL")
        ci = os.environ.get("CI")

        if not source_url or not source_url.startswith("postgresql"):
            if ci:
                raise AssertionError(
                    "CI is set but OPPORTUNITYOS_DB_URL is missing or not a "
                    "PostgreSQL URL (postgresql+psycopg2://...). A real "
                    "PostgreSQL DSN is required in CI for "
                    f"scripts.test_backup_restore; got: {source_url!r}."
                )
            raise unittest.SkipTest(
                "scripts.test_backup_restore requires a PostgreSQL "
                f"OPPORTUNITYOS_DB_URL to exercise the real backup/restore "
                f"cycle; got {source_url!r}. Skipping outside CI."
            )

        cls.source_url = source_url
        cls.target_url = _replace_db_name(source_url, TARGET_DB_NAME)
        cls._recreate_target_database()

    @classmethod
    def _terminate_and_drop_target(cls, conn):
        conn.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :dbname AND pid <> pg_backend_pid()"
            ),
            {"dbname": TARGET_DB_NAME},
        )
        conn.execute(text(f'DROP DATABASE IF EXISTS "{TARGET_DB_NAME}"'))

    @classmethod
    def _recreate_target_database(cls):
        admin_engine = create_engine(cls.source_url, isolation_level="AUTOCOMMIT")
        try:
            with admin_engine.connect() as conn:
                cls._terminate_and_drop_target(conn)
                conn.execute(text(f'CREATE DATABASE "{TARGET_DB_NAME}"'))
        finally:
            admin_engine.dispose()

    @classmethod
    def tearDownClass(cls):
        if not hasattr(cls, "source_url"):
            return  # setUpClass skipped/failed before any database was created
        admin_engine = create_engine(cls.source_url, isolation_level="AUTOCOMMIT")
        try:
            with admin_engine.connect() as conn:
                cls._terminate_and_drop_target(conn)
        finally:
            admin_engine.dispose()

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dump_file = os.path.join(self.temp_dir.name, "backup.json")

        # Ensure the source database schema is at head, then start each
        # test from an empty source (storage.test_postgres_integration may
        # have left rows behind from a prior run in the same session).
        self._upgrade_source_to_head()
        engine = get_engine(self.source_url)
        try:
            with engine.begin() as conn:
                for table in reversed(Base.metadata.sorted_tables):
                    conn.execute(text(f'TRUNCATE TABLE "{table.name}" CASCADE;'))
        finally:
            engine.dispose()

    def _upgrade_source_to_head(self):
        alembic_cfg = Config(str(ALEMBIC_INI_PATH))
        alembic_cfg.set_main_option("sqlalchemy.url", self.source_url)
        previous = os.environ.get("OPPORTUNITYOS_DB_URL")
        os.environ["OPPORTUNITYOS_DB_URL"] = self.source_url
        try:
            alembic_command.upgrade(alembic_cfg, "head")
        finally:
            if previous is not None:
                os.environ["OPPORTUNITYOS_DB_URL"] = previous
            else:
                del os.environ["OPPORTUNITYOS_DB_URL"]

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_full_backup_and_restore_cycle(self):
        # 1. Populate source db
        engine = get_engine(self.source_url)
        session_factory = get_session_factory(engine)
        session = session_factory()
        repo = StorageRepository(session)

        repo.save_opportunity({
            "id": "OPP-BACKUP-1",
            "track": "EMPLOYMENT",
            "title": "Principal Distributed Systems Engineer",
            "organization": "Alexandria Cloud Labs",
            "description": "Distributed systems",
            "source_id": "greenhouse:alexandria",
            "source_url": "https://boards.greenhouse.io/alexandria/1",
            "content_hash": "hash999",
        }, [{"field_name": "title", "derivation_type": "EXACT_EXTRACTION", "record_checksum": "hash999"}])

        repo.record_feedback("OPP-BACKUP-1", "good_match", None, "Perfect role fit")

        # Seed one row per D4/D4b table (match_evaluations, source_poll_runs,
        # founder_opportunity_views, founder_triage_states) -- three of the
        # four have an opportunity_id FK *column* with no relationship()
        # edge, which is exactly the ordering hazard restore_database's
        # explicit post-section-1 session.flush() exists to close (see
        # scripts/backup_restore.py). Seeding zero rows here (as this test
        # did before) is green against that bug regardless of whether the
        # fix is present, since an empty child table produces zero INSERTs
        # to misorder.
        # Naive, representing UTC wall-clock time directly (this project's own
        # established convention -- DateTime columns here are TIMESTAMP WITHOUT
        # TIME ZONE; handing psycopg2 a tz-aware datetime instead lets PostgreSQL
        # convert it to the session's timezone GUC before storing it naive, which
        # would silently shift these seeded values on a non-UTC session timezone).
        match_eval_evaluated_at = datetime(2026, 9, 2, 10, 30, 0)
        detail_json = (
            '{"hard_constraints": [], "strengths": [], "gaps": [], '
            '"unknowns": [], "uncertainty_penalty": 0.1, "explanation": "test"}'
        )
        session.add(MatchEvaluationRecord(
            id="me-backup-1",
            opportunity_id="OPP-BACKUP-1",
            truth_pack_hash="truth-pack-hash-backup-1",
            qualification_decision="uncertain",
            fit_score=63.25,
            dimension_scores_json='[{"dimension_name": "skills", "raw_score": 0.6}]',
            reasons_json='[{"kind": "gap", "dimension": "skills", "text": "Rust experience not evidenced"}]',
            evaluation_detail_json=detail_json,
            policy_version="1.0.0",
            evaluated_at=match_eval_evaluated_at,
        ))
        session.add(SourcePollRunRecord(
            id="spr-backup-1",
            source_id="greenhouse:alexandria",
            job_id="job-backup-1",
            started_at=datetime(2026, 9, 2, 10, 0, 0),
            finished_at=datetime(2026, 9, 2, 10, 0, 5),
            status="ok",
            raw_ingested=1,
            unique_opportunities=1,
            inserted=1,
            unchanged=0,
            updated=0,
        ))
        session.add(FounderOpportunityViewRecord(
            id="fov-backup-1",
            opportunity_id="OPP-BACKUP-1",
            viewed_at=datetime(2026, 9, 2, 10, 15, 0),
        ))
        triage_snoozed_until = datetime(2026, 9, 9, 0, 0, 0)
        session.add(FounderTriageStateRecord(
            opportunity_id="OPP-BACKUP-1",
            state="snoozed",
            snoozed_until=triage_snoozed_until,
            created_at=datetime(2026, 9, 2, 10, 16, 0),
            updated_at=datetime(2026, 9, 2, 10, 16, 0),
        ))
        # D3 (BRIEF-FR-005) council repair, defect 7: this test previously
        # asserted backup completeness for founder_filter_settings on a
        # row-count check alone (this class's own setUp TRUNCATEs the table,
        # so the prior version of this test dumped and restored zero rows --
        # a round trip that passes regardless of whether values actually
        # survive). Seed one row explicitly toggled away from its migration
        # default (enabled=True, mode="hide", non-empty params) and assert
        # every field below survives the restore intact.
        filter_updated_at = datetime(2026, 9, 2, 10, 17, 0)
        session.add(FounderFilterSettingRecord(
            filter_id="min_fit_score",
            enabled=True,
            mode="hide",
            params_json=json.dumps({"min_score": 42.5}),
            updated_at=filter_updated_at,
        ))
        session.commit()
        session.close()
        engine.dispose()

        # 2. Dump
        dump_database(self.source_url, self.dump_file)
        self.assertTrue(os.path.exists(self.dump_file))

        # 3. Restore into the distinct target database. The target starts
        # with no schema at all (dropped and recreated in setUpClass), so
        # this exercises restore_database's own Alembic upgrade-to-head.
        # This is the call that raised ForeignKeyViolation before the
        # explicit post-section-1 flush() fix, once any of the four new
        # tables held a row.
        restore_database(self.dump_file, self.target_url)

        # 4. Verify target db contents: opportunity round-trips with its
        # provenance and its founder feedback.
        dst_engine = get_engine(self.target_url)
        dst_session = get_session_factory(dst_engine)()

        opp = dst_session.query(OpportunityRecord).filter_by(id="OPP-BACKUP-1").first()
        self.assertIsNotNone(opp)
        self.assertEqual(opp.title, "Principal Distributed Systems Engineer")
        self.assertEqual(len(opp.provenances), 1)

        fb = dst_session.query(FounderFeedbackRecord).filter_by(opportunity_id="OPP-BACKUP-1").first()
        self.assertIsNotNone(fb)
        self.assertEqual(fb.feedback_label, "good_match")

        # 4b. The four new tables round-trip byte-for-byte, not just "a row
        # exists": this is what distinguishes "restore succeeded" from
        # "restore succeeded and preserved the data".
        me = dst_session.query(MatchEvaluationRecord).filter_by(id="me-backup-1").first()
        self.assertIsNotNone(me, "match_evaluations row must survive restore")
        self.assertEqual(me.opportunity_id, "OPP-BACKUP-1")
        self.assertEqual(me.truth_pack_hash, "truth-pack-hash-backup-1")
        self.assertEqual(me.qualification_decision, "uncertain")
        self.assertEqual(me.fit_score, 63.25)
        self.assertEqual(me.evaluation_detail_json, detail_json)
        self.assertEqual(me.evaluated_at, match_eval_evaluated_at)

        spr = dst_session.query(SourcePollRunRecord).filter_by(id="spr-backup-1").first()
        self.assertIsNotNone(spr, "source_poll_runs row must survive restore")
        self.assertEqual(spr.source_id, "greenhouse:alexandria")
        self.assertEqual(spr.status, "ok")
        self.assertEqual(spr.inserted, 1)

        fov = dst_session.query(FounderOpportunityViewRecord).filter_by(id="fov-backup-1").first()
        self.assertIsNotNone(fov, "founder_opportunity_views row must survive restore")
        self.assertEqual(fov.opportunity_id, "OPP-BACKUP-1")

        triage = dst_session.query(FounderTriageStateRecord).filter_by(opportunity_id="OPP-BACKUP-1").first()
        self.assertIsNotNone(triage, "founder_triage_states row must survive restore")
        self.assertEqual(triage.state, "snoozed")
        self.assertIsNotNone(triage.snoozed_until, "a snoozed triage state must keep its snoozed_until")
        self.assertEqual(triage.snoozed_until, triage_snoozed_until)

        filter_setting = dst_session.query(FounderFilterSettingRecord).filter_by(filter_id="min_fit_score").first()
        self.assertIsNotNone(filter_setting, "founder_filter_settings row must survive restore")
        self.assertTrue(filter_setting.enabled, "the non-default enabled=True must survive, not the migration default False")
        self.assertEqual(filter_setting.mode, "hide")
        self.assertEqual(json.loads(filter_setting.params_json), {"min_score": 42.5})
        self.assertEqual(filter_setting.updated_at, filter_updated_at)

        # 5. The restored target has the Alembic head stamped (read the
        # head from the script directory, never hard-coded).
        alembic_cfg = Config(str(ALEMBIC_INI_PATH))
        script_dir = ScriptDirectory.from_config(alembic_cfg)
        head_revision = script_dir.get_current_head()

        with dst_engine.connect() as conn:
            stamped_revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        self.assertEqual(stamped_revision, head_revision)

        # 6. Restoring the same dump a second time must not duplicate the
        # provenance row: field_provenances is now dumped with its
        # autoincrement `id` and restored with merge() (not add()), so a
        # second restore upserts by identity instead of inserting a
        # duplicate.
        restore_database(self.dump_file, self.target_url)
        opp_after_second_restore = dst_session.query(OpportunityRecord).filter_by(id="OPP-BACKUP-1").first()
        self.assertEqual(len(opp_after_second_restore.provenances), 1)
        me_count_after_second_restore = dst_session.query(MatchEvaluationRecord).filter_by(id="me-backup-1").count()
        self.assertEqual(me_count_after_second_restore, 1, "a second restore must not duplicate match_evaluations rows")

        dst_session.close()
        dst_engine.dispose()

    def test_restore_refuses_dump_with_column_delta(self):
        # 1. Take a real dump against the (empty, freshly-upgraded) source
        # schema, so its "table_columns" header reflects the real, current
        # model exactly.
        dump_database(self.source_url, self.dump_file)

        # 2. Direction 1: the *current model* gains a column the dump never
        # recorded (the dump is stale). Rather than mutating the real,
        # shared Base.metadata table objects in place (SQLAlchemy makes a
        # Table's ColumnCollection read-only once it has been used, so an
        # in-place append can't cleanly be undone -- see append/remove probe
        # in the deliverable notes), build a scratch MetaData that is a full
        # copy of every real table (via Table.to_metadata, which preserves
        # foreign keys so sorted_tables' topological sort keeps working),
        # add one extra column to the copy of "opportunities", and swap
        # Base.metadata to point at the scratch copy only for the duration
        # of this restore call. The original metadata object is restored in
        # `finally` so no mutation leaks into any other test in this
        # process.
        original_metadata = Base.metadata
        scratch_metadata = MetaData()
        for table in original_metadata.sorted_tables:
            table.to_metadata(scratch_metadata)
        scratch_metadata.tables["opportunities"].append_column(
            Column("scratch_added_column", String)
        )

        Base.metadata = scratch_metadata
        try:
            with self.assertRaises(BackupCompletenessError) as ctx:
                restore_database(self.dump_file, self.target_url)
        finally:
            Base.metadata = original_metadata

        message = str(ctx.exception)
        self.assertIn("scratch_added_column", message)
        self.assertIn("opportunities", message)

        # 3. Direction 2: the *dump* claims a column the current model does
        # not have (the dump is from a newer schema than this code). This
        # needs no metadata mutation at all -- editing the dump's own
        # "table_columns" header directly is the natural way to simulate a
        # dump that recorded a column the (unmodified, real) current model
        # does not have.
        with open(self.dump_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["table_columns"]["opportunities"].append("scratch_unknown_in_dump_column")
        mutated_dump_file = os.path.join(self.temp_dir.name, "mutated_backup.json")
        with open(mutated_dump_file, "w", encoding="utf-8") as f:
            json.dump(data, f)

        with self.assertRaises(BackupCompletenessError) as ctx2:
            restore_database(mutated_dump_file, self.target_url)
        message2 = str(ctx2.exception)
        self.assertIn("scratch_unknown_in_dump_column", message2)
        self.assertIn("opportunities", message2)

    def test_upgrade_to_head_is_independent_of_process_cwd(self):
        # alembic.ini's script_location/version_locations are written
        # relative to the repo root but Alembic resolves them against the
        # process CWD; from a scratch directory containing no
        # storage/migrations tree of its own, an unfixed _upgrade_to_head
        # raises CommandError. Running this from a CWD outside the repo
        # proves the fix is CWD-independent rather than accidentally
        # relying on the caller's working directory being the repo root.
        original_cwd = os.getcwd()
        scratch_dir = tempfile.mkdtemp()
        try:
            os.chdir(scratch_dir)
            backup_restore._upgrade_to_head(self.source_url)
        finally:
            os.chdir(original_cwd)


if __name__ == "__main__":
    unittest.main()
