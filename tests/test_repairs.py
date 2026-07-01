"""Repair-flow tests: the Refresh button re-polls and clears the issue."""

from __future__ import annotations

from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import issue_registry as ir

from custom_components.aseko_cloud.const import ACCOUNT_URL, DOMAIN
from custom_components.aseko_cloud.coordinator import access_blocked_issue_id
from custom_components.aseko_cloud.repairs import async_create_fix_flow

from .conftest import TOS_BODY, mock_blocked, mock_units_ok, setup_ok


async def _make_flow(hass: HomeAssistant, entry: MockConfigEntry):
    flow = await async_create_fix_flow(
        hass,
        access_blocked_issue_id(entry.entry_id),
        {"entry_id": entry.entry_id, "error": TOS_BODY["error"], "url": ACCOUNT_URL},
    )
    flow.hass = hass
    return flow


async def _fail_blocked(hass, aioclient_mock, entry) -> None:
    aioclient_mock.clear_requests()
    mock_blocked(aioclient_mock, TOS_BODY)
    await entry.runtime_data.async_refresh()
    assert ir.async_get(hass).async_get_issue(
        DOMAIN, access_blocked_issue_id(entry.entry_id)
    )


async def test_fix_flow_shows_localised_message(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """The confirm step shows the backend's (localised) error verbatim."""
    entry = await setup_ok(hass, aioclient_mock)
    flow = await _make_flow(hass, entry)

    result = await flow.async_step_init()

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "confirm"
    assert result["description_placeholders"] == {
        "error": TOS_BODY["error"],
        "url": ACCOUNT_URL,
    }


async def test_refresh_clears_issue_when_resolved(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Submitting after resolution re-polls, succeeds and removes the issue."""
    entry = await setup_ok(hass, aioclient_mock)
    coordinator = entry.runtime_data
    await _fail_blocked(hass, aioclient_mock, entry)

    aioclient_mock.clear_requests()
    mock_units_ok(aioclient_mock)
    flow = await _make_flow(hass, entry)
    await flow.async_step_init()
    result = await flow.async_step_confirm({})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert coordinator.last_update_success is True
    assert (
        ir.async_get(hass).async_get_issue(
            DOMAIN, access_blocked_issue_id(entry.entry_id)
        )
        is None
    )


async def test_refresh_aborts_when_still_blocked(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Submitting while still blocked aborts and keeps the issue."""
    entry = await setup_ok(hass, aioclient_mock)
    await _fail_blocked(hass, aioclient_mock, entry)

    flow = await _make_flow(hass, entry)
    await flow.async_step_init()
    result = await flow.async_step_confirm({})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "still_blocked"
    assert ir.async_get(hass).async_get_issue(
        DOMAIN, access_blocked_issue_id(entry.entry_id)
    )
