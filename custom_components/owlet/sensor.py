"""Support for Owlet sensors."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from . import OwletConfigEntry
from .const import SLEEP_STATES
from .coordinator import OwletCoordinator
from .entity import OwletBaseEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class OwletSensorEntityDescription(SensorEntityDescription):
    """Represent the owlet sensor entity description."""

    available_during_charging: bool


SENSORS: tuple[OwletSensorEntityDescription, ...] = (
    OwletSensorEntityDescription(
        key="battery_percentage",
        translation_key="batterypercent",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        available_during_charging=True,
    ),
    OwletSensorEntityDescription(
        key="oxygen_saturation",
        translation_key="o2saturation",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        available_during_charging=False,
    ),
    OwletSensorEntityDescription(
        key="heart_rate",
        translation_key="heartrate",
        native_unit_of_measurement="bpm",
        state_class=SensorStateClass.MEASUREMENT,
        available_during_charging=False,
    ),
    OwletSensorEntityDescription(
        key="battery_minutes",
        translation_key="batterymin",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        available_during_charging=False,
    ),
    OwletSensorEntityDescription(
        key="signal_strength",
        translation_key="signalstrength",
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        available_during_charging=True,
    ),
    OwletSensorEntityDescription(
        key="skin_temperature",
        translation_key="skintemp",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        available_during_charging=False,
    ),
    OwletSensorEntityDescription(
        key="movement",
        translation_key="movement",
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        available_during_charging=False,
    ),
    OwletSensorEntityDescription(
        key="movement_bucket",
        translation_key="movementbucket",
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        available_during_charging=False,
    ),
    # Raw status codes from the device, useful when checking what the sock
    # reports during an alert. Their meaning is not documented by Owlet.
    OwletSensorEntityDescription(
        key="alerts_mask",
        translation_key="alerts_mask",
        entity_category=EntityCategory.DIAGNOSTIC,
        available_during_charging=True,
    ),
    OwletSensorEntityDescription(
        key="base_monitoring_status",
        translation_key="base_mon_status",
        entity_category=EntityCategory.DIAGNOSTIC,
        available_during_charging=True,
    ),
    OwletSensorEntityDescription(
        key="battery_status",
        translation_key="battery_status",
        entity_category=EntityCategory.DIAGNOSTIC,
        available_during_charging=True,
    ),
)

RED_ALERT_SUMMARY = "RED_ALERT_SUMMARY"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: OwletConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the owlet sensors from config entry."""
    sensors: list[SensorEntity] = []

    for coordinator in config_entry.runtime_data.values():
        properties = coordinator.sock.properties
        sensors.extend(
            OwletSensor(coordinator, description)
            for description in SENSORS
            if description.key in properties
        )
        if OwletSleepSensor.entity_description.key in properties:
            sensors.append(OwletSleepSensor(coordinator))
        if OwletOxygenAverageSensor.entity_description.key in properties:
            sensors.append(OwletOxygenAverageSensor(coordinator))
        sensors.append(OwletLastUpdatedSensor(coordinator))
        if RED_ALERT_SUMMARY in (coordinator.sock.raw_properties or {}):
            sensors.append(OwletLastRedAlertSensor(coordinator))

    async_add_entities(sensors)


class OwletSensor(OwletBaseEntity, SensorEntity):
    """Representation of an Owlet sensor."""

    def __init__(
        self,
        coordinator: OwletCoordinator,
        description: OwletSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description: OwletSensorEntityDescription = description
        self._attr_unique_id = f"{self.sock.serial}-{description.key}"

    @property
    def available(self) -> bool:
        """Return if entity is available.

        Nothing from a reading that is not fresh is shown, so a frozen value
        is never mistaken for a live one. Vitals are hidden while charging too.
        """
        return super().available and self.coordinator.reading_available(
            self.entity_description.key,
            self.entity_description.available_during_charging,
        )

    @property
    def native_value(self) -> StateType:
        """Return sensor value."""
        return self.sock.properties.get(self.entity_description.key)


class OwletSleepSensor(OwletSensor):
    """Representation of an Owlet sleep sensor."""

    _attr_options = list(SLEEP_STATES.values())
    entity_description = OwletSensorEntityDescription(
        key="sleep_state",
        translation_key="sleepstate",
        device_class=SensorDeviceClass.ENUM,
        available_during_charging=False,
    )

    def __init__(
        self,
        coordinator: OwletCoordinator,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, self.entity_description)

    @property
    def native_value(self) -> StateType:
        """Return sensor value."""
        return SLEEP_STATES.get(self.sock.properties.get("sleep_state"), "unknown")


class OwletOxygenAverageSensor(OwletSensor):
    """Representation of the Owlet 10 minute oxygen average sensor."""

    entity_description = OwletSensorEntityDescription(
        key="oxygen_10_av",
        translation_key="o2saturation10a",
        native_unit_of_measurement=PERCENTAGE,
        available_during_charging=False,
        state_class=SensorStateClass.MEASUREMENT,
    )

    def __init__(
        self,
        coordinator: OwletCoordinator,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, self.entity_description)

    @property
    def available(self) -> bool:
        """Return if entity is available.

        The sock reports 255 until it has ten minutes of data.
        """
        value = self.sock.properties.get("oxygen_10_av")
        return super().available and value is not None and 0 <= value <= 100


class OwletLastUpdatedSensor(OwletBaseEntity, SensorEntity):
    """When the Owlet cloud last received a reading from the sock."""

    entity_description = SensorEntityDescription(
        key="last_updated",
        translation_key="last_updated",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
    )

    def __init__(self, coordinator: OwletCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{self.sock.serial}-last_updated"

    @property
    def native_value(self) -> datetime | None:
        """Return the timestamp of the latest reading."""
        return self.coordinator.last_updated


class OwletLastRedAlertSensor(OwletBaseEntity, SensorEntity):
    """When the sock last recorded a red alert.

    The RED_ALERT_SUMMARY property holds an opaque summary of red alerts; the
    moment the cloud last received a new one is the useful part.
    """

    entity_description = SensorEntityDescription(
        key="last_red_alert",
        translation_key="last_red_alert",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
    )

    def __init__(self, coordinator: OwletCoordinator) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{self.sock.serial}-last_red_alert"

    @property
    def native_value(self) -> datetime | None:
        """Return when the red alert summary was last updated."""
        return self.coordinator.property_updated_at(RED_ALERT_SUMMARY)
