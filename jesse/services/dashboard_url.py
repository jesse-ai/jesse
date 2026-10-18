"""
Public dashboard origin resolution.

Jesse deals with two different kinds of address:

- The bind address (``APP_HOST``/``APP_PORT``) decides where uvicorn listens. It may be a
  wildcard such as ``0.0.0.0`` and is also what Jesse's own MCP worker uses to reach the
  API on the same machine.
- The public dashboard origin (``DASHBOARD_URL``) is what people and MCP clients type or
  click. It differs from the bind address whenever Jesse runs on another machine, inside
  Docker, or behind a reverse proxy.

Links Jesse prints or returns (dashboard session pages and the advertised MCP endpoint)
are built only from the public origin, and internal requests never use it. Only a bare
origin is accepted because the bundled dashboard loads its assets, API and WebSocket from
absolute root paths, so it cannot be served under a path prefix.
"""

import ipaddress
import re
from typing import Mapping, Optional
from urllib.parse import quote, urlsplit

DASHBOARD_URL_ENV_KEY = 'DASHBOARD_URL'
MCP_ENDPOINT_PATH = '/mcp'
# Where `jesse run` listens when APP_HOST and APP_PORT are not set.
DEFAULT_APP_HOST = '0.0.0.0'
DEFAULT_APP_PORT = 9000

# One DNS label (RFC 1123). Underscores are tolerated because some LAN and container
# hostnames use them even though they are not strictly valid DNS names.
_HOSTNAME_LABEL = re.compile(r'^[a-z0-9_](?:[a-z0-9_-]{0,61}[a-z0-9_])?$')

# A complete URL authority without userinfo: a bracketed IPv6 literal or a plain host,
# optionally followed by ":" and a port of 1-5 digits with no leading zero. Anything else
# (an empty port, text after "]", stray brackets or colons) is malformed.
_AUTHORITY = re.compile(r'^(?:\[(?P<ipv6>[^\[\]]+)\]|(?P<host>[^\[\]:]+))(?::(?P<port>[1-9][0-9]{0,4}))?$')


class InvalidDashboardUrlError(ValueError):
    """Raised when DASHBOARD_URL cannot be used as the public dashboard origin."""


def is_unspecified_host(host: Optional[str]) -> bool:
    """Return True for an empty host or a wildcard bind address such as 0.0.0.0 or ::."""
    host = (host or '').strip().strip('[]')
    if not host:
        return True
    try:
        return ipaddress.ip_address(host).is_unspecified
    except ValueError:
        return False


def format_url_host(host: str) -> str:
    """Bracket IPv6 literals so they can be embedded in a URL authority."""
    host = host.strip()
    if ':' in host and not host.startswith('['):
        return f'[{host}]'
    return host


def internal_api_url(bind_host: Optional[str], port: int) -> str:
    """
    Return the URL Jesse's MCP worker uses to reach the API on this machine.

    A wildcard bind address is not a routable destination (notably on Windows), so it is
    translated to the loopback address of the same IP family; a concrete bind address is
    used directly. This never involves DASHBOARD_URL, which may point at a proxy or a
    hostname that does not resolve from the Jesse host itself.
    """
    host = (bind_host or '').strip().strip('[]')
    if is_unspecified_host(host):
        host = '::1' if host and ipaddress.ip_address(host).version == 6 else '127.0.0.1'
    return f'http://{format_url_host(host)}:{int(port)}'


def default_dashboard_url(bind_host: Optional[str], port: int) -> str:
    """Return the dashboard origin used when DASHBOARD_URL is not set."""
    host = 'localhost' if is_unspecified_host(bind_host) else (bind_host or '').strip().strip('[]')
    return f'http://{format_url_host(host)}:{int(port)}'


def _validate_hostname(host: str, value: str) -> None:
    """Reject hostnames that browsers and MCP clients could not resolve as written."""
    labels = host.split('.')
    # All-numeric names that failed IPv4 parsing (e.g. 192.168.1.020) are interpreted
    # inconsistently by browsers, so they are rejected rather than treated as host names.
    if all(label.isdigit() for label in labels) or any(not _HOSTNAME_LABEL.match(label) for label in labels):
        raise InvalidDashboardUrlError(
            f'DASHBOARD_URL has an invalid host name: {value!r}. Use a DNS name, an IPv4 '
            'address, or a bracketed IPv6 address such as http://[fd00::10]:9000.'
        )


