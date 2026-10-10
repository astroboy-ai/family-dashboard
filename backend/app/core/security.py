from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from pwdlib import PasswordHash

from app.core.config import Settings, get_settings


password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        return password_hash.verify(password, encoded_hash)
    except (ValueError, TypeError):
        return False


def create_access_token(
    *,
    member_id: str,
    household_id: str,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> str:
    app_settings = settings or get_settings()
    issued_at = now or datetime.now(UTC)
    claims = {
        "sub": member_id,
        "household_id": household_id,
        "token_type": "access",
        "iat": issued_at,
        "exp": issued_at + timedelta(minutes=app_settings.access_token_minutes),
    }
    return jwt.encode(claims, app_settings.jwt_secret, algorithm="HS256")


def decode_access_token(
    token: str,
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    app_settings = settings or get_settings()
    claims = jwt.decode(
        token,
        app_settings.jwt_secret,
        algorithms=["HS256"],
        options={"verify_exp": now is None},
        leeway=0,
    )
    if claims.get("token_type") != "access":
        raise jwt.InvalidTokenError("wrong token type")
    if now is not None:
        expires_at = datetime.fromtimestamp(claims["exp"], tz=UTC)
        if expires_at <= now:
            raise jwt.ExpiredSignatureError("token expired")
    return claims