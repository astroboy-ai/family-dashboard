"""The vault's "use it, never read it" half.

``call_api_with_secret`` exists so a credential can be *used* without its
plaintext entering the caller's context. Two properties matter, and neither is
visible from reading the diff:

- the SSRF guard refuses everything that is not a public http(s) target, and
- the value is injected into the outbound request but never returned.
"""

import base64
import ipaddress

import pytest

from app.agent.executor import _redact_params
from app.agent.registry import registry
from app.services import outbound_http
from app.services.outbound_http import OutboundHttpError, validate_target

REFUSED = [
    "ftp://example.com/",
    "file:///etc/passwd",
    "javascript:alert(1)",
    "http://169.254.169.254/latest/meta-data/",  # cloud instance metadata
    "http://127.0.0.1:8000/mcp/",  # the backend's own port
    "http://127.1.2.3/",
    "https://10.0.0.5/",
    "https://172.16.4.4/",
    "https://192.168.1.1/",
    "http://0.0.0.0/",
    "http://100.64.1.1/",
    "https://198.51.100.9/",
    "http://[::1]/",
    "http://[::ffff:127.0.0.1]/",  # v4-mapped loopback
    "http://[fc00::1]/",
    "http://[64:ff9b::10.0.0.1]/",  # NAT64 embedding a private v4
    "http://[2002:7f00:1::]/",  # 6to4 embedding loopback
    "http://localhost/",
    "http://localhost./",  # trailing dot
    "http://infisical.internal/",
    "http://something.local/",
    "http://metadata.google.internal/",
    "https://user:pw@example.com/",  # credentials in the URL
    "http://familyos-backend:8000/mcp/",  # compose service name
]


@pytest.mark.parametrize("url", REFUSED)
def test_private_and_malformed_targets_are_refused(url: str) -> None:
    with pytest.raises(OutboundHttpError):
        validate_target(url)


def test_public_literal_targets_are_allowed() -> None:
    for url in ("https://1.1.1.1/", "http://93.184.216.34/x?y=1"):
        parsed, addresses = validate_target(url)
        assert addresses == [parsed.hostname]


def test_public_hostname_is_allowed() -> None:
    try:
        _, addresses = validate_target("https://example.com/")
    except OutboundHttpError as error:  # pragma: no cover - no DNS here
        pytest.skip(f"no DNS in this environment: {error}")
    assert addresses
    assert all(outbound_http._public(ipaddress.ip_address(a)) for a in addresses)


def test_ipv4_mapped_ipv6_is_checked_as_ipv4() -> None:
    assert outbound_http._public(ipaddress.ip_address("::ffff:8.8.8.8")) is True
    assert outbound_http._public(ipaddress.ip_address("::ffff:10.0.0.1")) is False


