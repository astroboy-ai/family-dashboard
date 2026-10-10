"""Text segmentation for full-text search.

PostgreSQL's ``simple`` text-search configuration does not segment CJK text: an
entire Chinese sentence collapses into a single token, so a query for 默書 never
matches a row containing 下星期三中文默書 (verified against this database before
the change: ``to_tsvector('simple','下星期三中文默書') @@
websearch_to_tsquery('simple','默書')`` returned false).

We therefore segment text in Python before it reaches ``tsvector``.

The **same** segmenter must run on both sides:

* the write path, filling the ``search_tokens_*`` columns, and
* the query path, before ``websearch_to_tsquery``.

If the two sides tokenize differently the index never matches, so both go
through :func:`build_search_text` / :func:`segment`.
"""

from __future__ import annotations

import re
import unicodedata

# CJK ideographs, kana and hangul. These are the ranges jieba is asked to
# segment; everything else is treated as latin/digit runs.
_CJK_RANGES = (
    "\u3400-\u4dbf"  # CJK Extension A
    "\u4e00-\u9fff"  # CJK Unified Ideographs
    "\uf900-\ufaff"  # CJK Compatibility Ideographs
    "\u3040-\u30ff"  # Hiragana + Katakana
    "\uac00-\ud7af"  # Hangul syllables
)

_TOKEN_RE = re.compile(rf"[{_CJK_RANGES}]+|[A-Za-z0-9_]+")
_CJK_RE = re.compile(rf"^[{_CJK_RANGES}]")

try:  # pragma: no cover - import behaviour is covered by the image build
    import jieba

    jieba.setLogLevel(60)  # silence the "building prefix dict" banner
    _JIEBA_AVAILABLE = True
except ImportError:  # pragma: no cover - keeps the stack usable without jieba
    jieba = None  # type: ignore[assignment]
    _JIEBA_AVAILABLE = False


def jieba_available() -> bool:
    """Whether real CJK segmentation is active (as opposed to the fallback)."""

    return _JIEBA_AVAILABLE


def _normalize(text: str) -> str:
    # NFKC folds full-width latin/digits onto their ASCII forms so that
    # "ＡＢＣ１２３" and "abc123" produce the same tokens.
    return unicodedata.normalize("NFKC", text).lower()


def _segment_cjk_run(run: str) -> list[str]:
    if _JIEBA_AVAILABLE:
        return [token for token in jieba.cut(run, cut_all=False) if token.strip()]

    # Fallback when jieba is not installed: emit the run itself plus every
    # adjacent bigram. Recall is worse than real segmentation (no word
    # boundaries, so ranking suffers) but a single-character query still hits,
    # and the stack keeps working — see blueprint principle "fail soft".
    tokens = [run]
    tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
    return tokens


def segment(text: str | None) -> list[str]:
    """Split *text* into search tokens.

    Latin/digit runs are lowercased and kept whole; CJK runs are segmented with
    jieba. Punctuation and whitespace are dropped.
    """

    if not text:
        return []

    tokens: list[str] = []
    for match in _TOKEN_RE.finditer(_normalize(text)):
        piece = match.group(0)
        if _CJK_RE.match(piece):
            tokens.extend(_segment_cjk_run(piece))
        else:
            tokens.append(piece)
    return tokens


def build_search_text(*parts: str | None) -> str:
    """Tokenize each part and join the tokens with single spaces.

    The result is what gets stored in a ``search_tokens_*`` column and fed to
    ``to_tsvector('simple', ...)``. Spaces are the only separator ``simple``
    needs, and they keep the stored value readable for debugging.
    """

    tokens: list[str] = []
    for part in parts:
        tokens.extend(segment(part))
    return " ".join(tokens)


def build_query_text(query: str | None) -> str:
    """Normalize a user query into the same token space as the indexed rows.

    Returns an empty string for an empty/whitespace-only query, which callers
    treat as "no text filter" (browse mode).
    """

    if not query:
        return ""
    return build_search_text(query)
