"""Test the Owlet binary sensors."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.owlet.const import DOMAIN
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .conftest import FRESH_TIME, load_json
from .helpers import SERIAL, setup_integration, state

pytestmark = pytest.mark.freeze_time(FRESH_TIME)

ALERTS = (
    "high_heart_rate_alert",
    "low_heart_rate_alert",
    "high_oxygen_alert",
    "low_oxygen_alert",
    "low_battery_alert",
    "lost_power_alert",
    "sock_disconnected",
)


def _state(hass: HomeAssistant, key: str) -> str:
    return state(hass, "binary_sensor", key).state


async def test_binary_sensors_asleep(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_owlet_api: dict[str, AsyncMock],
) -> None:
    """Test binary sensor values for a sleeping baby."""
    await setup_integration(hass, mock_config_entry)

    assert _state(hass, "charging") == STATE_OFF
    assert _state(hass, "base_station_on") == STATE_ON
    assert _state(hass, "sock_off") == STATE_OFF
    assert _state(hass, "sleep_state") == STATE_OFF
    assert _state(hass, "data_stale") == STATE_OFF
    for alert in ALERTS:
        assert _state(hass, alert) == STATE_OFF, alert


@pytest.mark.parametrize("properties_fixture", ["update_properties_awake.json"])
async def test_binary_sensors_awake(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_owlet_api: dict[str, AsyncMock],
) -> None:
    """Test binary sensor values when the vitals alerts are active."""
    await setup_integration(hass, mock_config_entry)

    assert _state(hass, "sleep_state") == STATE_ON
    for alert in ALERTS[:-1]:
        assert _state(hass, alert) == STATE_ON, alert
    assert _state(hass, "sock_disconnected") == STATE_OFF


@pytest.mark.parametrize("properties_fixture", ["update_properties_charging.json"])
async def test_binary_sensors_charging(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_owlet_api: dict[str, AsyncMock],
) -> None:
    """Test the awake sensor is unavailable while charging."""
    await setup_integration(hass, mock_config_entry)

    assert _state(hass, "charging") == STATE_ON
    assert _state(hass, "base_station_on") == STATE_OFF
    assert _state(hass, "sleep_state") == STATE_UNAVAILABLE


async def test_awake_is_unknown_without_sleep_state(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_owlet_api: dict[str, AsyncMock],
) -> None:
    """Sleep state 0 means the sock does not know, so awake is unknown, not on."""
    data = load_json("update_properties_asleep.json")
    vitals = json.loads(data["response"]["REAL_TIME_VITALS"]["value"])
    vitals["ss"] = 0
    data["response"]["REAL_TIME_VITALS"]["value"] = json.dumps(vitals)
    mock_owlet_api["get_properties"].side_effect = lambda *_: data

    await setup_integration(hass, mock_config_entry)

    assert _state(hass, "sleep_state") == STATE_UNKNOWN
    assert state(hass, "sensor", "sleep_state").state == "unknown"


async def test_no_switch_entities(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_owlet_api: dict[str, AsyncMock],
    entity_registry: er.EntityRegistry,
) -> None:
    """Nothing in Home Assistant can switch the base station: no switch exists."""
    await setup_integration(hass, mock_config_entry)

    assert hass.states.async_entity_ids("switch") == []
    assert not [
        entry
        for entry in er.async_entries_for_config_entry(
            entity_registry, mock_config_entry.entry_id
        )
        if entry.domain == "switch"
    ]


async def test_leftover_switch_is_removed(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_owlet_api: dict[str, AsyncMock],
    entity_registry: er.EntityRegistry,
) -> None:
    """A base station switch left by an earlier release is removed on setup."""
    mock_config_entry.add_to_hass(hass)
    unique_id = f"{SERIAL}-base_station_on"
    entity_registry.async_get_or_create(
        "switch", DOMAIN, unique_id, config_entry=mock_config_entry
    )
    assert entity_registry.async_get_entity_id("switch", DOMAIN, unique_id)

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert entity_registry.async_get_entity_id("switch", DOMAIN, unique_id) is None
    # The same unique id now lives on the read-only binary sensor.
    assert _state(hass, "base_station_on") == STATE_ON
