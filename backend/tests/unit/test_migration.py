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


def render_migration(direction: str) -> str:
    output = StringIO()
    migration_context = MigrationContext.configure(
        dialect=postgresql.dialect(),
        opts={
            "as_sql": True,
            "output_buffer": output,
            "target_metadata": Base.metadata,
        },
    )
    original_operations = MIGRATION.op
    MIGRATION.op = Operations(migration_context)
    try:
        getattr(MIGRATION, direction)()
    finally:
        MIGRATION.op = original_operations
    return output.getvalue()


def test_initial_upgrade_creates_every_phase_one_model_table() -> None:
    sql = render_migration("upgrade")
    created_tables = set(re.findall(r"CREATE TABLE ([a-z_]+)", sql))

    assert created_tables == set(Base.metadata.tables)
    assert "gen_random_uuid()" in sql
    assert "GENERATED ALWAYS AS" in sql
    assert "CONSTRAINT ck_notes_visibility_valid" in sql
    assert "CONSTRAINT ck_notes_ck_notes_visibility_valid" not in sql


def test_initial_downgrade_drops_every_table_in_reverse_dependency_order() -> None:
    sql = render_migration("downgrade")
    dropped_tables = re.findall(r"DROP TABLE ([a-z_]+)", sql)

    assert set(dropped_tables) == set(Base.metadata.tables)
    assert dropped_tables.index("note_blocks") < dropped_tables.index("notes")
    assert dropped_tables.index("notes") < dropped_tables.index("family_members")