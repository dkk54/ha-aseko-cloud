"""Sensor platform for the Aseko Cloud integration.

One sensor is created per ``statusValues`` field a unit actually reports. The
integrator API returns clean, typed numbers, so no string parsing is needed.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfElectricPotential,
    UnitOfPressure,
    UnitOfTemperature,
    UnitOfVolumeFlowRate,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from . import AsekoCloudConfigEntry
from .api import AsekoUnit
from .const import LOGGER
from .coordinator import AsekoCloudCoordinator
from .entity import AsekoCloudEntity, async_add_unit_entities

# Read-only, coordinator-driven: no per-entity update calls to throttle.
PARALLEL_UPDATES = 0

_DIAGNOSTIC = EntityCategory.DIAGNOSTIC


@dataclass(frozen=True, kw_only=True)
class AsekoSensorDescription(SensorEntityDescription):
    """Describes a sensor backed by a ``statusValues`` field."""

    api_field: str
    # Key inside ``api_field`` when the field is an object, not a plain value.
    value_key: str | None = None
    # Field holding this sensor's unit string, when the API reports it.
    unit_field: str | None = None
    # True for enum sensors; the raw value is lower-cased to match ``options``.
    is_enum: bool = False


def _temperature(key: str, api_field: str, **kwargs: object) -> AsekoSensorDescription:
    """Build a temperature sensor description.

    ``state_class`` defaults to MEASUREMENT but the caller can pass
    ``state_class=None`` to opt out (e.g. for diagnostic setpoint sensors).
    """
    kwargs.setdefault("state_class", SensorStateClass.MEASUREMENT)
    return AsekoSensorDescription(
        key=key,
        translation_key=key,
        api_field=api_field,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        **kwargs,  # type: ignore[arg-type]
    )


def _enum(key: str, api_field: str, options: list[str]) -> AsekoSensorDescription:
    """Build an enum sensor description."""
    return AsekoSensorDescription(
        key=key,
        translation_key=key,
        api_field=api_field,
        is_enum=True,
        device_class=SensorDeviceClass.ENUM,
        options=options,
    )


def _filtration_period(key: str, value_key: str) -> AsekoSensorDescription:
    """Build a sensor for the start or end (``HH:MM``) of the filtration period.

    The period is the one currently running, or the next one when filtration
    is idle. Non-stop filtration has no start or end, so the value is unknown.
    """
    return AsekoSensorDescription(
        key=key,
        translation_key=key,
        api_field="upcomingFiltrationPeriod",
        value_key=value_key,
    )


SENSORS: tuple[AsekoSensorDescription, ...] = (
    _temperature("water_temperature", "waterTemperature"),
    _temperature("air_temperature", "airTemperature"),
    _temperature("solar_temperature", "solarTemperature"),
    _temperature(
        "water_temperature_required",
        "waterTemperatureRequired",
        state_class=None,
        entity_category=_DIAGNOSTIC,
    ),
    AsekoSensorDescription(
        key="ph",
        translation_key="ph",
        api_field="ph",
        device_class=SensorDeviceClass.PH,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    AsekoSensorDescription(
        key="ph_required",
        translation_key="ph_required",
        api_field="phRequired",
        device_class=SensorDeviceClass.PH,
        entity_category=_DIAGNOSTIC,
    ),
    AsekoSensorDescription(
        key="redox",
        translation_key="redox",
        api_field="redox",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.MILLIVOLT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    AsekoSensorDescription(
        key="redox_required",
        translation_key="redox_required",
        api_field="redoxRequired",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.MILLIVOLT,
        entity_category=_DIAGNOSTIC,
    ),
    AsekoSensorDescription(
        key="cl_free",
        translation_key="cl_free",
        api_field="clFree",
        native_unit_of_measurement="mg/L",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    AsekoSensorDescription(
        key="cl_bounded",
        translation_key="cl_bounded",
        api_field="clBounded",
        native_unit_of_measurement="mg/L",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    AsekoSensorDescription(
        key="cl_free_required",
        translation_key="cl_free_required",
        api_field="clFreeRequired",
        unit_field="clFreeRequiredUnit",
        entity_category=_DIAGNOSTIC,
    ),
    AsekoSensorDescription(
        key="salinity",
        translation_key="salinity",
        api_field="salinity",
        native_unit_of_measurement="kg/m³",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    AsekoSensorDescription(
        key="electrode_power",
        translation_key="electrode_power",
        api_field="electrodePower",
        native_unit_of_measurement="g/h",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    AsekoSensorDescription(
        key="filter_flow_speed",
        translation_key="filter_flow_speed",
        api_field="filterFlowSpeed",
        device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
        native_unit_of_measurement=UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    AsekoSensorDescription(
        key="filter_pressure",
        translation_key="filter_pressure",
        api_field="filterPressure",
        device_class=SensorDeviceClass.PRESSURE,
        native_unit_of_measurement=UnitOfPressure.BAR,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    AsekoSensorDescription(
        key="water_level",
        translation_key="water_level",
        api_field="waterLevel",
        native_unit_of_measurement="cm",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    _enum("mode", "mode", ["auto", "eco", "off", "on", "party", "winter"]),
    _enum(
        "filtration_speed",
        "filtrationSpeed",
        ["boost", "high", "low", "medium", "off"],
    ),
    _enum("pool_flow", "poolFlow", ["overflow", "bottom"]),
    _enum("water_level_state", "waterLevelState", ["ok", "filling", "low", "high"]),
    _enum(
        "electrolyzer_direction",
        "electrolyzerDirection",
        ["left", "right", "waiting"],
    ),
    _filtration_period("filtration_period_start", "start"),
    _filtration_period("filtration_period_end", "end"),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AsekoCloudConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Aseko Cloud sensors from a config entry."""
    async_add_unit_entities(
        entry,
        entry.runtime_data,
        async_add_entities,
        SENSORS,
        _reports_field,
        AsekoCloudSensor,
    )


def _reports_field(description: AsekoSensorDescription, unit: AsekoUnit) -> bool:
    """Return True when the unit reports the field backing the sensor."""
    return description.api_field in unit.status_values


class AsekoCloudSensor(AsekoCloudEntity, SensorEntity):
    """A measurement read from an Aseko pool unit."""

    entity_description: AsekoSensorDescription

    def __init__(
        self,
        coordinator: AsekoCloudCoordinator,
        serial_number: str,
        description: AsekoSensorDescription,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, serial_number)
        self.entity_description = description
        self._attr_unique_id = f"{serial_number}_{description.key}"

    @property
    def native_value(self) -> StateType:
        """Return the current sensor value."""
        description = self.entity_description
        value = self.unit.status_values.get(description.api_field)
        if description.value_key is not None:
            if not isinstance(value, dict):
                return None
            value = value.get(description.value_key)
        if value is None:
            return None
        if description.is_enum:
            option = str(value).lower()
            if option not in (description.options or ()):
                # A value added to the API after this release; report it as
                # unknown instead of letting Home Assistant log an error.
                LOGGER.debug("Unknown %s value from Aseko: %s", description.key, value)
                return None
            return option
        return value

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit, preferring an API-reported unit when available."""
        description = self.entity_description
        if description.unit_field and self.available:
            reported = self.unit.status_values.get(description.unit_field)
            if reported:
                return reported
        return description.native_unit_of_measurement
