"""Dashboard tests: the pool dashboard ships with the integration."""

from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from homeassistant.core import HomeAssistant

from .conftest import make_entry, mock_units, unit_payload


@pytest.mark.parametrize(
    ("path", "content_type"),
    [
        ("aseko-pool-loader.js", "text/javascript"),
        ("aseko-pool.js", "text/javascript"),
        ("aseko-logo.svg", "image/svg+xml"),
    ],
)
async def test_dashboard_is_served(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    hass_client: ClientSessionGenerator,
    path: str,
    content_type: str,
) -> None:
    """Home Assistant serves the dashboard files once the integration is set up."""
    mock_units(aioclient_mock, [unit_payload()])
    entry = make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    client = await hass_client()
    response = await client.get(f"/aseko_cloud/dashboard/{path}")
    assert response.status == 200
    assert response.content_type == content_type
