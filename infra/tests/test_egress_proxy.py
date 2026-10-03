"""Egress proxy unit tests (no network beyond 127.0.0.1). Run in the tools container:

    docker compose ... run --rm -T tools python -m pytest infra/tests/test_egress_proxy.py

The live allow and deny checks from inside ai are in test_isolation.py (make test-infra).
"""
import asyncio
from urllib.parse import urlsplit

import pytest
import yaml

from common.config import REPO_ROOT, cfg
from infra import egress_proxy as ep

HOSTS, PORTS = ["api.example.test"], [443]


@pytest.mark.parametrize("head,expected", [
    (b"CONNECT api.example.test:443 HTTP/1.1\r\n\r\n", (200, "api.example.test", 443)),
    (b"CONNECT API.Example.Test.:443 HTTP/1.1\r\n\r\n", (200, "api.example.test", 443)),  # case, trailing dot
    (b"CONNECT other.example.test:443 HTTP/1.1\r\n\r\n", (403, "other.example.test", 443)),
    (b"CONNECT api.example.test.evil.test:443 HTTP/1.1\r\n\r\n", (403, "api.example.test.evil.test", 443)),
    (b"CONNECT api.example.test:80 HTTP/1.1\r\n\r\n", (403, "api.example.test", 80)),
    (b"CONNECT [::1]:443 HTTP/1.1\r\n\r\n", (403, "[::1]", 443)),
    (b"GET http://api.example.test/ HTTP/1.1\r\n\r\n", (405, "", 0)),
    (b"CONNECT api.example.test HTTP/1.1\r\n\r\n", (400, "", 0)),
    (b"CONNECT api.example.test:x HTTP/1.1\r\n\r\n", (400, "", 0)),
    (b"\xff\xfe\r\n\r\n", (400, "", 0)),
])
def test_decide_allows_only_listed_host_and_port(head, expected):
    assert ep.decide(head, HOSTS, PORTS) == expected


def test_tunnel_relays_bytes_and_denies_other_ports(monkeypatch):
    conf = {"egress.allowed_hosts": ["127.0.0.1"], "egress.allowed_ports": [], "egress.connect_timeout_s": 3}
    monkeypatch.setattr(ep, "cfg", conf.__getitem__)

    async def echo(r, w):
        w.write(await r.read(4))
        await w.drain()
        w.close()

    async def main():
        upstream = await asyncio.start_server(echo, "127.0.0.1", 0)
        uport = upstream.sockets[0].getsockname()[1]
        conf["egress.allowed_ports"] = [uport]
        proxy = await asyncio.start_server(ep.handle, "127.0.0.1", 0)
        pport = proxy.sockets[0].getsockname()[1]

        r, w = await asyncio.open_connection("127.0.0.1", pport)
        w.write(f"CONNECT 127.0.0.1:{uport} HTTP/1.1\r\n\r\n".encode())
        assert (await r.readuntil(b"\r\n\r\n")).startswith(b"HTTP/1.1 200 ")
        w.write(b"ping")
        await w.drain()
        assert await r.readexactly(4) == b"ping"
        w.close()

        r, w = await asyncio.open_connection("127.0.0.1", pport)
        w.write(f"CONNECT 127.0.0.1:{uport + 1} HTTP/1.1\r\n\r\n".encode())
        assert (await r.read()).startswith(b"HTTP/1.1 403 ")
        w.close()
        proxy.close()
        upstream.close()

    asyncio.run(main())


def test_allowlist_is_the_llm_host():
    # Exactly the hosted LLM APIs (Gemini; NVIDIA NIM and OpenAI, added 2026-10-03 at the
    # human's request), nothing else.
    from agent import llm
    urls = [urlsplit(llm.GEMINI_URL), urlsplit(cfg("llm.nim.base_url")), urlsplit(cfg("llm.openai.base_url"))]
    assert sorted(cfg("egress.allowed_hosts")) == sorted(u.hostname for u in urls)
    for u in urls:
        assert (u.port or 443) in cfg("egress.allowed_ports")


def test_only_the_proxy_reaches_the_internet_and_only_ai_reaches_the_proxy():
    compose = yaml.safe_load((REPO_ROOT / "infra" / "docker-compose.yml").read_text(encoding="utf-8"))
    nets = {name: set(svc.get("networks", [])) for name, svc in compose["services"].items()}
    internet = {n for n, spec in compose["networks"].items() if not (spec or {}).get("internal")}
    # dashboard and web: the 127.0.0.1-bound operator network (SIMPLIFIED, see the compose header).
    # web added with human approval 2026-10-04 (site/web live Ask page).
    assert {s for s, n in nets.items() if n & internet} == {"egress-proxy", "dashboard", "web"}
    assert nets["dashboard"] & internet == {"operator"}
    assert nets["web"] & internet == {"operator"}
    assert "private" not in nets["web"]
    assert {s for s, n in nets.items() if "ai-proxy" in n} == {"ai", "egress-proxy"}
    assert compose["networks"]["ai-proxy"]["internal"] is True
    proxy = urlsplit(compose["services"]["ai"]["environment"]["HTTPS_PROXY"])
    assert (proxy.hostname, str(proxy.port)) == ("egress-proxy", compose["services"]["egress-proxy"]["command"][-1])


def test_published_ports_bind_loopback_only():
    compose = yaml.safe_load((REPO_ROOT / "infra" / "docker-compose.yml").read_text(encoding="utf-8"))
    published = {name: svc["ports"] for name, svc in compose["services"].items() if svc.get("ports")}
    assert set(published) == {"dashboard", "web"}
    for name, ports in published.items():
        for p in ports:
            assert str(p).startswith("127.0.0.1:"), (name, p)


def test_dashboard_label_matches_the_proxy():
    from dashboard import data
    assert data.LABELS["egress"] == ep.LABEL
