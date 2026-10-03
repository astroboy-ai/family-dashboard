"""Vision / image understanding backed by the shared litellm gateway.

Used by the ``media.enrich`` outbox job: a photo the user asked to "AI analyse"
is described once, and the description is stored on the media asset (and copied
to the owning note block) so it becomes searchable text.

Kept deliberately small: one chat completion with an image part, OpenAI-compatible
shape, same egress path as embeddings (see :mod:`app.services.embeddings`).
"""

from __future__ import annotations

import base64
from dataclasses import dataclass

import httpx

from app.services.ai_settings import AiSettings


class VisionError(RuntimeError):
    """Raised when the vision provider cannot be reached or returns junk."""


DEFAULT_PROMPT = (
    "Describe this image for a family knowledge base. Reply in the same language "
    "as any text in the image (Traditional Chinese preferred). Cover: what it is, "
    "any readable text (OCR), key dates, amounts, names and actionable items. "
    "Be concise — 3 to 6 sentences."
)


@dataclass(frozen=True)
class VisionResult:
    description: str
    model: str


class VisionClient:
    """Calls ``POST {base_url}/chat/completions`` with an image part."""

    def __init__(self, settings: AiSettings, *, timeout: float = 60.0) -> None:
        self._settings = settings
        self._timeout = timeout

    @property
    def model(self) -> str:
        return self._settings.vision_model or self._settings.llm_model

    async def describe(self, image: bytes, *, mime: str, prompt: str | None = None) -> VisionResult:
        model = self.model
        if not model:
            raise VisionError("no vision or LLM model configured in admin settings")

        encoded = base64.b64encode(image).decode("ascii")
        headers = {"Content-Type": "application/json"}
        if self._settings.api_key:
            headers["Authorization"] = f"Bearer {self._settings.api_key}"

        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt or DEFAULT_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{encoded}"},
                        },
                    ],
                }
            ],
            "max_tokens": 600,
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._settings.base_url.rstrip('/')}/chat/completions",
                    json=payload,
                    headers=headers,
                )
        except httpx.HTTPError as error:
            raise VisionError(f"vision request failed: {error}") from error

        if response.status_code >= 400:
            raise VisionError(
                f"vision provider returned {response.status_code}: {response.text[:400]}"
            )

        try:
            body = response.json()
        except ValueError as error:
            raise VisionError("vision provider returned a non-JSON body") from error

        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            raise VisionError("vision provider returned no choices")

        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, list):
            # Some providers return the content as parts.
            content = "".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )
        if not isinstance(content, str) or not content.strip():
            raise VisionError("vision provider returned an empty description")

        return VisionResult(description=content.strip(), model=model)
