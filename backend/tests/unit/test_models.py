from sqlalchemy import Computed

from app.models import Base, FamilyMember, MediaAsset, Note, NoteBlock, note_tags


EXPECTED_PHASE_ONE_TABLES = {
    "households",
    "users",
    "family_members",
    "device_tokens",
    "notes",
    "note_blocks",
    "tags",
    "note_tags",
    "note_relations",
    "media_assets",
    "jobs_outbox",
    "agent_tool_calls",
    "audit_log",
    "notifications",
    "tools",
    "tag_exclusions",
    "tag_proposals",
    "tag_audit_log",
}


def test_phase_one_core_tables_are_registered() -> None:
    assert set(Base.metadata.tables) == EXPECTED_PHASE_ONE_TABLES
    assert len(Base.metadata.sorted_tables) == len(EXPECTED_PHASE_ONE_TABLES)


def test_note_tags_uses_both_ids_as_composite_primary_key() -> None:
    assert {column.name for column in note_tags.primary_key.columns} == {"note_id", "tag_id"}
    assert note_tags.c.note_id.foreign_keys
    assert note_tags.c.tag_id.foreign_keys


def test_note_and_block_search_vectors_are_database_generated() -> None:
    note_search = Note.__table__.c.search_tsv.server_default
    block_search = NoteBlock.__table__.c.search_tsv.server_default

    assert isinstance(note_search, Computed)
    assert isinstance(block_search, Computed)
    assert "title" in str(note_search.sqltext)
    assert "ocr_text" in str(block_search.sqltext)


def test_visibility_role_and_media_kind_constraints_exist() -> None:
    note_constraints = {constraint.name for constraint in Note.__table__.constraints}
    member_constraints = {constraint.name for constraint in FamilyMember.__table__.constraints}
    media_constraints = {constraint.name for constraint in MediaAsset.__table__.constraints}

    assert "ck_notes_visibility_valid" in note_constraints
    assert "ck_family_members_role_valid" in member_constraints
    assert "ck_media_assets_kind_valid" in media_constraints


def test_search_and_household_dedupe_indexes_exist() -> None:
    note_indexes = {index.name for index in Note.__table__.indexes}
    media_indexes = {index.name for index in MediaAsset.__table__.indexes}

    assert "ix_notes_search_tsv_gin" in note_indexes
    assert "ix_notes_household_status_updated" in note_indexes
    assert "ix_media_assets_household_sha256" in media_indexes