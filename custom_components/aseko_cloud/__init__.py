"""The Aseko Cloud integration."""

from __future__ import annotations

import asyncio
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.importlib import async_import_module
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from .const import DOMAIN
from .coordinator import AsekoCloudCoordinator

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.IMAGE, Platform.SENSOR]

type AsekoCloudConfigEntry = ConfigEntry[AsekoCloudCoordinator]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

# The pool dashboard ships with the integration and is served from here.
DASHBOARD_URL = f"/{DOMAIN}/dashboard"
DASHBOARD_DIR = Path(__file__).parent / "frontend"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Serve the pool dashboard (strategy custom:aseko-pool) to the frontend."""
    integration = await async_get_integration(hass, DOMAIN)
    await hass.http.async_register_static_paths(
        [StaticPathConfig(DASHBOARD_URL, str(DASHBOARD_DIR), True)]
    )
    if "frontend" in hass.config.components:
        # The version makes browsers fetch the dashboard afresh after an update.
        add_extra_js_url(
            hass, f"{DASHBOARD_URL}/aseko-pool-loader.js?v={integration.version}"
        )
    return True


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
