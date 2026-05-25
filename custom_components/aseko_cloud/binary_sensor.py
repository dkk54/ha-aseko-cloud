"""Binary sensor platform for the Aseko Cloud integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import AsekoCloudConfigEntry
from .api import AsekoUnit
from .coordinator import AsekoCloudCoordinator
from .entity import AsekoCloudEntity


@dataclass(frozen=True, kw_only=True)
class AsekoBinarySensorDescription(BinarySensorEntityDescription):
    """Describes an Aseko Cloud binary sensor."""

    value_fn: Callable[[AsekoUnit], bool | None]
    exists_fn: Callable[[AsekoUnit], bool] = lambda unit: True
    attributes_fn: Callable[[AsekoUnit], dict[str, Any] | None] | None = None


def _status_value(field: str) -> Callable[[AsekoUnit], bool | None]:
    """Return a value_fn that pulls a boolean out of ``statusValues``."""
    return lambda unit: unit.status_values.get(field)


def _has_status_value(field: str) -> Callable[[AsekoUnit], bool]:
    """Return an exists_fn that checks for a field in ``statusValues``."""
    return lambda unit: field in unit.status_values


def _alarm_attributes(unit: AsekoUnit) -> dict[str, Any] | None:
    """Expose the active status messages as attributes of the problem sensor."""
    if not unit.status_messages:
        return None
    return {
        "messages": [
            {
                "type": m.get("type"),
                "severity": m.get("severity"),
                "message": m.get("message"),
            }
            for m in unit.status_messages
        ]
    }


BINARY_SENSORS: tuple[AsekoBinarySensorDescription, ...] = (
    AsekoBinarySensorDescription(
        key="online",
        translation_key="online",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda unit: unit.online,
    ),
    AsekoBinarySensorDescription(
        key="problem",
        translation_key="problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda unit: unit.has_error,
        attributes_fn=_alarm_attributes,
    ),
    AsekoBinarySensorDescription(
        key="filtration",
        translation_key="filtration",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=_status_value("filtrationRunning"),
        exists_fn=_has_status_value("filtrationRunning"),
    ),
    AsekoBinarySensorDescription(
        key="heating",
        translation_key="heating",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=_status_value("heatingRunning"),
        exists_fn=_has_status_value("heatingRunning"),
    ),
    AsekoBinarySensorDescription(
        key="solar",
        translation_key="solar",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=_status_value("solarRunning"),
        exists_fn=_has_status_value("solarRunning"),
    ),
    AsekoBinarySensorDescription(
        key="electrolyzer",
        translation_key="electrolyzer",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=_status_value("electrolyzerRunning"),
        exists_fn=_has_status_value("electrolyzerRunning"),
    ),
    AsekoBinarySensorDescription(
        key="water_filling",
        translation_key="water_filling",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=_status_value("waterFillingRunning"),
        exists_fn=_has_status_value("waterFillingRunning"),
    ),
    AsekoBinarySensorDescription(
        key="water_flow_to_probes",
        translation_key="water_flow_to_probes",
        value_fn=_status_value("waterFlowToProbes"),
        exists_fn=_has_status_value("waterFlowToProbes"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AsekoCloudConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Aseko Cloud binary sensors from a config entry."""
    coordinator = entry.runtime_data
    async_add_entities(
        AsekoCloudBinarySensor(coordinator, serial, description)
        for serial, unit in coordinator.data.items()
        for description in BINARY_SENSORS
        if description.exists_fn(unit)
    )


class AsekoCloudBinarySensor(AsekoCloudEntity, BinarySensorEntity):
    """A binary state read from an Aseko pool unit."""

    entity_description: AsekoBinarySensorDescription

    def __init__(
        self,
        coordinator: AsekoCloudCoordinator,
        serial_number: str,
        description: AsekoBinarySensorDescription,
    ) -> None:
        """Initialise the binary sensor."""
        super().__init__(coordinator, serial_number)
        self.entity_description = description
        self._attr_unique_id = f"{serial_number}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        """Return True when the binary sensor is active."""
        return self.entity_description.value_fn(self.unit)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra attributes, if the description provides any."""
        if self.entity_description.attributes_fn is None:
            return None
        return self.entity_description.attributes_fn(self.unit)
