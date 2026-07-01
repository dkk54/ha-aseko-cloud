"""Coordinator tests: a blocked-access 403 is transient, not an auth failure."""

from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from homeassistant.config_entries import SOURCE_REAUTH
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.aseko_cloud.const import ACCOUNT_URL, DOMAIN
from custom_components.aseko_cloud.coordinator import access_blocked_issue_id

from .conftest import (
    BLOCKED_BODIES,
    TOS_BODY,
    mock_auth_error,
    mock_blocked,
    mock_units_ok,
    setup_ok,
)


def _reauth_flows(hass: HomeAssistant) -> list:
    return [
        flow
        for flow in hass.config_entries.flow.async_progress()
        if flow["context"].get("source") == SOURCE_REAUTH
    ]


@pytest.mark.parametrize("body", BLOCKED_BODIES)
async def test_blocked_raises_update_failed_and_opens_repair_issue(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, body: dict
) -> None:
    """Any recoverable 403 surfaces as UpdateFailed plus an actionable issue."""
    entry = await setup_ok(hass, aioclient_mock)
    coordinator = entry.runtime_data
    assert coordinator.last_update_success

    aioclient_mock.clear_requests()
    mock_blocked(aioclient_mock, body)
    await coordinator.async_refresh()

    assert coordinator.last_update_success is False
    assert isinstance(coordinator.last_exception, UpdateFailed)

    issue = ir.async_get(hass).async_get_issue(
        DOMAIN, access_blocked_issue_id(entry.entry_id)
    )
    assert issue is not None
    assert issue.is_fixable is True
    assert issue.translation_key == "access_blocked"
    assert issue.translation_placeholders == {
        "error": body["error"],
        "url": ACCOUNT_URL,
    }


async def test_blocked_does_not_trigger_reauth(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """The whole point of the fix: a valid key must not be sent to reauth."""
    entry = await setup_ok(hass, aioclient_mock)
    aioclient_mock.clear_requests()
    mock_blocked(aioclient_mock, TOS_BODY)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert _reauth_flows(hass) == []


async def test_recovers_automatically_after_resolved(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Once the user resolves it, the next poll succeeds and clears the issue."""
    entry = await setup_ok(hass, aioclient_mock)
    coordinator = entry.runtime_data
    reg = ir.async_get(hass)

    aioclient_mock.clear_requests()
    mock_blocked(aioclient_mock, TOS_BODY)
    await coordinator.async_refresh()
    assert reg.async_get_issue(DOMAIN, access_blocked_issue_id(entry.entry_id))

    aioclient_mock.clear_requests()
    mock_units_ok(aioclient_mock)
    await coordinator.async_refresh()

    assert coordinator.last_update_success is True
    assert reg.async_get_issue(DOMAIN, access_blocked_issue_id(entry.entry_id)) is None


async def test_genuine_auth_failure_triggers_reauth_without_issue(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A real bad key still goes through reauth and opens no repair issue."""
    entry = await setup_ok(hass, aioclient_mock)
    coordinator = entry.runtime_data

    aioclient_mock.clear_requests()
    mock_auth_error(aioclient_mock, 401)
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator.last_update_success is False
    assert len(_reauth_flows(hass)) == 1
    assert (
        ir.async_get(hass).async_get_issue(
            DOMAIN, access_blocked_issue_id(entry.entry_id)
        )
        is None
    )
