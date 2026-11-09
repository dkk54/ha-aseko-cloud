"""Shared fixtures and helpers for the Aseko Cloud tests."""

from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant

from custom_components.aseko_cloud.const import ACCOUNT_URL, API_BASE_URL, DOMAIN

# The 403 bodies the public API returns when the key is valid but an account
# condition blocks access. ``error`` is already localised by the backend.
TOS_BODY = {
    "error": "Terms of services are not accepted.",
    "errorType": "TOS_NOT_ACCEPTED",
    "statusCode": 403,
}
SUBSCRIPTION_BODY = {
    "error": "Your subscription is unpaid or insufficient.",
    "errorType": "UNPAID_OR_LOW_SUBSCRIPTION_PLAN",
    "statusCode": 403,
}
# Every recoverable-403 body, for parametrising tests over all of them.
BLOCKED_BODIES = [TOS_BODY, SUBSCRIPTION_BODY]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load the custom integration in every test."""
    yield


def unit_payload(serial: str = "SN1", **overrides: object) -> dict:
    """Build a ``PairedUnit`` detail payload."""
    payload = {
        "serialNumber": serial,
        "name": "Pool",
        "online": True,
        "statusValues": {"waterTemperature": 25.0},
        "statusMessages": [],
    }
    payload.update(overrides)
    return payload


def mock_units(
    aioclient_mock: AiohttpClientMocker,
    units: list[dict],
    expires_at: str | None = None,
) -> None:
    """Register a valid key check, the paired-units listing and every detail."""
    aioclient_mock.get(
        f"{API_BASE_URL}/auth/check", json={"valid": True, "expiresAt": expires_at}
    )
    aioclient_mock.get(
        f"{API_BASE_URL}/paired-units",
        json={
            "items": [{"serialNumber": unit["serialNumber"]} for unit in units],
            "totalItems": len(units),
        },
    )
    for unit in units:
        aioclient_mock.get(
            f"{API_BASE_URL}/paired-units/{unit['serialNumber']}", json=unit
        )


def mock_units_ok(aioclient_mock: AiohttpClientMocker) -> None:
    """Register a successful paired-units listing plus one unit's detail."""
    mock_units(aioclient_mock, [unit_payload()])


def mock_blocked(aioclient_mock: AiohttpClientMocker, body: dict) -> None:
    """Register a recoverable 403 (ToS / subscription) on the collection."""
    aioclient_mock.get(f"{API_BASE_URL}/paired-units", status=403, json=body)


def mock_auth_error(aioclient_mock: AiohttpClientMocker, status: int = 401) -> None:
    """Register a genuine authentication rejection (bad/expired key)."""
    aioclient_mock.get(
        f"{API_BASE_URL}/paired-units",
        status=status,
        json={"error": "bad key", "errorType": "API_KEY_INVALID", "statusCode": status},
    )


def make_entry() -> MockConfigEntry:
    """Build a config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Aseko Cloud",
        data={CONF_API_KEY: "test-key"},
        unique_id="testkey",
    )


async def setup_ok(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> MockConfigEntry:
    """Add and set up an entry whose first poll succeeds."""
    mock_units_ok(aioclient_mock)
    entry = make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry
