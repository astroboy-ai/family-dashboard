"""AES-GCM encryption for password blocks.

Why this exists
---------------
A password block holds a secret the user typed. Storing it in plaintext in
``note_blocks.data`` means the value is readable by anything that can read the
row — a database dump, a backup, a log line, an agent with ``notes.read``.

Design
------
* **AES-256-GCM** — authenticated encryption. A tampered ciphertext fails to
  decrypt rather than silently returning garbage, which matters because the
  failure mode we are protecting against is a wrong password being *shown*, not
  just a wrong password being *stored*.
* **Server-held key** — the key lives in the process environment, never in the
  database. An attacker who gets the database but not the server gets nothing.
* **Agent-readable by scope** — an agent with ``notes.read.secrets`` can ask for
  the plaintext; one without it gets a masked placeholder. The ciphertext is
  always stored, so granting the scope later needs no migration.

The key is a 32-byte value, base64-encoded in the environment as
``FAMILYOS_SECRET_KEY``. It is read once at import; a missing key raises at
startup rather than at first use, so a misconfigured deploy fails loudly
instead of silently storing plaintext.
"""

from __future__ import annotations

import base64
import os
from typing import Final

import structlog

logger = structlog.get_logger(__name__)

_KEY_ENV_VAR: Final = "FAMILYOS_SECRET_KEY"
_KEY_BYTES: Final = 32
_NONCE_BYTES: Final = 12

_key: bytes | None = None


class SecretKeyError(RuntimeError):
    """The encryption key is missing or malformed."""


def _load_key() -> bytes:
    """Read and validate the key from the environment.

    Raises at import time when the key is absent or the wrong length, so a
    deploy that forgot it fails on boot rather than on the first write.
    """

    raw = os.environ.get(_KEY_ENV_VAR)
    if not raw:
        raise SecretKeyError(
            f"{_KEY_ENV_VAR} is not set. Generate one with: "
            f"python3 -c \"import base64,os;print(base64.b64encode(os.urandom(32)).decode())\""
        )
    try:
        key = base64.b64decode(raw, validate=True)
    except Exception as error:  # noqa: BLE001
        raise SecretKeyError(
            f"{_KEY_ENV_VAR} is not valid base64: {error}"
        ) from error
    if len(key) != _KEY_BYTES:
        raise SecretKeyError(
            f"{_KEY_ENV_VAR} must decode to {_KEY_BYTES} bytes, got {len(key)}"
        )
    return key


try:
    _key = _load_key()
except SecretKeyError:
    # Import must still succeed so the rest of the app boots; the error is
    # raised again on the first encrypt/decrypt call, which is where a human
    # will see it. Logged here so the boot log carries the reason too.
    logger.error("secret_key_missing_or_malformed", var=_KEY_ENV_VAR)
    _key = None


def _require_key() -> bytes:
    if _key is None:
        raise SecretKeyError(
            f"{_KEY_ENV_VAR} is not set or malformed; cannot encrypt or decrypt secrets"
        )
    return _key


def encrypt(plaintext: str) -> str:
    """Encrypt a string. Returns ``base64(nonce + ciphertext + tag)``.

    The nonce is random per call, so encrypting the same password twice yields
    different ciphertext — important because identical ciphertext would leak
    that two blocks hold the same secret.
    """

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = os.urandom(_NONCE_BYTES)
    ciphertext = AESGCM(_require_key()).encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ciphertext).decode("ascii")


def decrypt(token: str) -> str:
    """Decrypt a value produced by :func:`encrypt`.

    Raises ``ValueError`` on a bad tag — the ciphertext was tampered with, or
    the key changed. Callers should surface that as a distinct failure rather
    than showing a wrong password.
    """

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    try:
        raw = base64.b64decode(token, validate=True)
    except Exception as error:  # noqa: BLE001
        raise ValueError(f"secret is not valid base64: {error}") from error
    if len(raw) < _NONCE_BYTES + 16:
        raise ValueError("secret is too short to be a valid ciphertext")
    nonce, ciphertext = raw[:_NONCE_BYTES], raw[_NONCE_BYTES:]
    try:
        plaintext = AESGCM(_require_key()).decrypt(nonce, ciphertext, None)
    except Exception as error:  # noqa: BLE001
        raise ValueError(f"secret failed to decrypt (wrong key or tampered): {error}") from error
    return plaintext.decode("utf-8")


def is_encrypted(value: object) -> bool:
    """True when a stored value looks like one of ours.

    Used to tell an encrypted block from a legacy plaintext one during the
    read path, so existing rows keep working until they are next edited.
    """

    if not isinstance(value, str):
        return False
    if not value:
        return False
    try:
        raw = base64.b64decode(value, validate=True)
    except Exception:  # noqa: BLE001
        return False
    return len(raw) >= _NONCE_BYTES + 16
