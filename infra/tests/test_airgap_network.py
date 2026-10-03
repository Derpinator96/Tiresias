"""Run inside the ai container in air-gapped mode (make test-airgap). Proves ai reaches the
host's Ollama and nothing else outside: not the LLM API host, not the internet by IP, not
either Postgres (by name, and by the IPs from docker inspect that the Makefile passes in).

The Ollama check skips, with the reason, when nothing listens on llm.ollama.base_url; every
other check runs regardless, so the isolation is proven even before Ollama is installed.
"""
import os
import socket

import httpx
import pytest

from agent import llm
from common.config import cfg

TIMEOUT_S = 3.0


def _connect(host: str, port: int) -> None:
    with socket.create_connection((host, port), timeout=TIMEOUT_S):
        pass


def test_ai_is_in_airgap_mode():
    assert llm.provider_name() == "ollama", "ai is not in air-gapped mode: run make airgap"


@pytest.mark.parametrize("host,port", [(llm.GEMINI_HOST, 443), (llm.nim_host(), 443), (llm.openai_host(), 443), ("1.1.1.1", 443), ("8.8.8.8", 53)])
def test_no_internet(host, port):
    with pytest.raises(OSError):
        _connect(host, port)


@pytest.mark.parametrize("host", ["pg-prod", "pg-twin"])
def test_postgres_name_is_unreachable(host):
    with pytest.raises(OSError):
        _connect(host, 5432)


@pytest.mark.parametrize("env", ["PG_PROD_IP", "PG_TWIN_IP"])
def test_postgres_ip_is_unreachable(env):
    ip = os.environ.get(env)
    assert ip, f"{env} not set; run this through make test-airgap"
    with pytest.raises(OSError):
        _connect(ip, 5432)


def test_gateway_is_reachable():
    assert httpx.get(os.environ["GATEWAY_URL"] + "/healthz", timeout=TIMEOUT_S).status_code == 200


def test_ollama_is_reachable():
    url = cfg("llm.ollama.base_url")
    try:
        r = httpx.get(url + "/api/version", timeout=TIMEOUT_S)
    except httpx.TransportError as e:
        pytest.skip(f"Ollama is not reachable at {url} ({type(e).__name__}); see README.md, air-gapped mode")
    assert r.status_code == 200
    print(f"Ollama at {url}, version {r.json()['version']}")
