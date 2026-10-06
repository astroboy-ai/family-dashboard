"""End-to-end smoke for the Archify import path over the real public origin.

Walks the exact sequence the UI performs — list, multipart upload, fetch, rename,
delete — against ``https://familyos.logeebox.com``, so it exercises Cloudflare,
the Next.js rewrite and the multipart parser together rather than only the
service layer that ``smoke_graph_artifacts.py`` covers.

Run inside the backend container, which is the only place that has both the JWT
secret (to mint a session) and the internal origin (to compare against):

    docker exec -e PYTHONPATH=/app familyos-backend-1 \\
        /app/.venv/bin/python /app/scripts/smoke_artifact_http.py

Known edge behaviour
--------------------
Cloudflare appends its Web Analytics beacon
(``static.cloudflareinsights.com/beacon.min.js``) to **any** ``text/html``
response, inserted just before ``</body>``. So a download through the public
origin is not byte-identical to what was uploaded. The stored object is
untouched — only the served copy grows — which is why byte-exactness is asserted
against the internal origin and the public origin is checked for intact content.
This is a property of the zone, not of the import path.
"""

import asyncio
import io
import json
import urllib.error
import urllib.request
import uuid

from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import session_factory
from app.core.security import create_access_token
from app.models import FamilyMember

PUBLIC = "https://familyos.logeebox.com"
INTERNAL = "http://127.0.0.1:8000"
BEACON_HOST = b"cloudflareinsights.com"

# A genuinely interactive artifact: inline JS mutates the DOM, so a viewer that
# executes it is distinguishable from one that merely shows source.
SAMPLE_HTML = b"""<!doctype html>
<html><head><meta charset="utf-8"><title>Smoke graph</title>
<style>body{font-family:sans-serif;background:#111;color:#eee}</style></head>
<body><h1 id="t">loading</h1>
<script>document.getElementById('t').textContent='ARCHIFY OK '+ (6*7);</script>
</body></html>"""

PASS, FAIL = [], []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{' — ' + detail if detail else ''}")


def call(path, method="GET", body=None, ctype=None, token=None, base=None):
    request = urllib.request.Request((base or PUBLIC) + path, method=method)
    # Cloudflare answers 1010 (browser-signature ban) for urllib's default UA.
    request.add_header("User-Agent", "FamilyOS-Smoke/1.0 (+familyos)")
    if ctype:
        request.add_header("Content-Type", ctype)
    if token:
        request.add_header("Cookie", f"access_token={token}")
    if body is not None:
        request.data = body
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def multipart(fields, filename, content, ctype):
    boundary = "----e2e" + uuid.uuid4().hex
    out = io.BytesIO()
    for key, value in fields.items():
        out.write(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode()
        )
    out.write(
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
        f'filename="{filename}"\r\nContent-Type: {ctype}\r\n\r\n'.encode()
    )
    out.write(content)
    out.write(f"\r\n--{boundary}--\r\n".encode())
    return out.getvalue(), f"multipart/form-data; boundary={boundary}"


async def mint_token() -> str:
    async with session_factory() as session:
        member = (
            await session.execute(
                select(FamilyMember).where(FamilyMember.role == "parent").limit(1)
            )
        ).scalars().first()
        if member is None:
            member = (await session.execute(select(FamilyMember).limit(1))).scalars().first()
        return create_access_token(
            member_id=str(member.id), household_id=str(member.household_id)
        )


def main() -> None:
    token = asyncio.run(mint_token())

    print("== authenticated list ==")
    code, body = call("/api/graph/artifacts", token=token)
    check("list returns 200 with a session", code == 200, f"status={code}")
    if code != 200:
        print("      body:", body[:200])
        return
    before = json.loads(body)["total"]
    print(f"      {before} artifact(s) before")

    print("\n== multipart upload (the UI path) ==")
    payload, ctype = multipart(
        {"name": "E2E smoke graph", "source": "e2e"}, "smoke.html", SAMPLE_HTML, "text/html"
    )
    code, body = call("/api/graph/artifacts", "POST", payload, ctype, token=token)
    check("upload returns 201", code == 201, f"status={code}")
    if code != 201:
        print("      body:", body[:300])
        return
    artifact = json.loads(body)
    check("kind is html", artifact["kind"] == "html", f"kind={artifact['kind']}")
    check("size matches what was sent", artifact["size_bytes"] == len(SAMPLE_HTML),
          f"{artifact['size_bytes']} bytes")
    check("media asset linked", artifact["media_asset_id"] is not None)

    print("\n== bytes are served back to the viewer ==")
    media = f"/api/media/{artifact['media_asset_id']}/download"

    code, served = call(media, token=token)
    check("download returns 200", code == 200, f"status={code}")

    # Everything up to the injection point must match; the beacon lands before
    # </body>, so the served copy is not a prefix of the original.
    head, _, _ = SAMPLE_HTML.partition(b"</body>")
    check("content intact up to the injection point", served.startswith(head),
          f"{len(served)} served vs {len(SAMPLE_HTML)} uploaded")
    check("artifact's own script preserved", b"ARCHIFY OK" in served)
    check("document still closes correctly", served.rstrip().endswith(b"</html>"))
    check("the only addition is the edge beacon", BEACON_HOST in served,
          f"beacon present={BEACON_HOST in served}")

    code, origin = call(media, token=token, base=INTERNAL)
    check("byte-exact at the origin (no edge rewriting)", origin == SAMPLE_HTML,
          f"{len(origin)} bytes")

    print("\n== list reflects the import ==")
    code, body = call("/api/graph/artifacts", token=token)
    after = json.loads(body)["total"] if code == 200 else -1
    check("total incremented", after == before + 1, f"{before} -> {after}")

    print("\n== rename ==")
    code, body = call(
        f"/api/graph/artifacts/{artifact['id']}",
        "PATCH",
        json.dumps({"name": "E2E renamed"}).encode(),
        "application/json",
        token=token,
    )
    check("rename returns 200", code == 200, f"status={code}")
    if code == 200:
        check("name applied", json.loads(body)["name"] == "E2E renamed")

    print("\n== delete ==")
    code, _ = call(f"/api/graph/artifacts/{artifact['id']}", "DELETE", token=token)
    check("delete returns 204", code == 204, f"status={code}")
    code, body = call("/api/graph/artifacts", token=token)
    final = json.loads(body)["total"] if code == 200 else -1
    check("total back to baseline", final == before, f"{before} -> {final}")

    print(f"\n{'=' * 46}\n  {len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("  FAILED: " + ", ".join(FAIL))
    print("=" * 46)


if __name__ == "__main__":
    main()
