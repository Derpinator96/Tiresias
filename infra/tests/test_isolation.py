"""Run inside the `ai` container. Proves the AI side cannot reach either Postgres, and reaches
the internet only through the egress proxy, only to the LLM API host.

PG_PROD_IP and PG_TWIN_IP are passed in by infra/tests/run.sh (read from `docker inspect`
on the host), so the test also covers connecting by IP, not just by name. If they are
missing the test fails rather than skips: an untested boundary is not a proven one.
"""
import os
import socket
from urllib.parse import urlsplit

import httpx
import pytest

TIMEOUT_S = 3.0


def _connect(host: str, port: int) -> None:
    with socket.create_connection((host, port), timeout=TIMEOUT_S):
        pass


@pytest.mark.parametrize("host", ["pg-prod", "pg-twin"])
def test_postgres_name_does_not_resolve_or_connect(host):
    with pytest.raises(OSError):
        _connect(host, 5432)


@pytest.mark.parametrize("env", ["PG_PROD_IP", "PG_TWIN_IP"])
def test_postgres_ip_is_unreachable(env):
    ip = os.environ.get(env)
    assert ip, f"{env} not set; run this through infra/tests/run.sh"
    with pytest.raises(OSError):
        _connect(ip, 5432)


def test_gateway_is_reachable():
    r = httpx.get(os.environ["GATEWAY_URL"] + "/healthz", timeout=TIMEOUT_S)
    assert r.status_code == 200


LLM_HOST = "generativelanguage.googleapis.com"


def _connect_via_proxy(target: str, method: str = "CONNECT") -> int:
    """Send one request line to the egress proxy (HTTPS_PROXY) and return its status code."""
    proxy = urlsplit(os.environ["HTTPS_PROXY"])
    with socket.create_connection((proxy.hostname, proxy.port), timeout=TIMEOUT_S) as s:
        s.sendall(f"{method} {target} HTTP/1.1\r\nHost: {target}\r\n\r\n".encode())
        return int(s.recv(1024).split(b" ", 2)[1])


def test_llm_api_host_is_reachable():
    # Through the egress proxy (ai has no direct internet route): the tunnel opens.
    assert _connect_via_proxy(f"{LLM_HOST}:443") == 200


@pytest.mark.parametrize("target,method,status", [
    ("example.com:443", "CONNECT", 403),          # host not on the allowlist
    (f"{LLM_HOST}:80", "CONNECT", 403),           # allowed host, port not on the allowlist
    ("1.1.1.1:443", "CONNECT", 403),              # an IP literal is not an allowed host
    ("http://example.com/", "GET", 405),          # plain forwarding is not offered
])
def test_non_allowlisted_host_is_blocked_by_the_proxy(target, method, status):
    assert _connect_via_proxy(target, method) == status


@pytest.mark.parametrize("host", [LLM_HOST, "example.com", "1.1.1.1"])
def test_no_direct_internet_route(host):
    # Not even the LLM host is reachable directly: the proxy is ai's only way out.
    with pytest.raises(OSError):
        _connect(host, 443)
