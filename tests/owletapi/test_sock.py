"""Tests for the Sock model."""

from __future__ import annotations

import datetime

import pytest

from custom_components.owlet.owletapi.api import OwletAPI
from custom_components.owlet.owletapi.sock import Sock

from .conftest import BASE, DSN, FakeSession, load

PROPERTIES_URL = f"{BASE}/dsns/{DSN}/properties.json"
ACTIVATE_URL = f"{BASE}/dsns/{DSN}/properties/APP_ACTIVE/datapoints.json"


@pytest.fixture
def sock(authed_api: OwletAPI) -> Sock:
    return Sock(authed_api, {"dsn": DSN, "product_name": "Owlet Baby Monitors"})


async def test_v3_properties(mock_api: FakeSession, sock: Sock) -> None:
    mock_api.post(ACTIVATE_URL, payload={})
    mock_api.get(PROPERTIES_URL, payload=load("properties_v3.json"))

    await sock.update_properties()

    assert sock.version == 3
    assert sock.properties["heart_rate"] == 97.0
    assert sock.properties["oxygen_saturation"] == 99.0
    assert sock.properties["sleep_state"] == 8
    assert sock.last_updated_at == datetime.datetime(
        2023, 5, 24, 14, 15, 50, tzinfo=datetime.UTC
    )


async def test_v2_properties(mock_api: FakeSession, sock: Sock) -> None:
    mock_api.post(ACTIVATE_URL, payload={})
    mock_api.get(PROPERTIES_URL, payload=load("properties_v2.json"))

    await sock.update_properties()

    assert sock.version == 2
    assert sock.properties["heart_rate"] == 145
    # Newest vital timestamp in the fixture is HEART_RATE / MOVEMENT at 14:05:01.
    assert sock.last_updated_at == datetime.datetime(
        2023, 11, 20, 14, 5, 1, tzinfo=datetime.UTC
    )


def test_last_updated_without_data(sock: Sock) -> None:
    assert sock.last_updated_at is None


def test_sock_has_no_control_methods(sock: Sock) -> None:
    """The sock model is read-only, there is nothing that could change the base station."""
    assert not hasattr(sock, "control_base_station")
    assert not hasattr(sock.api, "post_command")