async def test_secret_is_injected_but_never_returned(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "s3cr3t-value-9f3a91"
    captured: dict = {}

    async def fake_get_secret(key: str, path: str = "/") -> str:
        assert key == "sn-orange-9f3a91"
        return secret

    async def fake_perform(**kwargs) -> dict:
        captured.update(kwargs)
        return {
            "status_code": 200,
            "url": "https://api.example.com/v1/me",
            # A response that echoes the credential back must not carry it out.
            "headers": {"x-echo": secret},
            "body": f'{{"token":"{secret}","ok":true}}',
            "truncated": False,
        }

    monkeypatch.setattr(outbound_http.infisical, "get_secret", fake_get_secret)
    monkeypatch.setattr(outbound_http, "_perform", fake_perform)

    result = await outbound_http.call_with_secret(
        # A public literal address: validate_target runs for real here, and a
        # literal needs no DNS, so the test stays hermetic.
        url="https://93.184.216.34/v1/me",
        secret_key="sn-orange-9f3a91",
        inject_as="bearer",
    )

    # Injected on the way out...
    assert captured["request_headers"]["Authorization"] == f"Bearer {secret}"
    # ...and absent on the way back.
    assert secret not in result["body"]
    assert secret not in str(result["headers"])
    assert "[redacted]" in result["body"]
    # The key is a pointer and stays, so the audit row can name the credential.
    assert result["key"] == "sn-orange-9f3a91"


async def test_query_injection_puts_the_value_in_the_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "k-12345"
    captured: dict = {}

    async def fake_get_secret(key: str, path: str = "/") -> str:
        return secret

    async def fake_perform(**kwargs) -> dict:
        captured.update(kwargs)
        return {
            "status_code": 200,
            "url": kwargs["target_url"],
            "headers": {},
            "body": "",
            "truncated": False,
        }

    monkeypatch.setattr(outbound_http.infisical, "get_secret", fake_get_secret)
    monkeypatch.setattr(outbound_http, "_perform", fake_perform)

    result = await outbound_http.call_with_secret(
        url="https://93.184.216.34/v1/x?a=1",
        secret_key="sn-k",
        inject_as="query",
        name="api_key",
    )

    assert f"api_key={secret}" in captured["target_url"]
    assert secret not in result["url"]
    assert "[redacted]" in result["url"]


async def test_basic_auth_redacts_the_value_and_its_encoding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "hunter2-xyz"
    encoded = base64.b64encode(f"manager:{secret}".encode()).decode()
    captured: dict = {}

    async def fake_get_secret(key: str, path: str = "/") -> str:
        return secret

    async def fake_perform(**kwargs) -> dict:
        captured.update(kwargs)
        return {
            "status_code": 200,
            "url": "https://x.example.com/",
            "headers": {},
            "body": f"echo {encoded}",
            "truncated": False,
        }

    monkeypatch.setattr(outbound_http.infisical, "get_secret", fake_get_secret)
    monkeypatch.setattr(outbound_http, "_perform", fake_perform)

    result = await outbound_http.call_with_secret(
        url="https://93.184.216.34/",
        secret_key="sn-router",
        inject_as="basic_auth",
        username="manager",
    )

    assert captured["request_headers"]["Authorization"] == f"Basic {encoded}"
    assert encoded not in result["body"]
    assert "[redacted]" in result["body"]


async def test_a_json_object_body_is_serialised(monkeypatch: pytest.MonkeyPatch) -> None:
    """The MCP layer hands a JSON body over as a dict, not a string.

    Any argument that looks like JSON is parsed into a real object before
    pydantic validates it, so `body: str` rejected every JSON body outright —
    which is most API calls. A non-string has to be serialised back.
    """

    async def fake_get_secret(key: str, path: str = "/") -> str:
        return "s"

    captured: dict = {}

    async def fake_perform(**kwargs) -> dict:
        captured.update(kwargs)
        return {"status_code": 200, "url": "", "headers": {}, "body": "", "truncated": False}

    monkeypatch.setattr(outbound_http.infisical, "get_secret", fake_get_secret)
    monkeypatch.setattr(outbound_http, "_perform", fake_perform)

    await outbound_http.call_with_secret(
        url="https://93.184.216.34/",
        secret_key="sn-k",
        method="POST",
        body={"jsonrpc": "2.0", "id": 1},
    )

    assert captured["payload"] == b'{"jsonrpc": "2.0", "id": 1}'


async def test_refused_target_is_rejected_before_the_vault_is_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An SSRF attempt must not cost a secret read.

    Ordering, not just outcome: the guard has to run first, so a private target
    never reaches the vault and never lands in the audit log as a read.
    """

    async def exploding_get_secret(key: str, path: str = "/") -> str:
        raise AssertionError("the vault was read for a refused target")

    monkeypatch.setattr(outbound_http.infisical, "get_secret", exploding_get_secret)

    with pytest.raises(OutboundHttpError):
        await outbound_http.call_with_secret(
            url="http://169.254.169.254/latest/meta-data/",
            secret_key="sn-anything",
            inject_as="bearer",
        )


async def test_incomplete_or_unknown_injection_arguments_are_refused() -> None:
    # All of these fail before the vault is touched, so no secret is read.
    for kwargs in (
        {"inject_as": "header"},  # no name
        {"inject_as": "query"},  # no name
        {"inject_as": "basic_auth"},  # no username
        {"inject_as": "telepathy"},
        {"method": "TRACE"},
    ):
        with pytest.raises(OutboundHttpError):
            await outbound_http.call_with_secret(
                url="https://api.example.com/", secret_key="sn-k", **kwargs
            )


def test_tool_is_registered_and_gated_on_secrets_read() -> None:
    import app.agent.tools  # noqa: F401  — populates the registry via @register

    definition = registry["call_api_with_secret"]
    assert definition.permissions == ("secrets.read",)
    # Not a write tool: it changes no household state, it reads a secret and
    # calls out. Declaring ``mutates`` would demand a .write scope and fail
    # closed in the executor.
    assert definition.mutates is False


def test_audit_redaction_recurses_into_nested_arguments() -> None:
    redacted = _redact_params(
        {"headers": {"Authorization": "Bearer abc", "X-Trace": "1"}, "key": "sn-x"}
    )
    assert redacted["headers"]["Authorization"] == "[redacted]"
    assert redacted["headers"]["X-Trace"] == "1"
    # A key is a pointer, not a value — it stays readable on purpose.
    assert redacted["key"] == "sn-x"
