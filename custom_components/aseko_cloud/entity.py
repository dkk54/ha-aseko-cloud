"""Base entity for the Aseko Cloud integration."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity, EntityDescription
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import AsekoUnit
from .const import ACCOUNT_URL, DOMAIN, MANUFACTURER
from .coordinator import AsekoCloudCoordinator


@callback
def async_add_unit_entities[DescriptionT: EntityDescription](
    entry: ConfigEntry,
    coordinator: AsekoCloudCoordinator,
    async_add_entities: AddConfigEntryEntitiesCallback,
    descriptions: Sequence[DescriptionT],
    exists: Callable[[DescriptionT, AsekoUnit], bool],
    entity_factory: Callable[[AsekoCloudCoordinator, str, DescriptionT], Entity],
) -> None:
    """Add entities for every unit now and for units paired later.

    After each poll, entities are created for units and metrics that were not
    seen before, so a unit paired in the Aseko app shows up without a reload.
    Entities of an unpaired unit are removed together with its device by the
    coordinator; forgetting them here lets them come back if it is re-paired.
    """
    added: set[tuple[str, str]] = set()

    @callback
    def _async_add_new_entities() -> None:
        units = coordinator.data or {}
        added.intersection_update(
            {(serial, key) for serial, key in added if serial in units}
        )
        new = [
            (serial, description)
            for serial, unit in units.items()
            for description in descriptions
            if (serial, description.key) not in added and exists(description, unit)
        ]
        if not new:
            return
        added.update((serial, description.key) for serial, description in new)
        async_add_entities(
            entity_factory(coordinator, serial, description)
            for serial, description in new
        )

    _async_add_new_entities()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_new_entities))


class AsekoCloudEntity(CoordinatorEntity[AsekoCloudCoordinator]):
    """Common base for all Aseko Cloud entities.

    Every entity belongs to a single pool unit, exposed as one device.
    """

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: AsekoCloudCoordinator, serial_number: str
    ) -> None:
        """Initialise the entity for one pool unit."""
        super().__init__(coordinator)
        self._serial_number = serial_number
        unit = self.unit
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, serial_number)},
            configuration_url=ACCOUNT_URL,
            manufacturer=MANUFACTURER,
            model=unit.brand,
            name=unit.name,
            serial_number=serial_number,
        )

    @property
    def unit(self) -> AsekoUnit:
        """Return the current data for this entity's pool unit."""
        return self.coordinator.data[self._serial_number]

    @property
    def available(self) -> bool:
        """Return True when the last poll succeeded and the unit is present."""
        return super().available and self._serial_number in self.coordinator.data
