"""Config flow for the Aseko Cloud integration."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_API_KEY
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    AsekoAccessBlockedError,
    AsekoAuthError,
    AsekoCloudApi,
    AsekoCloudError,
)
from .const import API_KEYS_URL, DOMAIN, LOGGER

STEP_API_KEY_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
    }
)


def _api_key_id(api_key: str) -> str:
    """Stable identifier derived from an API key, used as the unique id."""
    return hashlib.sha256(api_key.encode()).hexdigest()[:16]


class AsekoCloudConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config and reauth flow for Aseko Cloud."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for an API key and validate it."""
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {"url": API_KEYS_URL}
        if user_input is not None:
            error, message = await self._async_validate(user_input[CONF_API_KEY])
            if error:
                errors["base"] = error
                if message:
                    placeholders["error"] = message
            else:
                await self.async_set_unique_id(_api_key_id(user_input[CONF_API_KEY]))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="Aseko Cloud", data=user_input)
        return self.async_show_form(
            step_id="user",
            data_schema=STEP_API_KEY_SCHEMA,
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start reauthentication after the stored API key stopped working."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect a fresh API key and update the existing entry."""
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {"url": API_KEYS_URL}
        if user_input is not None:
            error, message = await self._async_validate(user_input[CONF_API_KEY])
            if error:
                errors["base"] = error
                if message:
                    placeholders["error"] = message
            else:
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(), data=user_input
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_API_KEY_SCHEMA,
            errors=errors,
            description_placeholders=placeholders,
        )

    async def _async_validate(
        self, api_key: str
    ) -> tuple[str | None, str | None]:
        """Validate an API key against ``/auth/check``.

        Returns ``(error_key, message)``. ``message`` is the backend's localised
        text for the ``access_blocked`` error (so the UI can show the real
        reason), and ``None`` otherwise.
        """
        api = AsekoCloudApi(
            async_get_clientsession(self.hass),
            api_key,
            self.hass.config.language,
        )
        try:
            await api.async_check()
        except AsekoAccessBlockedError as err:
            # Key is valid; an account condition (unaccepted Terms of Service,
            # unpaid subscription, ...) blocks it. Show the localised backend
            # reason rather than the misleading "cannot connect".
            return "access_blocked", err.message
        except AsekoAuthError:
            return "invalid_auth", None
        except AsekoCloudError:
            return "cannot_connect", None
        except Exception:  # noqa: BLE001
            LOGGER.exception("Unexpected error validating Aseko API key")
            return "unknown", None
        return None, None
