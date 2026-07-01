"""Data update coordinator for the Aseko Cloud integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    AsekoAccessBlockedError,
    AsekoAuthError,
    AsekoCloudApi,
    AsekoCloudError,
    AsekoUnit,
)
from .const import ACCOUNT_URL, DOMAIN, LOGGER, SCAN_INTERVAL


def access_blocked_issue_id(entry_id: str) -> str:
    """Repair-issue id for the access-blocked condition of a config entry."""
    return f"access_blocked_{entry_id}"


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
            data = await self.api.async_get_units()
        except AsekoAccessBlockedError as err:
            self._raise_access_blocked_issue(err.message)
            raise UpdateFailed(err.message) from err
        except AsekoAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except AsekoCloudError as err:
            raise UpdateFailed(str(err)) from err
        ir.async_delete_issue(
            self.hass, DOMAIN, access_blocked_issue_id(self.config_entry.entry_id)
        )
        return data

    def _raise_access_blocked_issue(self, message: str) -> None:
        """Surface an actionable repair issue for an account-blocked key.

        The key is valid; an account condition (unaccepted Terms of Service,
        unpaid subscription, ...) blocks the API, so this is treated as a
        transient failure: the coordinator keeps polling and recovers on its
        own once the user resolves it. ``message`` is the localised backend
        text, shown verbatim. ``entry_id`` is passed to the fix flow so its
        Refresh button can re-poll this exact entry.
        """
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            access_blocked_issue_id(self.config_entry.entry_id),
            is_fixable=True,
            severity=ir.IssueSeverity.ERROR,
            translation_key="access_blocked",
            translation_placeholders={"error": message, "url": ACCOUNT_URL},
            data={
                "entry_id": self.config_entry.entry_id,
                "error": message,
                "url": ACCOUNT_URL,
            },
        )
