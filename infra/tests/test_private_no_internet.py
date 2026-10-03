"""Run inside the `gateway` container. The gateway touches raw data, so it must have no
internet route: it sits only on the internal `private` and `boundary` networks."""
import socket

import pytest


def test_gateway_cannot_reach_the_internet():
    with pytest.raises(OSError):
        with socket.create_connection(("generativelanguage.googleapis.com", 443), timeout=3.0):
            pass


def test_gateway_reaches_both_postgres():
    for host in ("pg-prod", "pg-twin"):
        with socket.create_connection((host, 5432), timeout=3.0):
            pass
