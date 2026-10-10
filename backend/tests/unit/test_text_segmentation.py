"""Search tokenization must behave identically on both sides of the index.

The failure these tests guard against: PostgreSQL's ``simple`` configuration
treats a whole Chinese sentence as one token, so a query for 默書 never matches a
row containing 下星期三中文默書. That was verified against the live database
before the fix.
"""

from app.core.text import build_query_text, build_search_text, segment


def test_chinese_is_segmented_into_multiple_tokens():
    tokens = segment("下星期三中文默書")

    assert len(tokens) > 1, "a CJK sentence must not collapse into a single token"
    assert "默書" in tokens, f"expected 默書 among {tokens}"


def test_chinese_query_and_document_share_tokens():
    """The whole point: a query term must appear in the document's token list."""

    document = set(segment("下星期三 Phoebe 有中文默書"))
    query = set(segment("默書"))

    assert query & document, f"query tokens {query} did not intersect document tokens {document}"


def test_english_is_lowercased_and_split_on_whitespace():
    tokens = segment("Phoebe has English Dictation")

    assert tokens == ["phoebe", "has", "english", "dictation"]


def test_fullwidth_latin_is_normalized():
    assert segment("ＡＢＣ１２３") == segment("abc123")


def test_mixed_language_keeps_both_scripts():
    tokens = segment("Phoebe 星期五 有 English 默書")

    assert "phoebe" in tokens
    assert "english" in tokens
    assert "默書" in tokens


def test_punctuation_is_dropped():
    tokens = segment("默書，英文！(dictation)")

    assert "，" not in tokens
    assert "默書" in tokens
    assert "dictation" in tokens


def test_build_search_text_joins_tokens_with_spaces():
    text = build_search_text("中文默書", "English dictation")

    assert "  " not in text, "tokens must be single-space separated for to_tsvector('simple')"
    assert "默書" in text
    assert "dictation" in text


def test_empty_inputs_return_empty():
    assert segment(None) == []
    assert segment("") == []
    assert build_search_text(None, "", None) == ""
    assert build_query_text(None) == ""
    assert build_query_text("   ") == ""


def test_query_and_document_paths_agree():
    """A query built by build_query_text must be findable in build_search_text."""

    document = build_search_text("下星期三中文默書")
    query = build_query_text("中文默書")

    document_tokens = set(document.split())
    query_tokens = set(query.split())

    assert query_tokens <= document_tokens, (
        f"query tokens {query_tokens - document_tokens} missing from document tokens"
    )
