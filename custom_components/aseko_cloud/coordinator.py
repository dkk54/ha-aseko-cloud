"""Data update coordinator for the Aseko Cloud integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AsekoAuthError, AsekoCloudApi, AsekoCloudError, AsekoUnit
from .const import DOMAIN, LOGGER, SCAN_INTERVAL


class AsekoCloudCoordinator(DataUpdateCoordinator[dict[str, AsekoUnit]]):
    """Polls the Aseko integrator API and shares the result with all entities."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialise the coordinator and API client."""
        super().__init__(
            hass,
            LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.api = AsekoCloudApi(
            async_get_clientsession(hass),
            config_entry.data[CONF_API_KEY],
            hass.config.language,
        )

    async def _async_update_data(self) -> dict[str, AsekoUnit]:
        """Fetch every paired unit and its current state."""
        try:
            return await self.api.async_get_units()
        except AsekoAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except AsekoCloudError as err:
            raise UpdateFailed(str(err)) from err
