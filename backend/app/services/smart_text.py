"""Smart Text blocks, built by an agent.

A Smart Text block is free-form text with its secrets replaced by
``{{secret:<key>}}`` placeholders; the values live in the vault. The frontend
builds these from a paste-and-scan flow. This module lets an agent build the same
block from a list of secrets it has already identified — the operator's stated
workflow is "drop the messy text at my agent, she analyses it, she files it".

Why a shared helper instead of letting the tool assemble the block
------------------------------------------------------------------
The block is only safe if three things agree, and getting any one wrong silently
leaks or breaks:

1. **The key format** must match what the frontend mints (``sn-<slug>-<6hex>``),
   or the UI's ``segmentText`` still renders the placeholder but the metadata
   lookup misses and the chip loses its label.
2. **``data.secrets`` must hold no values.** ``embedding_jobs.block_text``
   flattens ``data`` and sends it to an external embedding provider, so a value
   that lands in this index leaves the household. Only labels and placeholders
   belong here.
3. **``text_content`` must hold only placeholders**, for the same reason.

Mirrors ``frontend-main/src/lib/secret-detector.ts``. Keep the two in step.
"""

from __future__ import annotations

import re
import secrets as _secrets
import uuid
from dataclasses import dataclass

from app.core.errors import AppError
from app.services import infisical

# Matches the frontend's PLACEHOLDER_PATTERN.
PLACEHOLDER_PATTERN = re.compile(r"\{\{secret:([^}]+)\}\}")

# Same ceiling the vault enforces per value.
MAX_SECRET_VALUE_BYTES = 64 * 1024


@dataclass(frozen=True)
class SecretInput:
    """One secret the agent identified in the source text."""

    label: str
    value: str
    type: str = "password"
    severity: str = "HIGH"


@dataclass(frozen=True)
class BuiltSecret:
    """What was stored, minus the value."""

    placeholder: str
    key: str
    label: str
    type: str
    severity: str


def vault_path_for_note(note_id: uuid.UUID | str) -> str:
    """The vault folder a note's secrets live in.

    Identical to the frontend's ``secretsPathFor`` and to the password-block
    path, so every secret belonging to one note sits together and deleting the
    note can drop the whole folder.
    """
    return f"/notes/{note_id}"


def _slug(label: str, fallback: str) -> str:
    """Lowercase, non-alphanumeric runs to single dashes, trimmed, max 40.

    Mirrors ``secretKeyFor`` in the frontend so a key minted here is
    indistinguishable from one the UI minted.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")[:40]
    return slug or fallback


def mint_key(label: str, secret_type: str) -> str:
    """``sn-<slug>-<6hex>``.

    The random suffix keeps two same-labelled secrets ("old password" twice)
    distinct without a lookup, and is short enough to read in the placeholder.
    """
    return f"sn-{_slug(label, secret_type)}-{_secrets.token_hex(3)}"


def placeholder_for(key: str) -> str:
    """Render a key back into the placeholder the note text carries."""
    return f"{{{{secret:{key}}}}}"


def placeholder_keys(text: str) -> list[str]:
    """Every placeholder key in ``text``, in order."""
    return PLACEHOLDER_PATTERN.findall(text)


async def build_smart_text(
    *,
    note_id: uuid.UUID,
    text: str,
    secrets_in: list[SecretInput],
) -> tuple[str, list[BuiltSecret], str]:
    """Store the secrets and rewrite ``text`` to carry placeholders.

    ``text`` is the source with each secret still present. Every occurrence of a
    value is replaced, not just the first: the same password written twice in a
    pasted page is one secret, and leaving the second copy behind would defeat
    the point.

    Returns ``(text_content, built, vault_path)``. ``built`` holds no values.

    Raises ``AppError`` if the vault refuses — the caller must not fall back to
    storing the value in the block, because a secret that quietly stays in the
    row is worse than a visible failure.
    """

    if not secrets_in:
        raise AppError("At least one secret is required", status_code=400, error_code="invalid_params")

    for item in secrets_in:
        if not item.value:
            raise AppError(
                f"Secret '{item.label}' has an empty value",
                status_code=400,
                error_code="invalid_params",
            )
        if len(item.value.encode("utf-8")) > MAX_SECRET_VALUE_BYTES:
            raise AppError(
                f"Secret '{item.label}' is too large for the vault",
                status_code=400,
                error_code="invalid_params",
            )

    path = vault_path_for_note(note_id)
    try:
        await infisical.ensure_folder(path)
    except infisical.InfisicalError as error:
        raise AppError(str(error), status_code=502, error_code="vault_error") from error

    built: list[BuiltSecret] = []
    result_text = text

    for item in secrets_in:
        key = mint_key(item.label, item.type)
        try:
            await infisical.set_secret(key, item.value, path=path, comment=item.label)
        except infisical.InfisicalError as error:
            raise AppError(str(error), status_code=502, error_code="vault_error") from error

        placeholder = placeholder_for(key)
        # Replace every occurrence. A value that appears twice is still one
        # secret, and the leftover copy is the leak this feature exists to stop.
        result_text = result_text.replace(item.value, placeholder)

        built.append(
            BuiltSecret(
                placeholder=placeholder,
                key=key,
                label=item.label,
                type=item.type,
                severity=item.severity,
            )
        )

    return result_text, built, path


def secrets_index(built: list[BuiltSecret]) -> list[dict[str, str]]:
    """The ``data.secrets`` array the UI reads.

    Labels and placeholders only — never a value. See the module docstring: this
    dict is flattened into the embedded text.
    """
    return [
        {
            "placeholder": item.placeholder,
            "key": item.key,
            "label": item.label,
            "type": item.type,
            "severity": item.severity,
        }
        for item in built
    ]
