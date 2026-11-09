"""Diagnostics tests: useful for support, without the API key."""

from __future__ import annotations

from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from homeassistant.components.diagnostics import REDACTED
from homeassistant.core import HomeAssistant

from custom_components.aseko_cloud.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .conftest import setup_ok


async def test_diagnostics_redact_the_api_key(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """The API key never appears; the unit data does."""
    entry = await setup_ok(hass, aioclient_mock)

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["entry"]["data"] == {"api_key": REDACTED}
    assert "test-key" not in str(diagnostics)
    assert diagnostics["last_update_success"] is True
    assert diagnostics["units"][0]["serial_number"] == "SN1"
    assert diagnostics["units"][0]["status_values"] == {"waterTemperature": 25.0}
