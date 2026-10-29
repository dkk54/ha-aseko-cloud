"""Data update coordinator for the Aseko Cloud integration."""

from __future__ import annotations

from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr, issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    AsekoAccessBlockedError,
    AsekoAuthError,
    AsekoCloudApi,
    AsekoCloudError,
    AsekoConnectionError,
    AsekoUnit,
)
from .const import (
    ACCOUNT_URL,
    API_KEYS_URL,
    AUTH_CHECK_INTERVAL,
    DOMAIN,
    KEY_EXPIRY_WARNING,
    LOGGER,
    SCAN_INTERVAL,
)


def access_blocked_issue_id(entry_id: str) -> str:
    """Repair-issue id for the access-blocked condition of a config entry."""
    return f"access_blocked_{entry_id}"


def key_expiring_issue_id(entry_id: str) -> str:
    """Repair-issue id for an API key that is about to expire."""
    return f"api_key_expiring_{entry_id}"


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
        self.key_expires_at: datetime | None = None
        self._key_checked_at: datetime | None = None

    async def _async_update_data(self) -> dict[str, AsekoUnit]:
        """Fetch every paired unit and its current state."""
        # Follow a language change in Home Assistant without a reload.
        self.api.language = self.hass.config.language
        try:
            await self._async_check_key_expiry()
            data = await self.api.async_get_units()
        except AsekoAccessBlockedError as err:
            self._raise_access_blocked_issue(err.message)
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="access_blocked",
                translation_placeholders={"error": err.message},
            ) from err
        except AsekoAuthError as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="invalid_auth"
            ) from err
        except AsekoCloudError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="cannot_connect",
                translation_placeholders={"error": str(err)},
            ) from err
        ir.async_delete_issue(
            self.hass, DOMAIN, access_blocked_issue_id(self.config_entry.entry_id)
        )
        self._remove_stale_devices(data)
        return data

    async def _async_check_key_expiry(self) -> None:
        """Warn through a repair issue when the API key is about to expire.

        An expired key is already handled by reauth (the API answers 401); this
        gives the user time to replace it before the integration stops working.
        A failed check must not block the unit poll, so it is retried later.
        """
        now = dt_util.utcnow()
        if (
            self._key_checked_at is not None
            and now - self._key_checked_at < AUTH_CHECK_INTERVAL
        ):
            return
        try:
            check = await self.api.async_check()
        except AsekoConnectionError as err:
            LOGGER.debug("Could not check the API key expiry: %s", err)
            return
        self._key_checked_at = now
        self.key_expires_at = check.expires_at

        issue_id = key_expiring_issue_id(self.config_entry.entry_id)
        if check.expires_at is None or check.expires_at - now > KEY_EXPIRY_WARNING:
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)
            return
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            learn_more_url=API_KEYS_URL,
            translation_key="api_key_expiring",
            translation_placeholders={
                "expires": dt_util.as_local(check.expires_at).date().isoformat(),
                "url": API_KEYS_URL,
            },
        )

    def _remove_stale_devices(self, units: dict[str, AsekoUnit]) -> None:
        """Remove devices of units that are no longer paired with the account.

        An empty listing is never taken as every unit being unpaired: a glitch
        on the Aseko side would otherwise wipe all devices together with their
        names, areas and dashboard references. The devices stay unavailable.
        """
        if not units:
            return
        device_registry = dr.async_get(self.hass)
        for device in dr.async_entries_for_config_entry(
            device_registry, self.config_entry.entry_id
        ):
            serials = {
                ident for domain, ident in device.identifiers if domain == DOMAIN
            }
            if serials and not serials & units.keys():
                LOGGER.debug("Removing device of unpaired unit %s", serials)
                device_registry.async_update_device(
                    device.id, remove_config_entry_id=self.config_entry.entry_id
                )

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
