"""Base entity for the Aseko Cloud integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import AsekoUnit
from .const import DOMAIN, MANUFACTURER
from .coordinator import AsekoCloudCoordinator


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
