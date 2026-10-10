"""Deciding *what* text to embed for a note.

Chunking policy (blueprint §9.3, adapted):

* **Note-level** — one chunk from ``title + summary + ai_summary`` plus the
  leading slice of the concatenated block text. Gives a coarse whole-note vector
  that ranks well for "what is this note about".
* **Block-level** — one or more chunks per block, from ``text_content``,
  ``caption``, ``ai_description``, ``ocr_text`` and ``transcript``. Blocks carry
  the OCR of a photographed notice and the transcript of a voice memo, so they
  are usually the sharper retrieval unit. Structured ``data`` is flattened to
  ``key: value`` lines.

Never embedded: anything the caller cannot search anyway — vault payloads and
account secrets are excluded by the caller, not here, because this module only
sees the note it is handed.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Note, NoteBlock
from app.services.embeddings import content_hash

# Roughly 512 tokens at ~4 characters per token for mixed CJK/latin text.
CHUNK_CHARS = 2000
CHUNK_OVERLAP_CHARS = 250
NOTE_LEAD_CHARS = 800


@dataclass(frozen=True)
class Chunk:
    owner_type: str
    owner_id: uuid.UUID
    chunk_index: int
    content: str

    @property
    def content_hash(self) -> str:
        return content_hash(self.content)


def _flatten_data(data: Any) -> str:
    """Turn a JSON blob into ``key: value`` lines so it can be embedded."""

    if not isinstance(data, dict):
        return ""

    lines: list[str] = []
    for key, value in data.items():
        if value in (None, "", [], {}):
            continue
        if isinstance(value, (dict, list)):
            value = str(value)
        lines.append(f"{key}: {value}")
    return "\n".join(lines)


def _split(text: str, *, size: int = CHUNK_CHARS, overlap: int = CHUNK_OVERLAP_CHARS) -> list[str]:
    """Character-window split with overlap, breaking on whitespace when close."""

    text = text.strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            window = text.rfind(" ", start + size // 2, end)
            if window != -1:
                end = window
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return [chunk for chunk in chunks if chunk]


def block_text(block: NoteBlock) -> str:
    """All searchable text of one block, including flattened structured data."""

    parts = [
        block.text_content,
        block.caption,
        block.ai_description,
        block.ocr_text,
        block.transcript,
        _flatten_data(block.data),
    ]
    return "\n".join(part.strip() for part in parts if part and part.strip())


def note_text(note: Note, blocks: list[NoteBlock]) -> str:
    """The coarse whole-note text used for the note-level embedding."""

    header = "\n".join(
        part.strip() for part in (note.title, note.summary, note.ai_summary) if part and part.strip()
    )
    body = "\n".join(block_text(block) for block in blocks)
    lead = body[:NOTE_LEAD_CHARS]
    return "\n".join(part for part in (header, lead) if part).strip()


async def collect_note_chunks(session: AsyncSession, note: Note) -> list[Chunk]:
    """Every chunk to embed for *note*, note-level first."""

    blocks = list(
        (
            await session.execute(
                select(NoteBlock).where(NoteBlock.note_id == note.id).order_by(NoteBlock.order_index)
            )
        )
        .scalars()
        .all()
    )

    chunks: list[Chunk] = []

    whole = note_text(note, blocks)
    if whole:
        chunks.append(
            Chunk(owner_type="note", owner_id=note.id, chunk_index=0, content=whole)
        )

    for block in blocks:
        text = block_text(block)
        if not text:
            continue
        for index, piece in enumerate(_split(text)):
            chunks.append(
                Chunk(owner_type="block", owner_id=block.id, chunk_index=index, content=piece)
            )

    return chunks
