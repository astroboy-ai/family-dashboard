import importlib.util
import re
from io import StringIO
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.dialects import postgresql

from app.models import Base


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "0001_initial.py"
)
SPEC = importlib.util.spec_from_file_location("familyos_initial_migration", MIGRATION_PATH)
assert SPEC is not None and SPEC.loader is not None
MIGRATION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MIGRATION)
TAG_GOVERNANCE_PATH = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0004_tag_provenance_and_exclusions.py"
TAG_GOVERNANCE_SPEC = importlib.util.spec_from_file_location("tag_governance_migration", TAG_GOVERNANCE_PATH)
assert TAG_GOVERNANCE_SPEC is not None and TAG_GOVERNANCE_SPEC.loader is not None
TAG_GOVERNANCE_MIGRATION = importlib.util.module_from_spec(TAG_GOVERNANCE_SPEC)
TAG_GOVERNANCE_SPEC.loader.exec_module(TAG_GOVERNANCE_MIGRATION)
LATER_TABLES = {"tag_exclusions", "tag_proposals", "tag_audit_log"}


def render_revision(migration: object, direction: str) -> str:
    output = StringIO()
    migration_context = MigrationContext.configure(
        dialect=postgresql.dialect(),
        opts={
            "as_sql": True,
            "output_buffer": output,
            "target_metadata": Base.metadata,
        },
    )
    original_operations = migration.op
    migration.op = Operations(migration_context)
    try:
        getattr(migration, direction)()
    finally:
        migration.op = original_operations
    return output.getvalue()


def render_migration(direction: str) -> str:
    return render_revision(MIGRATION, direction)


def test_initial_upgrade_creates_every_phase_one_model_table() -> None:
    sql = render_migration("upgrade")
    created_tables = set(re.findall(r"CREATE TABLE ([a-z_]+)", sql))

    assert created_tables == set(Base.metadata.tables) - LATER_TABLES
    assert "gen_random_uuid()" in sql
    assert "GENERATED ALWAYS AS" in sql
    assert "CONSTRAINT ck_notes_visibility_valid" in sql
    assert "CONSTRAINT ck_notes_ck_notes_visibility_valid" not in sql


def test_initial_downgrade_drops_every_table_in_reverse_dependency_order() -> None:
    sql = render_migration("downgrade")
    dropped_tables = re.findall(r"DROP TABLE ([a-z_]+)", sql)

    assert set(dropped_tables) == set(Base.metadata.tables) - LATER_TABLES
    assert dropped_tables.index("note_blocks") < dropped_tables.index("notes")
    assert dropped_tables.index("notes") < dropped_tables.index("family_members")


def test_tag_governance_revision_adds_provenance_and_exclusion_tables() -> None:
    sql = render_revision(TAG_GOVERNANCE_MIGRATION, "upgrade")

    assert "ALTER TABLE note_tags ADD COLUMN source VARCHAR(16) DEFAULT 'human' NOT NULL" in sql
    assert "CREATE TABLE tag_exclusions" in sql
    assert "CREATE TABLE tag_proposals" in sql
    assert "CREATE TABLE tag_audit_log" in sql
    assert "approved_by_human" in sql