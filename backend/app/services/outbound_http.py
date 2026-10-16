"""Outbound HTTP with an out-of-band secret — "use it, never read it".

An agent that needs a credential in order to *do* something (call an API, log
in) must not be handed the plaintext. Anything that enters a model's context is
sent to that model's provider, and that is the one place a household secret must
never go — the operator stated this as a hard rule.

So the vault grows a second half. ``get_vault_secret`` reads a value *into* the
caller, which necessarily puts it in the caller's context. This module resolves
a value *inside the backend*, injects it into an outbound request, and returns
only the response. The plaintext never reaches the caller, and the audit row
holds the key, never the secret.

Everything here fetches a caller-supplied URL, so the project's SSRF rules apply
in full — this backend shares a Docker network with the rest of the stack and
runs on a cloud host whose metadata service answers at ``169.254.169.254``:

1. ``http``/``https`` only.
2. Resolve the host and reject private, loopback, link-local and reserved
   addresses.
3. Re-validate every redirect hop: a public URL that 302s to ``localhost`` is
   the standard bypass.
4. Connect to the validated address rather than the hostname again, so DNS
   rebinding cannot swap in an internal address between the check and the
   connect.
5. Cap redirects, response size and total time.

The outbound request carries no ``Referer`` and no internal hostname: the
household's addresses are never volunteered to a third party.
"""

from __future__ import annotations

import base64
import ipaddress
import json
import socket
from typing import Any
from urllib.parse import quote, urljoin, urlparse, urlunparse

import httpx

from app.services import infisical

MAX_REDIRECTS = 3
ALLOWED_METHODS = ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE")
INJECT_MODES = ("bearer", "header", "query", "basic_auth")
USER_AGENT = "FamilyOS-Agent/1.0"

_REDACTED = "[redacted]"
_REDIRECT_CODES = (301, 302, 303, 307, 308)

# Names that only ever resolve inside a private network. Checked by name as well
# as by address: it costs nothing and catches a resolver that is slow to answer.
_BLOCKED_SUFFIXES = (
    ".local",
    ".internal",
    ".localhost",
    ".localdomain",
    ".home.arpa",
    ".lan",
)
_BLOCKED_NAMES = ("localhost", "metadata.google.internal", "instance-data")

# Spelled out as explicit networks rather than ``is_global`` so the rule does not
# move when the interpreter does — the image runs 3.12, the workstation 3.13, and
# ``is_global``'s definition has changed between releases.
_BLOCKED_V4 = tuple(
    ipaddress.ip_network(network)
    for network in (
        "0.0.0.0/8",  # "this network"
        "10.0.0.0/8",  # RFC1918
        "100.64.0.0/10",  # CGNAT
        "127.0.0.0/8",  # loopback
        "169.254.0.0/16",  # link-local — cloud instance metadata
        "172.16.0.0/12",  # RFC1918
        "192.0.0.0/24",  # IETF protocol assignments
        "192.0.2.0/24",  # TEST-NET-1
        "192.168.0.0/16",  # RFC1918
        "198.18.0.0/15",  # benchmarking
        "198.51.100.0/24",  # TEST-NET-2
        "203.0.113.0/24",  # TEST-NET-3
        "224.0.0.0/4",  # multicast
        "240.0.0.0/4",  # reserved
        "255.255.255.255/32",
    )
)
_BLOCKED_V6 = tuple(
    ipaddress.ip_network(network)
    for network in (
        "::/128",  # unspecified
        "::1/128",  # loopback
        "64:ff9b::/96",  # NAT64 — can embed a private v4
        "100::/64",  # discard-only
        "2001::/32",  # Teredo — can embed a private v4
        "2001:db8::/32",  # documentation
        "2002::/16",  # 6to4 — can embed a private v4
        "fc00::/7",  # unique local
        "fe80::/10",  # link-local
        "ff00::/8",  # multicast
    )
)


class OutboundHttpError(RuntimeError):
    """A refused or failed outbound call. The message is safe to show an agent."""


