"""Diagnostics support for Owlet.

Built as an allowlist: only fields known to be harmless are included, so a
property Owlet adds tomorrow can never leak a token, an email address, a
serial number, a MAC address or the baby's details into a diagnostics
download.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import REDACTED
from homeassistant.const import CONF_REGION
from homeassistant.core import HomeAssistant

from . import OwletConfigEntry

# Raw Ayla properties whose value is included. Every other property is listed
# by name with its type and timestamp only: file properties carry URLs with
# device ids, CONFIG_STATUS carries MAC addresses, and the Smart Sock 2
# profile properties carry the baby's name, birth date and location.
VALUE_ALLOWED = frozenset(
    {
        "APP_ACTIVE",
        "REAL_TIME_VITALS",
        "HIGH_HR_ALRT",
        "LOW_HR_ALRT",
        "HIGH_OX_ALRT",
        "LOW_OX_ALRT",
        "CRIT_OX_ALRT",
        "LOW_BATT_ALRT",
        "CRIT_BATT_ALRT",
        "LOST_POWER_ALRT",
        "SOCK_DISCON_ALRT",
        "SOCK_OFF",
        "DISCOMFORT_ALRT",
        "LOW_INTEG_READ",
        "PREVIEW_HIGH_PRIORITY_ALARM",
        "PREVIEW_MED_PRIORITY_ALARM",
        "PREVIEW_LOW_PRIORITY_ALARM",
        "PREVIEW_DRM_PRIORITY_ALARM",
        "BASE_MON_STATUS",
        "BATTERY_STATUS",
        "DEVICE_PING",
        "FW_UPDATE_STATUS",
        "oem_sock_version",
        "oem_base_version",
        "oem_flash_version",
        # Smart Sock 2
        "HEART_RATE",
        "OXYGEN_LEVEL",
        "BATT_LEVEL",
        "MOVEMENT",
        "CHARGE_STATUS",
        "BLE_RSSI",
        "BASE_STATION_ON",
        "SOCK_CONNECTION",
        "SOCK_REC_PLACED",
        "ALRTS_DISABLED",
        "LOW_PA_ALRT",
        "NURSERY_MODE",
        "OTA_STATUS",
        "OTA_ERROR",
    }
)

# Metadata fields of a raw property that are always included.
PROPERTY_FIELDS = ("base_type", "direction", "data_updated_at")


def _describe_property(name: str, prop: Any) -> dict[str, Any]:
    """Return the allowed fields of a raw Ayla property."""
    if not isinstance(prop, dict):
        return {"value": REDACTED}
    described = {field: prop.get(field) for field in PROPERTY_FIELDS if field in prop}
    described["value"] = prop.get("value") if name in VALUE_ALLOWED else REDACTED
    return described


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: OwletConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    socks = []
    for index, coordinator in enumerate(entry.runtime_data.values()):
        sock = coordinator.sock
        last_updated = coordinator.last_updated
        socks.append(
            {
                "index": index,
                "version": getattr(sock, "version", None),
                "revision": getattr(sock, "revision", None),
                "model": getattr(sock, "model", None),
                "oem_model": getattr(sock, "oem_model", None),
                "sw_version": getattr(sock, "sw_version", None),
                "connection_status": getattr(sock, "connection_status", None),
                "last_update_success": coordinator.last_update_success,
                "last_updated": last_updated.isoformat() if last_updated else None,
                "vitals_fresh": coordinator.vitals_fresh,
                "stale_reason": coordinator.stale_reason,
                "readings_expected": coordinator.readings_expected,
                "is_stale": coordinator.is_stale,
                "properties": dict(sock.properties),
                "raw_properties": {
                    name: _describe_property(name, prop)
                    for name, prop in (sock.raw_properties or {}).items()
                },
            }
        )

    return {
        "entry": {
            "version": entry.version,
            "data": {CONF_REGION: entry.data.get(CONF_REGION)},
            "options": dict(entry.options),
        },
        "socks": socks,
    }
