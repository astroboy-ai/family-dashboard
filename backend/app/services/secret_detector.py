"""Server-side port of the browser secret detector.

Mirrors ``frontend-main/src/lib/secret-detector.ts``. The browser runs this to
help a human scan a paste; the server runs the same rules to **cross-check what
an agent claims**. Two independent passes over the same text is the point: an
LLM misses things, and a regex is not fooled by a plausible-looking paragraph.

Why a port rather than a call to the frontend
---------------------------------------------
The agent has no browser. It posts text to an endpoint and gets a verdict. Doing
the check in Python means the answer is available over MCP and HTTP, and the
rules can be unit-tested without a DOM.

Keeping the two in step
-----------------------
The rule table, the severity ranks, the placeholder patterns and the stacked-block
classifier are all duplicated here. **When one side changes, change both.** The
shared invariants are:

* key format ``sn-<slug>-<6hex>`` (see :mod:`app.services.smart_text`)
* placeholder syntax ``{{secret:<key>}}``
* magic tags ``[[secret]]…[[/secret]]``
* the ``\\b``-is-wrong lesson: word boundaries are ``(?<![A-Za-z0-9_])``, because
  ``_`` is a word character and ``\\bpassword\\b`` does not match
  ``DATABASE_PASSWORD``.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Literal

Severity = Literal["CRITICAL", "HIGH", "MEDIUM"]

SEVERITY_RANK: dict[str, int] = {"CRITICAL": 3, "HIGH": 2, "MEDIUM": 1}


@dataclass
class Finding:
    """One candidate secret, with the span it occupies in the source text."""

    start: int
    end: int
    value: str
    label: str
    type: str
    severity: str
    confidence: float
    entropy: float
    selected: bool
    rule: str
    manual: bool = False

    @property
    def id(self) -> str:
        return f"{self.start}:{self.end}:{self.type}"

    def to_dict(self) -> dict:
        """Serialise for the API.

        ``value`` is included on purpose: the caller supplied the text, so it
        already holds every value. Withholding it here only made the review
        panel unreadable on the frontend, where the same reasoning applies.
        """
        return {
            "id": self.id,
            "start": self.start,
            "end": self.end,
            "value": self.value,
            "label": self.label,
            "type": self.type,
            "severity": self.severity,
            "confidence": round(self.confidence, 3),
            "entropy": self.entropy,
            "selected": self.selected,
            "rule": self.rule,
            "manual": self.manual,
            "reason": rule_reason(self.rule),
        }


@dataclass(frozen=True)
class Rule:
    id: str
    type: str
    severity: str
    confidence: float
    pattern: re.Pattern
    # Which group holds the secret. Provider patterns match the whole token and
    # use 0; contextual rules capture only the value.
    value_group: int


def shannon_entropy(value: str) -> float:
    """Bits per character.

    Used only to *adjust* confidence, never to decide alone: a bare threshold
    flags every hash, ID and base64 blob.
    """
    if not value:
        return 0.0
    counts: dict[str, int] = {}
    for char in value:
        counts[char] = counts.get(char, 0) + 1
    total = len(value)
    entropy = 0.0
    for count in counts.values():
        p = count / total
        entropy -= p * math.log2(p)
    return entropy


# ── Provider rules: the format proves what it is ─────────────────────────────
#
# Versioned assumptions, not permanent truths — providers change their token
# shapes — so they live at the top where they are easy to revise.

PROVIDER_RULES: list[Rule] = [
    Rule(
        id="private_key",
        type="private_key",
        severity="CRITICAL",
        confidence=0.999,
        # Only the header: the body is base64 lines that a generic rule would
        # match anyway, and the header is enough to identify the block.
        pattern=re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"),
        value_group=0,
    ),
    Rule(
        id="github_pat_fine",
        type="github_token",
        severity="CRITICAL",
        confidence=0.995,
        pattern=re.compile(r"(?<![A-Za-z0-9_])github_pat_[A-Za-z0-9_]{20,255}(?![A-Za-z0-9_])"),
        value_group=0,
    ),
    Rule(
        id="github_pat",
        type="github_token",
        severity="CRITICAL",
        confidence=0.995,
        pattern=re.compile(r"(?<![A-Za-z0-9_])gh[pousr]_[A-Za-z0-9]{20,255}(?![A-Za-z0-9_])"),
        value_group=0,
    ),
    Rule(
        id="slack_token",
        type="slack_token",
        severity="CRITICAL",
        confidence=0.995,
        pattern=re.compile(r"(?<![A-Za-z0-9_])xox[baprs]-[A-Za-z0-9-]{10,}"),
        value_group=0,
    ),
    Rule(
        id="google_api_key",
        type="google_api_key",
        severity="HIGH",
        confidence=0.98,
        pattern=re.compile(r"(?<![A-Za-z0-9_])AIza[A-Za-z0-9_-]{30,}"),
        value_group=0,
    ),
    Rule(
        id="openai_key",
        type="api_key",
        severity="HIGH",
        confidence=0.97,
        pattern=re.compile(r"(?<![A-Za-z0-9_])sk-[A-Za-z0-9_-]{20,}"),
        value_group=0,
    ),
    Rule(
        id="jwt",
        type="jwt",
        severity="HIGH",
        confidence=0.96,
        pattern=re.compile(
            r"(?<![A-Za-z0-9_])eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"
        ),
        value_group=0,
    ),
    Rule(
        id="connection_string",
        type="database_credentials",
        severity="CRITICAL",
        confidence=0.98,
        # `user:password@host` — the whole authority section is the secret.
        pattern=re.compile(
            r"(?<![A-Za-z0-9_])(?:mongodb(?:\+srv)?|postgres(?:ql)?|mysql|mariadb|redis)"
            r"://[^\s/@]+:[^\s/@]+@",
            re.IGNORECASE,
        ),
        value_group=0,
    ),
    Rule(
        id="bearer",
        type="bearer_token",
        severity="HIGH",
        confidence=0.94,
        pattern=re.compile(r"(?<![A-Za-z0-9_])Bearer\s+([A-Za-z0-9._~+/-]{20,}={0,2})"),
        value_group=1,
    ),
]


# ── Context rules: a label the author wrote makes these work ─────────────────
#
# `1234567` alone is meaningless; `google password: 1234567` is not. Group 1 is
# the label, group 2 is the value.
#
# `[^\n]*?` rather than `.+?` so a match never crosses a line — a label with no
# value on its line must not swallow the next one.
#
# The boundary is `(?<![A-Za-z0-9])` / `(?![A-Za-z0-9])`, **not** `\b`.
# Underscore is a word character, so `\bpassword\b` fails inside
# `DATABASE_PASSWORD` — the commonest shape of all.

CONTEXT_RULES: list[Rule] = [
    Rule(
        id="password_assignment",
        type="password",
        severity="HIGH",
        confidence=0.9,
        pattern=re.compile(
            r"^([^\n:=]{0,60}?(?<![A-Za-z0-9])(?:password|passwd|pwd|passphrase)"
            r"(?![A-Za-z0-9])[^\n:=]{0,40})[:=]\s*[\"'`]?([^\s\"'`,;]{3,})[\"'`]?",
            re.MULTILINE | re.IGNORECASE,
        ),
        value_group=2,
    ),
    Rule(
        id="key_assignment",
        type="api_key",
        severity="HIGH",
        confidence=0.85,
        pattern=re.compile(
            r"^([^\n:=]{0,60}?(?<![A-Za-z0-9])"
            r"(?:api[ _-]?key|access[ _-]?token|auth[ _-]?token|client[ _-]?secret"
            r"|secret[ _-]?key|token|secret|key)(?![A-Za-z0-9])[^\n:=]{0,40})"
            r"[:=]\s*[\"'`]?([^\s\"'`,;]{8,})[\"'`]?",
            re.MULTILINE | re.IGNORECASE,
        ),
        value_group=2,
    ),
]

ALL_RULES: list[Rule] = [*PROVIDER_RULES, *CONTEXT_RULES]


# A line that is only a label — `Orange system:` with nothing after the colon.
# This is how people actually write a credential block in a text file: a heading,
# then one value per line. The inline rules cannot see it, because no single line
# carries `label: value`.
BARE_LABEL = re.compile(r"^[ \t]*([^\n:]{1,40}?)[ \t]*:[ \t]*$")

# Schemes that make a value an address rather than a credential.
URL_SHAPE = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)

# Values with a digit and a separator that are dates or times, not secrets.
# `Renewal:` / `2026-10-11` otherwise reads as "short, has a digit, has a symbol"
# — the password shape. A date is one of the commonest things under a heading.
DATE_OR_TIME = re.compile(
    r"^(?:\d{4}[-/.]\d{1,2}[-/.]\d{1,2}"
    r"|\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}"
    r"|\d{1,2}:\d{2}(?::\d{2})?)$"
)

MAGIC_OPEN = "[[secret]]"
MAGIC_CLOSE = "[[/secret]]"

# A magic tag may carry its own name: `[[secret:Orange ERP password]]…[[/secret]]`.
# Without one, the label comes from the line or the heading above — which is fine
# for a single secret but ambiguous when a heading covers several, where every
# finding would otherwise be named "Orange system".
MAGIC_OPEN_LABELLED = re.compile(r"\[\[secret:([^\]]*)\]\]")

SMART_TEXT_PLACEHOLDER = re.compile(r"\{\{secret:[^}]+\}\}")

PLACEHOLDER_PATTERNS: list[re.Pattern] = [
    re.compile(r"^<[^>]+>$"),
    re.compile(r"^\$\{[^}]+\}$"),
    re.compile(r"^\{\{[^}]+\}\}$"),
    re.compile(r"^%[A-Z_]+%$"),
    re.compile(r"^YOUR[_-]", re.IGNORECASE),
    re.compile(r"^YOUR[A-Z0-9_-]*$", re.IGNORECASE),
    re.compile(r"^REPLACE[_-]", re.IGNORECASE),
    re.compile(r"^CHANGE[_-]?ME$", re.IGNORECASE),
    re.compile(r"^CHANGE[_-]", re.IGNORECASE),
    re.compile(r"^EXAMPLE[_-]", re.IGNORECASE),
    re.compile(r"^SAMPLE[_-]", re.IGNORECASE),
    re.compile(r"^TODO$", re.IGNORECASE),
    re.compile(r"^REDACTED[_-]?", re.IGNORECASE),
    re.compile(r"^x{4,}$", re.IGNORECASE),
    re.compile(r"^\*{4,}$"),
    re.compile(r"^\.{4,}$"),
    re.compile(r"^dummy$", re.IGNORECASE),
    re.compile(r"^example$", re.IGNORECASE),
    re.compile(r"^placeholder$", re.IGNORECASE),
    re.compile(r"^none$", re.IGNORECASE),
    re.compile(r"^null$", re.IGNORECASE),
    re.compile(r"^undefined$", re.IGNORECASE),
    re.compile(r"^process\.env\."),
    re.compile(r"^\$[A-Z_]+$"),
]


def is_placeholder(value: str) -> bool:
    """True for documentation stand-ins and our own placeholders.

    The most valuable false-positive control for an agent-heavy workspace, where
    `API_KEY=<your-api-key>` is written constantly.
    """
    trimmed = value.strip()
    if not trimmed:
        return True
    if SMART_TEXT_PLACEHOLDER.search(trimmed):
        return True
    return any(pattern.search(trimmed) for pattern in PLACEHOLDER_PATTERNS)


def classify_stacked_value(value: str) -> dict | None:
    """Classify a value sitting under a bare label.

    Signals are weaker than for an inline `password: x` because the label is on
    another line, so this errs towards MEDIUM and lets the caller decide. Returns
    ``None`` when the value looks like ordinary text — the common case
    (`manager`, `ERP_DEMO` are identifiers, not credentials).
    """
    if not value or is_placeholder(value):
        return None
    if URL_SHAPE.match(value):
        return None
    if DATE_OR_TIME.match(value):
        return None
    # Whitespace means prose or a `label: value` line, not a bare value.
    if re.search(r"\s", value):
        return None

    length = len(value)
    has_digit = bool(re.search(r"\d", value))
    has_special = bool(re.search(r"[^A-Za-z0-9]", value))
    has_lower = bool(re.search(r"[a-z]", value))
    has_upper = bool(re.search(r"[A-Z]", value))
    entropy = shannon_entropy(value)

    # Long, high-entropy, mixed alphanumeric: a generated token.
    if length >= 20 and has_digit and entropy >= 3.5 and (has_lower or has_upper):
        return {"type": "api_key", "severity": "HIGH", "confidence": 0.8}

    # A password shape: short-ish, has a digit, and a symbol or mixed case.
    # `HGC@2020` qualifies; `ERP_DEMO` and `manager` do not.
    if length >= 6 and length <= 40 and has_digit and (has_special or (has_lower and has_upper)):
        return {
            "type": "password",
            "severity": "HIGH" if has_special else "MEDIUM",
            "confidence": 0.78 if has_special else 0.7,
        }

    return None


def _derive_label(source: str, start: int, fallback: str) -> str:
    """Name a finding from the words preceding it.

    The author's own words beat anything invented — `old password (2024-09-01)`
    says more than "password #2".
    """
    line_start = source.rfind("\n", 0, start) + 1
    prefix = source[line_start:start]
    cleaned = re.sub(r"[:=\s]+$", "", prefix).strip()
    if not cleaned:
        return fallback
    return cleaned if len(cleaned) <= 60 else fallback


def _detect_stacked_values(text: str, scannable: str | None = None) -> list[Finding]:
    """Find secrets written as a labelled block, one value per line.

    ```
    Orange system:
    manager
    HGC@2020
    ```

    Everything from the line after the label to the next blank line or the next
    bare label is a candidate. The label names the findings, because the author's
    own heading is a better name than anything derived from the value.

    ``scannable`` is the same text with magic-tag regions blanked. Values are
    read from it — a marker is syntax, not content. Line boundaries come from
    ``text``, because a fully-blanked line *looks* blank and would otherwise end
    the block early, hiding every value below a tagged one.
    """
    original_lines = text.split("\n")
    scan_lines = (scannable if scannable is not None else text).split("\n")

    line_starts: list[int] = []
    offset = 0
    for line in original_lines:
        line_starts.append(offset)
        offset += len(line) + 1

    findings: list[Finding] = []

    for i, line in enumerate(original_lines):
        header = BARE_LABEL.match(line)
        if not header:
            continue
        label = header.group(1).strip()
        if not label:
            continue

        for j in range(i + 1, len(original_lines)):
            raw_original = original_lines[j]
            # Blankness and section breaks are judged on the real text: a line
            # holding only a magic tag is blank in `scannable` but is not a blank
            # line in the note.
            if not raw_original.strip():
                break  # a blank line ends the block
            if BARE_LABEL.match(raw_original):
                break  # the next section starts

            raw = scan_lines[j] if j < len(scan_lines) else raw_original
            value = raw.strip()
            if not value:
                continue  # this line held only a marker

            classified = classify_stacked_value(value)
            if not classified:
                continue

            # Point the span at the value, not at the leading whitespace. Masking
            # preserves length, so the offset is valid in the original too.
            start = line_starts[j] + raw.index(value)
            end = start + len(value)

            findings.append(
                Finding(
                    start=start,
                    end=end,
                    value=value,
                    label=label,
                    type=classified["type"],
                    severity=classified["severity"],
                    confidence=classified["confidence"],
                    entropy=round(shannon_entropy(value), 2),
                    selected=classified["severity"] != "MEDIUM",
                    rule="stacked_block",
                )
            )

    return findings


def _nearest_heading(text: str, start: int) -> str | None:
    """The closest bare-label heading above ``start``, if any.

    `Orange system:` on one line, values on the lines below, is how people
    actually write a credential block. A magic tag sitting on its own line has no
    prefix of its own, so the heading is the only name available — and it is a
    better name than "marked by hand".
    """
    line_start = text.rfind("\n", 0, start) + 1
    cursor = line_start
    while cursor > 0:
        previous_end = cursor - 1  # the newline
        previous_start = text.rfind("\n", 0, previous_end) + 1
        line = text[previous_start:previous_end]
        stripped = line.strip()
        if not stripped:
            return None  # a blank line ends the block
        header = BARE_LABEL.match(line)
        if header and header.group(1).strip():
            return header.group(1).strip()
        cursor = previous_start
    return None


def mask_magic_spans(text: str) -> str:
    """Blank out every magic-tag region, preserving offsets.

    The marker is syntax, not content. Left visible, the `secret:` inside
    ``[[secret:Kurintic API key]]`` reads to the context rules as a
    `secret: value` assignment and produces a finding named `[[secret`.

    Spaces rather than deletion so every other finding keeps its span in the
    original string, which is what the review list and the replacement step
    both index into.
    """
    masked = list(text)
    cursor = 0

    while cursor < len(text):
        plain = text.find(MAGIC_OPEN, cursor)
        named = MAGIC_OPEN_LABELLED.search(text, cursor)

        if named is not None and (plain == -1 or named.start() < plain):
            start = named.start()
        elif plain != -1:
            start = plain
        else:
            break

        close_at = text.find(MAGIC_CLOSE, start)
        if close_at == -1:
            break

        end = close_at + len(MAGIC_CLOSE)
        for i in range(start, end):
            masked[i] = " "
        cursor = end

    return "".join(masked)


def _detect_manual_tags(text: str) -> list[Finding]:
    """Pull out everything wrapped in ``[[secret]]…[[/secret]]``.

    The detector will never catch everything, and the author knows their own data
    better than any ruleset. An agent that has already decided what is a secret
    marks it in place — the marker is plain text, so nothing new has to be
    stored, and the same detect → approve → protect flow does the rest.

    A tag may name itself — ``[[secret:Orange ERP password]]…[[/secret]]``. That
    matters when one heading covers several secrets: without a name every finding
    under `Orange system:` would be labelled "Orange system", and the review list
    would show two indistinguishable rows.

    Nested markers are not supported; the first closing tag ends the span.
    """
    findings: list[Finding] = []
    cursor = 0

    while cursor < len(text):
        # The two openers are genuinely distinct: `[[secret]]` closes its
        # brackets, `[[secret:name]]` has a colon. Take whichever comes first.
        plain = text.find(MAGIC_OPEN, cursor)
        named = MAGIC_OPEN_LABELLED.search(text, cursor)

        if named is not None and (plain == -1 or named.start() < plain):
            name = named.group(1).strip()
            value_start = named.end()
        elif plain != -1:
            name = ""
            value_start = plain + len(MAGIC_OPEN)
        else:
            break

        close_at = text.find(MAGIC_CLOSE, value_start)
        if close_at == -1:
            break

        start = value_start
        value = text[start:close_at]
        cursor = close_at + len(MAGIC_CLOSE)

        if not value.strip():
            continue

        # An explicit name wins. Otherwise take the line the marker sits on, with
        # the marker itself removed — `login: [[secret]]x[[/secret]]` is named
        # "login", not "login: [[secret]]". When the marker is alone on its line,
        # fall back to the heading above it: `Orange system:` on one line, values
        # below, is how a credential block is actually written.
        if name:
            label = name
        else:
            raw_label = _derive_label(text, start, "marked by hand")
            label = re.sub(r"\[\[/?secret:?[^\]]*\]\]", "", raw_label)
            label = re.sub(r"[:=\s]+$", "", label).strip()
            if not label:
                label = _nearest_heading(text, start) or "marked by hand"

        findings.append(
            Finding(
                start=start,
                end=close_at,
                value=value,
                label=label,
                type="manual",
                # The author asserted this is a secret, so it outranks any guess.
                severity="HIGH",
                confidence=1.0,
                entropy=round(shannon_entropy(value), 2),
                selected=True,
                rule="magic_tag",
                manual=True,
            )
        )

    return findings


def strip_magic_tags(text: str) -> str:
    """Remove the markers, keeping the values.

    Called after placeholders are applied, so
    ``[[secret]]{{secret:k}}[[/secret]]`` becomes just ``{{secret:k}}`` — the
    marker has done its job once the value is in the vault.

    Handles both forms: ``[[secret]]`` and the self-naming ``[[secret:name]]``.
    """
    result = text
    for _ in range(500):  # runaway guard
        # `[[secret]]` includes the closing brackets, so it is not a substring of
        # `[[secret:name]]` — the two openers are genuinely distinct.
        plain = result.find(MAGIC_OPEN)
        named = MAGIC_OPEN_LABELLED.search(result)

        if named is not None and (plain == -1 or named.start() < plain):
            open_at, open_end = named.start(), named.end()
        elif plain != -1:
            open_at, open_end = plain, plain + len(MAGIC_OPEN)
        else:
            break

        close_at = result.find(MAGIC_CLOSE, open_end)
        if close_at == -1:
            break

        result = result[:open_at] + result[open_end:close_at] + result[close_at + len(MAGIC_CLOSE) :]

    # An unclosed marker is a typo, not content — drop it so it cannot sit in the
    # note looking meaningful.
    result = MAGIC_OPEN_LABELLED.sub("", result)
    return result.replace(MAGIC_OPEN, "").replace(MAGIC_CLOSE, "")


def resolve_overlaps(findings: list[Finding]) -> list[Finding]:
    """Drop overlapping findings, keeping the strongest.

    `google password: 1234567` matches the password rule *and* the generic key
    rule. Reporting both would show two checkboxes for one value, and protecting
    both would write the same secret twice.
    """
    ordered = sorted(
        findings,
        key=lambda f: (
            -f.confidence,
            -SEVERITY_RANK.get(f.severity, 0),
            -(f.end - f.start),
        ),
    )

    accepted: list[Finding] = []
    for candidate in ordered:
        if not any(
            candidate.start < other.end and other.start < candidate.end for other in accepted
        ):
            accepted.append(candidate)

    return sorted(accepted, key=lambda f: f.start)


def detect_secrets(text: str) -> list[Finding]:
    """Scan ``text`` and return the findings a caller should be asked about.

    Pure and synchronous: same input, same output, no side effects.

    The rule passes run over the text with magic-tag regions blanked out. The
    markers are syntax the author added, not content to be scanned, and leaving
    them in makes `[[secret:Name]]` look like a `secret: value` assignment.
    """
    if not text.strip():
        return []

    candidates: list[Finding] = []
    scannable = mask_magic_spans(text)

    for rule in ALL_RULES:
        for match in rule.pattern.finditer(scannable):
            raw = match.group(rule.value_group) if rule.value_group else match.group(0)
            if not raw:
                continue

            # Locate the value inside the whole match so offsets point at the
            # secret, not at the label.
            offset_in_match = 0 if rule.value_group == 0 else match.group(0).rfind(raw)
            start = match.start() + (offset_in_match if offset_in_match >= 0 else 0)
            end = start + len(raw)

            if is_placeholder(raw):
                continue

            entropy = shannon_entropy(raw)
            confidence = rule.confidence
            if entropy >= 3.5:
                confidence += 0.03
            # A very short value under a contextual label is still a secret the
            # author labelled as one — keep it, with less confidence.
            if len(raw) < 6:
                confidence -= 0.1

            candidates.append(
                Finding(
                    start=start,
                    end=end,
                    value=raw,
                    # The label comes from the original text, not the masked copy,
                    # so a marker on the line does not blank the author's words.
                    label=_derive_label(text, start, rule.type.replace("_", " ")),
                    type=rule.type,
                    severity=rule.severity,
                    confidence=max(0.0, min(confidence, 0.999)),
                    entropy=round(entropy, 2),
                    # MEDIUM findings are plausible but not certain — let the
                    # caller opt in rather than pre-selecting.
                    selected=rule.severity != "MEDIUM",
                    rule=rule.id,
                )
            )

    return resolve_overlaps(
        [
            *candidates,
            *_detect_stacked_values(text, scannable),
            *_detect_manual_tags(text),
        ]
    )


RULE_REASONS: dict[str, str] = {
    "magic_tag": "you marked it by hand",
    "stacked_block": "a value on its own line under a heading",
    "private_key": "a private-key header",
    "github_pat": "a GitHub token format",
    "github_pat_fine": "a GitHub token format",
    "slack_token": "a Slack token format",
    "google_api_key": "a Google API key format",
    "openai_key": "an OpenAI key format",
    "jwt": "a JWT format",
    "connection_string": "a connection string with a password",
    "bearer": "a Bearer token in a header",
    "password_assignment": "the word password next to a value",
    "key_assignment": "a key/token label next to a value",
}


def rule_reason(rule_id: str) -> str:
    """A short explanation of why a finding was flagged.

    Shown next to the finding so the caller can judge a MEDIUM one instead of
    trusting a bare percentage.
    """
    return RULE_REASONS.get(rule_id, "a secret-like pattern")


@dataclass
class PreviewResult:
    """What a preview pass reports back."""

    findings: list[Finding] = field(default_factory=list)
    # Values the rules believe are secrets that carry no magic tag. This is the
    # cross-check: an agent that marked one secret but left another bare gets
    # told about it before anything is stored.
    untagged: list[Finding] = field(default_factory=list)
    # Magic tags whose content the rules would not have flagged on their own.
    # Not an error — the agent may know something the rules do not.
    tagged_only: list[Finding] = field(default_factory=list)
    placeholder_keys: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "findings": [f.to_dict() for f in self.findings],
            "untagged": [f.to_dict() for f in self.untagged],
            "tagged_only": [f.to_dict() for f in self.tagged_only],
            "placeholder_keys": self.placeholder_keys,
            "counts": {
                "total": len(self.findings),
                "tagged": sum(1 for f in self.findings if f.manual),
                "untagged": len(self.untagged),
                "placeholders": len(self.placeholder_keys),
            },
        }


def preview(text: str) -> PreviewResult:
    """Run detection and separate what is tagged from what is not.

    This is the cross-check the operator asked for: the agent says "these are the
    secrets", the rules say "and here is one you missed". Neither side is trusted
    alone.
    """
    findings = detect_secrets(text)
    tagged = [f for f in findings if f.manual]
    untagged = [f for f in findings if not f.manual]

    return PreviewResult(
        findings=findings,
        untagged=untagged,
        # A magic-tagged value the rules would not have found. Worth surfacing so
        # the agent can see the rules disagreed, not silently dropped.
        tagged_only=tagged,
        placeholder_keys=SMART_TEXT_PLACEHOLDER.findall(text),
    )
