"""Image platform for the Aseko Cloud integration."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components.image import ImageEntity, ImageEntityDescription
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import AsekoCloudConfigEntry
from .api import AsekoUnit
from .coordinator import AsekoCloudCoordinator
from .entity import AsekoCloudEntity, async_add_unit_entities

# The photos ship with the integration, nothing is fetched.
PARALLEL_UPDATES = 0

IMAGES_DIR = Path(__file__).parent / "images"

# Photos by the brand name the API reports, as (primary, secondary).
FAMILY_IMAGES: dict[tuple[str, str], str] = {
    ("ASIN AQUA", "Home"): "asin_aqua_home.webp",
    ("ASIN AQUA", "Home Pro"): "asin_aqua_home_pro.webp",
    ("ASIN AQUA", "Net"): "asin_aqua_net.webp",
    ("ASIN AQUA", "Net+"): "asin_aqua_net_plus.webp",
    ("ASIN AQUA", "Oxygen"): "asin_aqua_oxygen.webp",
    ("ASIN AQUA", "Pro"): "asin_aqua_pro.webp",
    ("ASIN AQUA", "Profi"): "asin_aqua_profi.webp",
    ("ASIN AQUA", "Salt"): "asin_aqua_salt.webp",
    ("ASIN AQUA", "Salt Net"): "asin_aqua_salt_net.webp",
    ("ASIN AQUA", "Salt Pro"): "asin_aqua_salt_pro.webp",
    ("ASIN AQUA", "Eox"): "asin_aqua_salt_eox.webp",
    ("ASIN AQUA", "Eox Pro"): "asin_aqua_salt_pro_eox.webp",
    ("ASIN", "Pool"): "asin_pool.webp",
}

PHOTO = ImageEntityDescription(key="photo", translation_key="photo")


def unit_image(unit: AsekoUnit) -> str | None:
    """Return the file name of the photo for a unit, if there is one.

    Units of a family without a photo and units that were never online, which
    have no brand name yet, get none.
    """
    return FAMILY_IMAGES.get((unit.brand, unit.brand_secondary))


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AsekoCloudConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the unit photos from a config entry."""
    async_add_unit_entities(
        entry,
        entry.runtime_data,
        async_add_entities,
        [PHOTO],
        lambda description, unit: True,
        AsekoCloudImage,
    )


class AsekoCloudImage(AsekoCloudEntity, ImageEntity):
    """A photo of an Aseko pool unit, picked by its family."""

    _attr_content_type = "image/webp"

    def __init__(
        self,
        coordinator: AsekoCloudCoordinator,
        serial_number: str,
        description: ImageEntityDescription,
    ) -> None:
        """Initialise the photo."""
        super().__init__(coordinator, serial_number)
        ImageEntity.__init__(self, coordinator.hass)
        self.entity_description = description
        self._attr_unique_id = f"{serial_number}_{description.key}"
        self._image = unit_image(self.unit)
        self._attr_image_last_updated = dt_util.utcnow()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Switch the photo once the unit reports a different family."""
        if self._serial_number in self.coordinator.data:
            image = unit_image(self.unit)
            if image != self._image:
                self._image = image
                self._attr_image_last_updated = dt_util.utcnow()
        super()._handle_coordinator_update()

    @property
    def entity_picture(self) -> str | None:
        """Return the photo URL, or none while the unit has no photo."""
        return super().entity_picture if self._image else None

    async def async_image(self) -> bytes | None:
        """Return the photo."""
        if self._image is None:
            return None
        return await self.hass.async_add_executor_job(
            (IMAGES_DIR / self._image).read_bytes
        )
