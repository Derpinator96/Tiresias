"""Run inside the `gateway` and `tools` containers. Both touch raw data, so they must have no
internet route: they sit only on the internal `private` and `boundary` networks, and cannot
reach ai's egress proxy either."""
import socket

import pytest


def test_gateway_cannot_reach_the_internet():
    with pytest.raises(OSError):
        with socket.create_connection(("generativelanguage.googleapis.com", 443), timeout=3.0):
            pass


def test_egress_proxy_is_out_of_reach():
    # Only ai shares a network with the proxy, so the private side cannot borrow its route.
    with pytest.raises(OSError):
        with socket.create_connection(("egress-proxy", 3128), timeout=3.0):
            pass


def test_gateway_reaches_both_postgres():
    for host in ("pg-prod", "pg-twin"):
        with socket.create_connection((host, 5432), timeout=3.0):
            pass
