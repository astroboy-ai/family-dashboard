import re
import uuid

from pydantic import BaseModel, Field, field_validator


class MediaPresignRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    mime: str = Field(min_length=3, max_length=160)
    size: int = Field(gt=0, le=100 * 1024 * 1024)
    sha256: str = Field(min_length=64, max_length=64)

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        if not re.fullmatch(r"[0-9a-fA-F]{64}", value):
            raise ValueError("sha256 must be a 64-character hexadecimal digest")
        return value.lower()


class MediaPresignResponse(BaseModel):
    asset_id: uuid.UUID
    upload_url: str | None
    fields: dict[str, str] = Field(default_factory=dict)
    deduplicated: bool = False


class MediaCompleteResponse(BaseModel):
    asset_id: uuid.UUID
    status: str
    queued: bool
    already_complete: bool = False