def _public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True only for a globally routable address.

    An IPv4-mapped IPv6 address (``::ffff:127.0.0.1``) is unwrapped first — it
    reaches the same interface as the v4 address it carries, so checking it as a
    v6 address would wave through a loopback target.
    """

    if isinstance(ip, ipaddress.IPv6Address):
        mapped = ip.ipv4_mapped
        if mapped is not None:
            return _public(mapped)
        return not any(ip in network for network in _BLOCKED_V6)
    return not any(ip in network for network in _BLOCKED_V4)


def _check_scheme_and_userinfo(url: str) -> None:
    """Cheap shape checks that need no DNS, so they run before touching the vault."""

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise OutboundHttpError(
            f"Only http and https URLs are allowed, not '{parsed.scheme or 'none'}'."
        )
    if parsed.username or parsed.password:
        raise OutboundHttpError(
            "URLs with embedded credentials are refused — file the credential in the "
            "vault and let this tool inject it."
        )
    if not parsed.hostname:
        raise OutboundHttpError("The URL has no host.")
    try:
        parsed.port
    except ValueError as error:
        raise OutboundHttpError("The URL has an invalid port.") from error


def validate_target(url: str) -> tuple[Any, list[str]]:
    """Validate a URL for outbound fetching. Returns (parsed, validated addresses).

    Raises ``OutboundHttpError`` for anything that is not a public http(s)
    target. The resolved addresses are returned so the caller can connect to a
    vetted address instead of resolving the name a second time.
    """

    _check_scheme_and_userinfo(url)
    parsed = urlparse(url)
    host = parsed.hostname
    assert host is not None  # _check_scheme_and_userinfo proved this

    lowered = host.casefold().rstrip(".")
    if lowered in _BLOCKED_NAMES or lowered.endswith(_BLOCKED_SUFFIXES):
        raise OutboundHttpError(f"Refusing to connect to '{host}': it is a private name.")

    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    try:
        literal: ipaddress.IPv4Address | ipaddress.IPv6Address | None = ipaddress.ip_address(
            host
        )
    except ValueError:
        literal = None

    if literal is not None:
        if not _public(literal):
            raise OutboundHttpError(
                f"Refusing to connect to '{host}': it is not a public address."
            )
        return parsed, [str(literal)]

    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as error:
        raise OutboundHttpError(f"Could not resolve '{host}'.") from error

    addresses = sorted({str(info[4][0]) for info in infos})
    if not addresses:
        raise OutboundHttpError(f"Could not resolve '{host}'.")
    # Every answer has to be public, not just the first: a name that resolves to
    # one public and one private address would otherwise be a coin flip.
    if not all(_public(ipaddress.ip_address(address)) for address in addresses):
        raise OutboundHttpError(
            f"Refusing to connect to '{host}': it resolves to a non-public address."
        )
    return parsed, addresses


def _redact(text: str, forms: list[str]) -> str:
    for form in forms:
        if form:
            text = text.replace(form, _REDACTED)
    return text


def _pin(parsed: Any, address: str) -> str:
    """Rewrite a URL to connect to a validated address, keeping the original host.

    The ``Host`` header and the TLS SNI name stay the real hostname, so
    certificate verification is unchanged — only the address actually dialled is
    pinned.
    """

    netloc = f"[{address}]" if ":" in address else address
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if port not in (80, 443):
        netloc = f"{netloc}:{port}"
    return urlunparse(parsed._replace(netloc=netloc))


async def _send_once(
    client: httpx.AsyncClient,
    *,
    method: str,
    parsed: Any,
    address: str,
    headers: dict[str, str],
    body: bytes | None,
    content_type: str,
    timeout: httpx.Timeout,
) -> httpx.Response:
    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    send_headers = dict(headers)
    send_headers["Host"] = host if port in (80, 443) else f"{host}:{port}"
    if body is not None:
        send_headers.setdefault("Content-Type", content_type)

    # httpcore reads this extension and uses it as the TLS server name, so the
    # certificate is still verified against the hostname rather than the address.
    extensions: dict[str, Any] = {}
    if parsed.scheme == "https":
        extensions["sni_hostname"] = host

    request = client.build_request(
        method,
        _pin(parsed, address),
        headers=send_headers,
        content=body,
        extensions=extensions,
        timeout=timeout,
    )
    return await client.send(request, stream=True)


async def call_with_secret(
    *,
    url: str,
    method: str = "GET",
    secret_key: str,
    secret_path: str = "/",
    inject_as: str = "bearer",
    name: str | None = None,
    username: str | None = None,
    headers: dict[str, str] | None = None,
    # The MCP layer parses an argument that looks like JSON into a real object
    # before pydantic ever sees it, so a JSON body arrives as a dict and a bare
    # `str` annotation rejects it outright. Accept both shapes; a non-string is
    # serialised back to JSON below.
    body: str | dict[str, Any] | list[Any] | None = None,
    content_type: str = "application/json",
    timeout_s: float = 20.0,
    max_response_bytes: int = 200_000,
) -> dict[str, Any]:
    """Call ``url`` with a vault secret injected, returning only the response.

    The secret's plaintext exists only inside this function. It is never
    returned, and any occurrence of it in the response — or of the Basic-auth
    encoding of it — is replaced with ``[redacted]`` before the result is built.
    """

    method = method.strip().upper()
    if method not in ALLOWED_METHODS:
        raise OutboundHttpError(
            f"Method '{method}' is not allowed. Use one of: {', '.join(ALLOWED_METHODS)}."
        )

    mode = inject_as.strip().casefold()
    if mode not in INJECT_MODES:
        raise OutboundHttpError(
            f"inject_as must be one of: {', '.join(INJECT_MODES)}."
        )
    if mode == "header" and not name:
        raise OutboundHttpError("inject_as='header' needs the header 'name'.")
    if mode == "query" and not name:
        raise OutboundHttpError("inject_as='query' needs the parameter 'name'.")
    if mode == "basic_auth" and not username:
        raise OutboundHttpError("inject_as='basic_auth' needs a 'username'.")

    # Validate the target BEFORE touching the vault: an SSRF attempt must not
    # cost a secret read, and must not be recorded as one either. The host is
    # unaffected by query injection, and every redirect hop is re-validated
    # inside _perform, so this does not replace the per-hop check.
    validate_target(url)

    value = await infisical.get_secret(secret_key, path=secret_path)
    if not value:
        raise OutboundHttpError(f"Secret '{secret_key}' has no value.")

    request_headers = {str(k): str(v) for k, v in (headers or {}).items()}
    request_headers.setdefault("User-Agent", USER_AGENT)
    request_headers.setdefault("Accept", "*/*")
    # Redact every spelling of the secret that could come back in a response.
    redact_forms = [value]
    target_url = url

    if mode == "bearer":
        request_headers["Authorization"] = f"Bearer {value}"
    elif mode == "header":
        request_headers[str(name)] = value
    elif mode == "query":
        parsed = urlparse(target_url)
        separator = "&" if parsed.query else "?"
        target_url = urlunparse(
            parsed._replace(
                query=f"{parsed.query}{separator}{quote(str(name), safe='')}={quote(value, safe='')}"
            )
        )
    else:  # basic_auth
        encoded = base64.b64encode(f"{username}:{value}".encode()).decode()
        request_headers["Authorization"] = f"Basic {encoded}"
        redact_forms.append(encoded)

    if body is not None and not isinstance(body, str):
        body = json.dumps(body, ensure_ascii=False)
    if body is not None and len(body.encode("utf-8")) > 256 * 1024:
        raise OutboundHttpError("The request body is larger than 256 KiB.")

    payload = body.encode("utf-8") if body is not None else None
    timeout = httpx.Timeout(timeout_s)

    try:
        result = await _perform(
            target_url=target_url,
            method=method,
            request_headers=request_headers,
            payload=payload,
            content_type=content_type,
            timeout=timeout,
            max_response_bytes=max_response_bytes,
        )
    except httpx.HTTPError as error:
        # An httpx message quotes the URL, and with inject_as='query' the URL
        # carries the secret. Redact before it can reach the caller's context.
        raise OutboundHttpError(
            _redact(f"Request failed: {error}", redact_forms)
        ) from error

    # Redaction lives here, not in _perform, so that it cannot be bypassed:
    # _perform owns the transport, this function owns the secret.
    result["url"] = _redact(str(result["url"]), redact_forms)
    result["headers"] = {
        str(key): _redact(str(value), redact_forms)
        for key, value in result["headers"].items()
    }
    result["body"] = _redact(str(result["body"]), redact_forms)
    result["injected_as"] = mode
    result["key"] = secret_key
    return result


async def _perform(
    *,
    target_url: str,
    method: str,
    request_headers: dict[str, str],
    payload: bytes | None,
    content_type: str,
    timeout: httpx.Timeout,
    max_response_bytes: int,
) -> dict[str, Any]:
    """Run the request, following redirects with a fresh SSRF check on each hop.

    Returns the response verbatim. Redacting the secret out of it is the
    caller's job — this function never sees ``redact_forms``.
    """

    truncated = False
    collected = bytearray()
    response: httpx.Response | None = None

    async with httpx.AsyncClient(
        follow_redirects=False, timeout=timeout, verify=True
    ) as client:
        current_url = target_url
        current_method = method
        current_body = payload

        for _ in range(MAX_REDIRECTS + 1):
            parsed, addresses = validate_target(current_url)
            response = await _send_once(
                client,
                method=current_method,
                parsed=parsed,
                address=addresses[0],
                headers=request_headers,
                body=current_body,
                content_type=content_type,
                timeout=timeout,
            )

            if response.status_code not in _REDIRECT_CODES:
                break

            location = response.headers.get("location")
            code = response.status_code
            await response.aclose()
            response = None
            if not location:
                raise OutboundHttpError("Redirect without a Location header.")

            # Re-validated on every hop: the whole point of the guard is that a
            # public URL cannot 302 its way to an internal one.
            current_url = urljoin(current_url, location)
            validate_target(current_url)

            # 303 always becomes GET. 301/302 become GET for anything that is not
            # already safe. 307/308 preserve both method and body.
            if code == 303 or (code in (301, 302) and current_method not in ("GET", "HEAD")):
                current_method = "GET"
                current_body = None
        else:
            raise OutboundHttpError(f"Too many redirects (more than {MAX_REDIRECTS}).")

        if response is None:
            raise OutboundHttpError("The request did not produce a response.")

        status_code = response.status_code
        response_url = str(response.url)
        response_headers = {str(key): str(value) for key, value in response.headers.items()}
        encoding = response.encoding or "utf-8"

        async for chunk in response.aiter_bytes():
            collected.extend(chunk)
            if len(collected) > max_response_bytes:
                del collected[max_response_bytes:]
                truncated = True
                break
        await response.aclose()

    return {
        "status_code": status_code,
        "url": response_url,
        "headers": response_headers,
        "body": bytes(collected).decode(encoding, errors="replace"),
        "truncated": truncated,
    }
