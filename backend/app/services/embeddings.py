"""Embedding provider backed by the shared litellm gateway.

litellm is the single egress point for model calls on this host, so the
backend talks OpenAI-compatible HTTP to it rather than holding provider keys.
Configuration comes from the household settings (see
:mod:`app.services.ai_settings`) so an operator can change model or dimension
from the admin page without redeploying.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import httpx

from app.services.ai_settings import AiSettings


class EmbeddingError(RuntimeError):
    """Raised when the embedding provider cannot be reached or returns junk."""


@dataclass(frozen=True)
class EmbeddingResult:
    vectors: list[list[float]]
    model: str
    dim: int


def content_hash(text: str) -> str:
    """Stable hash of the embedded text, used for job idempotency."""

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class EmbeddingClient:
    """Calls ``POST {base_url}/embeddings`` and validates the response shape."""

    def __init__(self, settings: AiSettings, *, timeout: float = 30.0) -> None:
        self._settings = settings
        self._timeout = timeout

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        if not texts:
            return EmbeddingResult(vectors=[], model=self._settings.embedding_model, dim=self._settings.embedding_dim)

        headers = {"Content-Type": "application/json"}
        if self._settings.api_key:
            headers["Authorization"] = f"Bearer {self._settings.api_key}"

        payload = {"model": self._settings.embedding_model, "input": texts}

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._settings.base_url.rstrip('/')}/embeddings",
                    json=payload,
                    headers=headers,
                )
        except httpx.HTTPError as error:
            raise EmbeddingError(f"embedding request failed: {error}") from error

        if response.status_code >= 400:
            raise EmbeddingError(
                f"embedding provider returned {response.status_code}: {response.text[:400]}"
            )

        try:
            body = response.json()
        except ValueError as error:
            raise EmbeddingError("embedding provider returned a non-JSON body") from error

        rows = body.get("data")
        if not isinstance(rows, list) or len(rows) != len(texts):
            raise EmbeddingError(
                f"expected {len(texts)} embeddings, got "
                f"{len(rows) if isinstance(rows, list) else 'none'}"
            )

        # Providers are not required to preserve input order; the OpenAI schema
        # carries an explicit index, so sort on it when present.
        if all(isinstance(row, dict) and "index" in row for row in rows):
            rows = sorted(rows, key=lambda row: row["index"])

        vectors: list[list[float]] = []
        for row in rows:
            vector = row.get("embedding") if isinstance(row, dict) else None
            if not isinstance(vector, list) or not vector:
                raise EmbeddingError("embedding provider returned an empty vector")
            vectors.append([float(value) for value in vector])

        dim = len(vectors[0])
        mismatched = {len(vector) for vector in vectors}
        if len(mismatched) != 1:
            raise EmbeddingError(f"provider returned inconsistent dimensions: {sorted(mismatched)}")

        configured = self._settings.embedding_dim
        if configured and dim != configured:
            raise EmbeddingError(
                f"provider returned {dim} dimensions but settings expect {configured}; "
                "update the embedding dimension in admin settings"
            )

        return EmbeddingResult(vectors=vectors, model=self._settings.embedding_model, dim=dim)
