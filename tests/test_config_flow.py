"""Config-flow tests: a blocked-access key reports a clear, localised error."""

from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.aseko_cloud.const import API_BASE_URL, DOMAIN

from .conftest import BLOCKED_BODIES


async def _start_user_flow(hass: HomeAssistant) -> dict:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "valid-key"}
    )


@pytest.mark.parametrize("body", BLOCKED_BODIES)
async def test_user_flow_reports_access_blocked_with_backend_message(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, body: dict
) -> None:
    """A valid key with a blocked account shows the localised backend reason."""
    aioclient_mock.get(f"{API_BASE_URL}/auth/check", status=403, json=body)

    result = await _start_user_flow(hass)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "access_blocked"}
    assert result["description_placeholders"]["error"] == body["error"]


async def test_user_flow_reports_invalid_auth(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A genuine bad key is still reported as invalid_auth."""
    aioclient_mock.get(
        f"{API_BASE_URL}/auth/check",
        status=401,
        json={"errorType": "API_KEY_INVALID", "statusCode": 401},
    )

    result = await _start_user_flow(hass)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_user_flow_succeeds_with_valid_key(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A valid, unblocked key creates the entry."""
    aioclient_mock.get(f"{API_BASE_URL}/auth/check", json={"valid": True})

    result = await _start_user_flow(hass)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_API_KEY: "valid-key"}
