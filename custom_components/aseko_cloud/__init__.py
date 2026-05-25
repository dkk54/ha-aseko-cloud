"""The Aseko Cloud integration."""

from __future__ import annotations

import asyncio

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.importlib import async_import_module

from .coordinator import AsekoCloudCoordinator

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]

type AsekoCloudConfigEntry = ConfigEntry[AsekoCloudCoordinator]


async def async_setup_entry(
    hass: HomeAssistant, entry: AsekoCloudConfigEntry
) -> bool:
    """Set up Aseko Cloud from a config entry."""
    # Pre-import platform modules in the executor so async_forward_entry_setups
    # below does not trigger a blocking import on the event loop. This is the
    # Home Assistant-blessed pattern for custom integrations.
    await asyncio.gather(
        *(
            async_import_module(hass, f"{__package__}.{platform.value}")
            for platform in PLATFORMS
        )
    )

    coordinator = AsekoCloudCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: AsekoCloudConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
