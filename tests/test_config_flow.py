"""Config-flow tests: setup, duplicates, reauth and reconfigure."""

from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.aseko_cloud.config_flow import _api_key_id
from custom_components.aseko_cloud.const import API_BASE_URL, DOMAIN

from .conftest import BLOCKED_BODIES, mock_units_ok, setup_ok


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


async def test_user_flow_aborts_for_already_configured_key(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """The same API key cannot be added twice."""
    aioclient_mock.get(f"{API_BASE_URL}/auth/check", json={"valid": True})
    MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_KEY: "valid-key"},
        unique_id=_api_key_id("valid-key"),
    ).add_to_hass(hass)

    result = await _start_user_flow(hass)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_replaces_the_key(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Reauth stores the new key on the existing entry."""
    entry = await setup_ok(hass, aioclient_mock)
    aioclient_mock.clear_requests()
    mock_units_ok(aioclient_mock)

    result = await entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "new-key"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_API_KEY] == "new-key"
    assert entry.unique_id == _api_key_id("new-key")


async def test_reauth_rejects_key_of_another_entry(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Reauth refuses a key that another entry already uses."""
    entry = await setup_ok(hass, aioclient_mock)
    MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_KEY: "other-key"},
        unique_id=_api_key_id("other-key"),
    ).add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "other-key"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_API_KEY] == "test-key"


async def test_reconfigure_replaces_the_key(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Reconfigure swaps the key in place and keeps the entry and its devices."""
    entry = await setup_ok(hass, aioclient_mock)
    aioclient_mock.clear_requests()
    mock_units_ok(aioclient_mock)

    result = await entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "new-key"}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_API_KEY] == "new-key"
    assert entry.unique_id == _api_key_id("new-key")
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


async def test_reconfigure_rejects_key_of_another_entry(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Reconfigure cannot switch to a key another entry already uses."""
    entry = await setup_ok(hass, aioclient_mock)
    MockConfigEntry(
        domain=DOMAIN,
        data={CONF_API_KEY: "other-key"},
        unique_id=_api_key_id("other-key"),
    ).add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "other-key"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data[CONF_API_KEY] == "test-key"


async def test_reconfigure_reports_invalid_key(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """An invalid key keeps the form open with an error."""
    entry = await setup_ok(hass, aioclient_mock)
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{API_BASE_URL}/auth/check", status=401, json={})

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "bad-key"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
