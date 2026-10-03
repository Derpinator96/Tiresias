"""Run inside the `ai` container. Proves the AI side cannot reach either Postgres.

PG_PROD_IP and PG_TWIN_IP are passed in by infra/tests/run.sh (read from `docker inspect`
on the host), so the test also covers connecting by IP, not just by name. If they are
missing the test fails rather than skips: an untested boundary is not a proven one.
"""
import os
import socket

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


def test_llm_api_host_is_reachable():
    # SIMPLIFIED egress (decision D): ai has unrestricted internet, so this passes for any
    # host. It shows the LLM route exists, not that other hosts are blocked.
    _connect("generativelanguage.googleapis.com", 443)
