"""API-client tests: error classification, paging, key expiry and parsing."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.aseko_cloud.api import (
    AsekoAccessBlockedError,
    AsekoAuthError,
    AsekoCloudApi,
    PAGE_SIZE,
)
from custom_components.aseko_cloud.const import API_BASE_URL

from .conftest import BLOCKED_BODIES, mock_auth_error, mock_blocked, unit_payload


def _api(hass: HomeAssistant) -> AsekoCloudApi:
    return AsekoCloudApi(async_get_clientsession(hass), "test-key", "cs")


def test_access_blocked_is_not_an_auth_error() -> None:
    """A blocked-access error must not be caught by AsekoAuthError handlers."""
    assert not issubclass(AsekoAccessBlockedError, AsekoAuthError)


@pytest.mark.parametrize("body", BLOCKED_BODIES)
async def test_recoverable_403_raises_access_blocked(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, body: dict
) -> None:
    """A 403 with a known errorType carries the backend message and the type."""
    mock_blocked(aioclient_mock, body)
    with pytest.raises(AsekoAccessBlockedError) as err:
        await _api(hass).async_get_units()
    assert err.value.message == body["error"]
    assert err.value.error_type == body["errorType"]


async def test_unknown_403_is_auth_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A 403 with an unrecognised errorType stays an auth failure."""
    aioclient_mock.get(
        f"{API_BASE_URL}/paired-units",
        status=403,
        json={"error": "nope", "errorType": "FORBIDDEN", "statusCode": 403},
    )
    with pytest.raises(AsekoAuthError):
        await _api(hass).async_get_units()


async def test_403_with_empty_body_is_auth_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A 403 with no/garbage JSON body falls back to auth failure."""
    aioclient_mock.get(f"{API_BASE_URL}/paired-units", status=403, text="")
    with pytest.raises(AsekoAuthError):
        await _api(hass).async_get_units()


async def test_401_is_auth_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A 401 is an auth failure, never a blocked-access error."""
    mock_auth_error(aioclient_mock, 401)
    with pytest.raises(AsekoAuthError):
        await _api(hass).async_get_units()


async def test_units_are_collected_across_pages(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Every page of the listing is read and every unit's detail fetched."""
    aioclient_mock.get(
        f"{API_BASE_URL}/paired-units",
        params={"page": 1, "limit": PAGE_SIZE},
        json={
            "items": [{"serialNumber": "SN1"}, {"serialNumber": "SN2"}],
            "totalItems": 3,
        },
    )
    aioclient_mock.get(
        f"{API_BASE_URL}/paired-units",
        params={"page": 2, "limit": PAGE_SIZE},
        json={"items": [{"serialNumber": "SN3"}], "totalItems": 3},
    )
    for serial in ("SN1", "SN2", "SN3"):
        aioclient_mock.get(
            f"{API_BASE_URL}/paired-units/{serial}", json=unit_payload(serial)
        )

    units = await _api(hass).async_get_units()

    assert list(units) == ["SN1", "SN2", "SN3"]
    assert units["SN3"].status_values == {"waterTemperature": 25.0}


async def test_unit_without_serial_in_detail_uses_requested_serial(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A detail payload missing serialNumber falls back to the requested one."""
    aioclient_mock.get(f"{API_BASE_URL}/paired-units/SN1", json={"online": True})

    unit = await _api(hass).async_get_unit("SN1")

    assert unit.serial_number == "SN1"
    assert unit.name == "SN1"


@pytest.mark.parametrize(
    ("expires_at", "expected"),
    [
        ("2026-11-20T08:00:00.000Z", datetime(2026, 11, 20, 8, tzinfo=UTC)),
        ("2026-11-20T08:00:00", datetime(2026, 11, 20, 8, tzinfo=UTC)),
        (None, None),
        ("not a date", None),
    ],
)
async def test_check_reports_key_expiry(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    expires_at: str | None,
    expected: datetime | None,
) -> None:
    """``/auth/check`` exposes when the key expires, if it ever does."""
    aioclient_mock.get(
        f"{API_BASE_URL}/auth/check", json={"valid": True, "expiresAt": expires_at}
    )

    check = await _api(hass).async_check()

    assert check.expires_at == expected


async def test_check_rejects_invalid_key(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """``valid: false`` is an auth failure."""
    aioclient_mock.get(
        f"{API_BASE_URL}/auth/check", json={"valid": False, "expiresAt": None}
    )

    with pytest.raises(AsekoAuthError):
        await _api(hass).async_check()
