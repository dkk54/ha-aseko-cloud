"""Client for the official Aseko integrator API.

Wraps ``https://api.aseko.cloud/api/v1`` -- the public, API-key authenticated
integrator API. Self-contained (no Home Assistant imports) so it can later be
extracted into a PyPI package for a Home Assistant core submission.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import Any

import aiohttp

from .const import API_BASE_URL, CLIENT_NAME, CLIENT_VERSION

REQUEST_TIMEOUT = 15
PAGE_SIZE = 50


class AsekoCloudError(Exception):
    """Base error for the Aseko integrator API."""


class AsekoConnectionError(AsekoCloudError):
    """Raised when the API cannot be reached."""


class AsekoAuthError(AsekoCloudError):
    """Raised when the API key is missing, invalid or expired."""


@dataclass
class AsekoUnit:
    """An Aseko pool unit returned by ``/paired-units/{serialNumber}``."""

    serial_number: str
    name: str
    online: bool
    note: str | None = None
    brand: str | None = None
    # Raw ``statusValues`` object. Fields are already clean and typed; a missing
    # key means the metric is unsupported by this unit.
    status_values: dict[str, Any] = field(default_factory=dict)
    status_messages: list[dict[str, Any]] = field(default_factory=list)

    @property
    def has_error(self) -> bool:
        """Return True if any status message has ERROR severity."""
        return any(m.get("severity") == "ERROR" for m in self.status_messages)


class AsekoCloudApi:
    """Authenticated client for the Aseko integrator API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        api_key: str,
        language: str = "en",
    ) -> None:
        """Initialise the client with an API key."""
        self._session = session
        self._api_key = api_key
        self._language = language

    async def async_check(self) -> None:
        """Validate the API key. Raises :class:`AsekoAuthError` if invalid."""
        data = await self._get("/auth/check")
        if not data.get("valid"):
            raise AsekoAuthError("The API key is not valid")

    async def async_get_units(self) -> dict[str, AsekoUnit]:
        """Return every paired unit (with detail), keyed by serial number."""
        units: dict[str, AsekoUnit] = {}
        page = 1
        while True:
            collection = await self._get(
                "/paired-units", params={"page": page, "limit": PAGE_SIZE}
            )
            items = collection.get("items") or []
            for item in items:
                serial = item.get("serialNumber")
                if serial:
                    units[serial] = await self.async_get_unit(serial)
            total = collection.get("totalItems", len(units))
            if not items or len(units) >= total:
                return units
            page += 1

    async def async_get_unit(self, serial_number: str) -> AsekoUnit:
        """Return the full detail for a single unit."""
        data = await self._get(f"/paired-units/{serial_number}")
        return _parse_unit(data)

    async def _get(
        self, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Perform an authenticated GET and return the decoded JSON body."""
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "X-Client-Name": CLIENT_NAME,
            "X-Client-Version": CLIENT_VERSION,
            "Accept-Language": self._language,
        }
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                async with self._session.get(
                    f"{API_BASE_URL}{path}", headers=headers, params=params
                ) as resp:
                    if resp.status in (
                        HTTPStatus.UNAUTHORIZED,
                        HTTPStatus.FORBIDDEN,
                    ):
                        raise AsekoAuthError(
                            f"Aseko rejected the API key ({resp.status})"
                        )
                    resp.raise_for_status()
                    return await resp.json()
        except AsekoAuthError:
            raise
        except TimeoutError as err:
            raise AsekoConnectionError("Timed out contacting Aseko") from err
        except aiohttp.ClientError as err:
            raise AsekoConnectionError(str(err)) from err


def _parse_unit(data: dict[str, Any]) -> AsekoUnit:
    """Map a raw ``PairedUnit`` payload onto an AsekoUnit."""
    serial = data["serialNumber"]
    brand = data.get("brandName") or {}
    return AsekoUnit(
        serial_number=serial,
        name=data.get("name") or serial,
        online=data.get("online", False),
        note=data.get("note"),
        brand=brand.get("primary"),
        status_values=data.get("statusValues") or {},
        status_messages=data.get("statusMessages") or [],
    )
