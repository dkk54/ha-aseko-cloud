"""API-client tests: classifying the 403 account-blocked responses."""

from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.aseko_cloud.api import (
    AsekoAccessBlockedError,
    AsekoAuthError,
    AsekoCloudApi,
)
from custom_components.aseko_cloud.const import API_BASE_URL

from .conftest import BLOCKED_BODIES, mock_auth_error, mock_blocked


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
