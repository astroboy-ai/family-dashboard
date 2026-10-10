"""Mint an agent device token for the internal agent API.

Run inside the backend container:

    docker exec -w /app familyos-backend-1 \\
      sh -c 'PYTHONPATH=/app /app/.venv/bin/python scripts/mint_agent_token.py \\
             --label "R2-D2 (Hermes)" --scopes notes.read'

The plaintext token is printed once and never stored. Only its SHA-256 hash is
written to ``device_tokens``, so a copy of the database cannot be replayed
against the API.

An agent token has no ``member_id`` by default: it acts for the household with
exactly the scopes it is granted, rather than impersonating a family member.
Pass ``--member`` only when an agent genuinely must act as a specific person.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.db import session_factory
from app.models import DeviceToken, Household
from app.services.agent_tokens import generate_token, hash_token


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mint an agent device token.")
    parser.add_argument("--label", required=True, help="Human-readable owner, e.g. 'R2-D2 (Hermes)'")
    parser.add_argument(
        "--scopes",
        default="notes.read",
        help="Comma-separated scopes. Default: notes.read",
    )
    parser.add_argument("--member", default=None, help="Optional family member UUID to act as")
    parser.add_argument("--days", type=int, default=365, help="Lifetime in days. 0 = never expires")
    parser.add_argument("--household", default=None, help="Household UUID (default: the only one)")
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    scopes = [scope.strip() for scope in args.scopes.split(",") if scope.strip()]

    async with session_factory() as session:
        if args.household:
            household = await session.get(Household, args.household)
        else:
            household = (await session.execute(select(Household).limit(2))).scalars().all()
            if len(household) != 1:
                print(
                    f"Expected exactly one household, found {len(household)}. "
                    "Pass --household explicitly.",
                    file=sys.stderr,
                )
                return 2
            household = household[0]

        if household is None:
            print("Household not found.", file=sys.stderr)
            return 2

        token = generate_token()
        expires_at = (
            None if args.days <= 0 else datetime.now(UTC) + timedelta(days=args.days)
        )

        session.add(
            DeviceToken(
                household_id=household.id,
                member_id=args.member,
                label=args.label,
                token_hash=hash_token(token),
                scopes=scopes,
                expires_at=expires_at,
            )
        )
        await session.commit()

        print("token=" + token)
        print("label=" + args.label)
        print("household=" + str(household.id))
        print("member=" + (args.member or "(none — acts for the household)"))
        print("scopes=" + ",".join(scopes))
        print("expires=" + (expires_at.isoformat() if expires_at else "never"))
        print()
        print("Store this token now — it cannot be read back.")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