def normalize_dashboard_url(value: str) -> str:
    """
    Validate a DASHBOARD_URL value and return it as a canonical origin.

    The result is ``scheme://host[:port]`` with a lower-case scheme and host, bracketed
    IPv6 literals, and no trailing slash. A trailing ``/`` in the input is accepted; any
    other path, a query, a fragment, credentials, or a wildcard host is rejected because
    the links built from it would not work.
    """
    value = value.strip()
    if not value:
        raise InvalidDashboardUrlError('DASHBOARD_URL is empty.')
    # Checked before anything else because later error messages quote the value, and a
    # URL with userinfo may carry a password that must never reach the terminal or logs.
    if '@' in value:
        raise InvalidDashboardUrlError('DASHBOARD_URL must not contain a username or password.')
    if any(char.isspace() or ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        raise InvalidDashboardUrlError('DASHBOARD_URL must not contain whitespace or control characters.')
    if not value.isascii():
        raise InvalidDashboardUrlError(
            'DASHBOARD_URL must be ASCII. Write internationalized host names in their '
            'punycode (xn--) form.'
        )
    if '\\' in value:
        raise InvalidDashboardUrlError('DASHBOARD_URL must not contain backslashes.')
    if '?' in value or '#' in value:
        raise InvalidDashboardUrlError(
            'DASHBOARD_URL must not contain a query or fragment. Jesse adds the dashboard '
            'page (#/...) and the /mcp path itself.'
        )

    try:
        parts = urlsplit(value)
    except ValueError as e:
        raise InvalidDashboardUrlError(f'DASHBOARD_URL is not a valid URL ({e}): {value!r}') from None

    scheme = parts.scheme.lower()
    if scheme not in ('http', 'https'):
        raise InvalidDashboardUrlError(
            f'DASHBOARD_URL must start with http:// or https://, for example '
            f'http://192.168.1.20:9000. Got {value!r}.'
        )
    if not parts.netloc:
        raise InvalidDashboardUrlError(f'DASHBOARD_URL has no host: {value!r}.')

    # urlsplit tolerates malformed authorities, depending on the Python version (e.g.
    # "[::1]garbage", or an empty port in "host:" that it silently drops). Matching the
    # whole authority ensures the advertised origin is exactly the one that was written.
    authority = _AUTHORITY.match(parts.netloc)
    if not authority:
        raise InvalidDashboardUrlError(
            f'DASHBOARD_URL has a malformed host or port: {value!r}. Use host or host:port '
            'with a port from 1 to 65535 written without leading zeros, and brackets around '
            'IPv6 addresses.'
        )
    port = int(authority.group('port')) if authority.group('port') else None
    if port is not None and port > 65535:
        raise InvalidDashboardUrlError(f'DASHBOARD_URL has a port above 65535: {value!r}.')

    if parts.path not in ('', '/'):
        raise InvalidDashboardUrlError(
            f'DASHBOARD_URL must be an origin without a path (got path {parts.path!r}). The '
            'dashboard loads its assets, API and WebSocket from the root of its origin, so '
            'serve Jesse at the root of a (sub)domain or port instead of under a path prefix.'
        )

    ipv6_host = authority.group('ipv6')
    host = (ipv6_host if ipv6_host is not None else authority.group('host')).lower()
    if ipv6_host is not None:
        # Enforce a real IPv6 address. Zone identifiers (fe80::1%25en0) parse as valid
        # but browsers reject them in URLs.
        try:
            if '%' in host:
                raise ValueError(host)
            ipaddress.IPv6Address(host)
        except ValueError:
            raise InvalidDashboardUrlError(
                f'DASHBOARD_URL has an invalid IPv6 address: {value!r}.'
            ) from None
    else:
        try:
            ipaddress.IPv4Address(host)
        except ValueError:
            _validate_hostname(host, value)

    if is_unspecified_host(host):
        raise InvalidDashboardUrlError(
            f'DASHBOARD_URL must be an address clients can connect to, not the wildcard bind '
            f'address {host!r}. Use this machine\'s LAN IP address or host name instead.'
        )

    netloc = format_url_host(host) + (f':{port}' if port is not None else '')
    return f'{scheme}://{netloc}'


def resolve_dashboard_url(env_values: Mapping[str, Optional[str]], bind_host: Optional[str], port: int) -> str:
    """
    Return the public dashboard origin: DASHBOARD_URL when set, otherwise the default.

    An unset, valueless, or blank DASHBOARD_URL falls back to advertising
    ``http://localhost:<APP_PORT>`` (or the concrete APP_HOST when Jesse is bound to a
    single address).
    """
    raw = env_values.get(DASHBOARD_URL_ENV_KEY)
    if raw is None or not str(raw).strip():
        return default_dashboard_url(bind_host, port)
    return normalize_dashboard_url(str(raw))


def live_session_url(session_id: str, env_values: Mapping[str, Optional[str]]) -> str:
    """
    Return the dashboard page of a live or paper session, or '' when DASHBOARD_URL is invalid.

    Sessions run in a worker process that does not receive the server's resolved origin,
    so it is resolved again from the same .env values that `jesse run` used.
    """
    try:
        origin = resolve_dashboard_url(
            env_values,
            env_values.get('APP_HOST') or DEFAULT_APP_HOST,
            int(env_values.get('APP_PORT') or DEFAULT_APP_PORT),
        )
    except ValueError:
        # Covers InvalidDashboardUrlError and a non-numeric APP_PORT edited after startup.
        return ''
    # The dashboard uses hash routing; opening this page loads the session into a Live tab.
    return f"{origin}/#/live/{quote(str(session_id), safe='')}"


def mcp_endpoint_url(dashboard_url: str) -> str:
    """Return the MCP endpoint advertised to clients: /mcp on the dashboard origin."""
    return f'{dashboard_url}{MCP_ENDPOINT_PATH}'
