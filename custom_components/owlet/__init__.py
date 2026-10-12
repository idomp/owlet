"""The Owlet Smart Sock integration.

Originally created by Ryan Clark (https://github.com/ryanbdclark/owlet),
continued by Lucas Vollebergh (https://github.com/lucasvollebergh/owlet), now
maintained at https://github.com/idomp/owlet.

This fork is read-only towards the Owlet cloud: the only property it ever
writes is APP_ACTIVE, which tells the base station that a client is watching.
"""

from __future__ import annotations

import asyncio
import logging

from aiohttp import ClientError

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_API_TOKEN,
    CONF_REGION,
    CONF_USERNAME,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er, issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_OWLET_EXPIRY,
    CONF_OWLET_REFRESH,
    DOMAIN,
    OWLET_CREDENTIAL_ERRORS,
    SUPPORTED_VERSIONS,
)
from .coordinator import OwletCoordinator
from .owletapi.api import OwletAPI
from .owletapi.exceptions import OwletConnectionError, OwletDevicesError, OwletError
from .owletapi.sock import Sock

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]

_LOGGER = logging.getLogger(__name__)

type OwletConfigEntry = ConfigEntry[dict[str, OwletCoordinator]]


async def async_setup_entry(hass: HomeAssistant, entry: OwletConfigEntry) -> bool:
    """Set up Owlet Smart Sock from a config entry."""
    owlet_api = OwletAPI(
        region=entry.data[CONF_REGION],
        token=entry.data[CONF_API_TOKEN],
        expiry=entry.data[CONF_OWLET_EXPIRY],
        refresh=entry.data[CONF_OWLET_REFRESH],
        session=async_get_clientsession(hass),
    )

    try:
        await owlet_api.authenticate()
        devices = await owlet_api.get_devices(SUPPORTED_VERSIONS)
    except OWLET_CREDENTIAL_ERRORS as err:
        raise ConfigEntryAuthFailed(
            f"Credentials expired for {entry.data[CONF_USERNAME]}"
        ) from err
    except OwletDevicesError as err:
        raise ConfigEntryNotReady(
            "No supported Owlet socks found on this account"
        ) from err
    except (OwletConnectionError, OwletError, ClientError, TimeoutError) as err:
        raise ConfigEntryNotReady(
            f"Error connecting to Owlet for {entry.data[CONF_USERNAME]}"
        ) from err

    _async_store_tokens(hass, entry, owlet_api)

    coordinators = {
        device["device"]["dsn"]: OwletCoordinator(
            hass, entry, Sock(owlet_api, device["device"])
        )
        for device in devices["response"]
    }

    await asyncio.gather(
        *(
            coordinator.async_config_entry_first_refresh()
            for coordinator in coordinators.values()
        )
    )

    entry.runtime_data = coordinators

    _async_remove_switch_entities(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


def _async_remove_switch_entities(hass: HomeAssistant, entry: OwletConfigEntry) -> None:
    """Remove the base station switch left behind by earlier releases.

    This fork never switches the base station on or off, the state is exposed
    as a binary sensor instead, so a leftover switch would stay unavailable
    forever.
    """
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity.domain == Platform.SWITCH:
            _LOGGER.info("Removing base station switch %s", entity.entity_id)
            registry.async_remove(entity.entity_id)


async def async_unload_entry(hass: HomeAssistant, entry: OwletConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        for coordinator in entry.runtime_data.values():
            ir.async_delete_issue(hass, DOMAIN, coordinator.stale_issue_id)
    return unload_ok


def _async_store_tokens(
    hass: HomeAssistant, entry: OwletConfigEntry, owlet_api: OwletAPI
) -> None:
    """Persist refreshed tokens so a restart does not need a new login."""
    tokens = {key: value for key, value in owlet_api.tokens.items() if value}
    if any(entry.data.get(key) != value for key, value in tokens.items()):
        hass.config_entries.async_update_entry(entry, data={**entry.data, **tokens})
