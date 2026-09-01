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
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import create_engine, text
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic import command as alembic_command

from storage.engine import get_engine, get_session_factory
from storage.repository import StorageRepository
from storage.models import Base, OpportunityRecord, FounderFeedbackRecord
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
        session.close()
        engine.dispose()

        # 2. Dump
        dump_database(self.source_url, self.dump_file)
        self.assertTrue(os.path.exists(self.dump_file))

        # 3. Restore into the distinct target database. The target starts
        # with no schema at all (dropped and recreated in setUpClass), so
        # this exercises restore_database's own Alembic upgrade-to-head.
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

        dst_session.close()
        dst_engine.dispose()

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
