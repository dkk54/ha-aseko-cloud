"""Diagnostics support for the Aseko Cloud integration."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant

from . import AsekoCloudConfigEntry

TO_REDACT = {CONF_API_KEY, "note"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: AsekoCloudConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry, without the API key."""
    coordinator = entry.runtime_data
    expires_at = coordinator.key_expires_at
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "api_key_expires_at": expires_at.isoformat() if expires_at else None,
        "last_update_success": coordinator.last_update_success,
        "units": async_redact_data(
            [asdict(unit) for unit in (coordinator.data or {}).values()], TO_REDACT
        ),
    }
