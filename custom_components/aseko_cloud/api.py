"""Client for the official Aseko integrator API.

Wraps ``https://api.aseko.cloud/api/v1`` -- the public, API-key authenticated
integrator API. Self-contained (no Home Assistant imports) so it can later be
extracted into a PyPI package for a Home Assistant core submission.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from http import HTTPStatus
from typing import Any

import aiohttp

from .const import API_BASE_URL, CLIENT_NAME, CLIENT_VERSION

REQUEST_TIMEOUT = 15
PAGE_SIZE = 50
# Unit details are fetched concurrently, but never more than this many at once.
MAX_CONCURRENT_REQUESTS = 5


class AsekoCloudError(Exception):
    """Base error for the Aseko integrator API."""


class AsekoConnectionError(AsekoCloudError):
    """Raised when the API cannot be reached."""


class AsekoAuthError(AsekoCloudError):
    """Raised when the API key is missing, invalid or expired."""


# 403 errorTypes that mean "the key is valid, but an account-level condition
# blocks access" -- the user must resolve it (accept new Terms of Service, pay
# the subscription, ...). These are transient and recoverable, NOT auth errors.
RECOVERABLE_403_ERROR_TYPES = frozenset(
    {"TOS_NOT_ACCEPTED", "UNPAID_OR_LOW_SUBSCRIPTION_PLAN"}
)


class AsekoAccessBlockedError(AsekoCloudError):
    """Raised when the API key is valid but access is blocked by an account
    condition the user must resolve (HTTP 403 with a known errorType, e.g.
    unaccepted Terms of Service or an unpaid/insufficient subscription).

    This is transient and user-recoverable and must NOT be treated as an
    authentication failure. ``message`` carries the backend's ``error`` string,
    already localised via the ``Accept-Language`` header, so it can be shown
    verbatim in the UI. ``error_type`` is the raw ``errorType``.
    """

    def __init__(self, message: str, error_type: str) -> None:
        """Store the localised backend message and the raw errorType."""
        super().__init__(message)
        self.message = message
        self.error_type = error_type


@dataclass
class AsekoAuthCheck:
    """The result of ``/auth/check`` for a valid API key."""

    # None when the key is configured to never expire.
    expires_at: datetime | None = None


@dataclass
class AsekoUnit:
    """An Aseko pool unit returned by ``/paired-units/{serialNumber}``."""

    serial_number: str
    name: str
    online: bool
    note: str | None = None
    brand: str | None = None
    brand_secondary: str | None = None
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
        # Sent as Accept-Language; the backend localises status messages by it.
        self.language = language
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    async def async_check(self) -> AsekoAuthCheck:
        """Validate the API key. Raises :class:`AsekoAuthError` if invalid."""
        data = await self._get("/auth/check")
        if not data.get("valid"):
            raise AsekoAuthError("The API key is not valid")
        return AsekoAuthCheck(expires_at=_parse_datetime(data.get("expiresAt")))

    async def async_get_units(self) -> dict[str, AsekoUnit]:
        """Return every paired unit (with detail), keyed by serial number.

        The collection endpoint does not include ``statusValues``, so each unit
        needs its own detail request; those run concurrently.
        """
        units: dict[str, AsekoUnit] = {}
        page = 1
        while True:
            collection = await self._get(
                "/paired-units", params={"page": page, "limit": PAGE_SIZE}
            )
            items = collection.get("items") or []
            serials = [s for item in items if (s := item.get("serialNumber"))]
            details = await asyncio.gather(*map(self.async_get_unit, serials))
            units.update(zip(serials, details, strict=True))
            total = collection.get("totalItems", len(units))
            if not items or len(units) >= total:
                return units
            page += 1

    async def async_get_unit(self, serial_number: str) -> AsekoUnit:
        """Return the full detail for a single unit."""
        async with self._semaphore:
            data = await self._get(f"/paired-units/{serial_number}")
        return _parse_unit(data, serial_number)

    async def _get(
        self, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Perform an authenticated GET and return the decoded JSON body."""
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "X-Client-Name": CLIENT_NAME,
            "X-Client-Version": CLIENT_VERSION,
            "Accept-Language": self.language,
        }
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                async with self._session.get(
                    f"{API_BASE_URL}{path}", headers=headers, params=params
                ) as resp:
                    # A 403 with a known errorType (unaccepted ToS, unpaid
                    # subscription, ...) means the key is fine but an account
                    # condition blocks access. Surface the localised backend
                    # message and keep it distinct from a real auth rejection so
                    # the integration recovers automatically.
                    if resp.status == HTTPStatus.FORBIDDEN:
                        blocked = await _access_blocked_error(resp)
                        if blocked is not None:
                            raise AsekoAccessBlockedError(*blocked)
                    if resp.status in (
                        HTTPStatus.UNAUTHORIZED,
                        HTTPStatus.FORBIDDEN,
                    ):
                        raise AsekoAuthError(
                            f"Aseko rejected the API key ({resp.status})"
                        )
                    resp.raise_for_status()
                    return await resp.json()
        except AsekoCloudError:
            raise
        except TimeoutError as err:
            raise AsekoConnectionError("Timed out contacting Aseko") from err
        except aiohttp.ClientError as err:
            raise AsekoConnectionError(str(err)) from err


async def _access_blocked_error(
    resp: aiohttp.ClientResponse,
) -> tuple[str, str] | None:
    """Return ``(message, error_type)`` if a 403 is a known recoverable account
    condition, else ``None`` (so the caller treats it as an auth failure).

    ``message`` is the backend's localised ``error`` text.
    """
    try:
        body = await resp.json()
    except (aiohttp.ClientError, ValueError):
        return None
    if not isinstance(body, dict):
        return None
    error_type = body.get("errorType")
    if error_type not in RECOVERABLE_403_ERROR_TYPES:
        return None
    message = body.get("error") or "Access to the Aseko API is blocked"
    return message, error_type


def _parse_datetime(value: Any) -> datetime | None:
    """Parse an ISO 8601 timestamp from the API; naive values are UTC."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _parse_unit(data: dict[str, Any], serial_number: str) -> AsekoUnit:
    """Map a raw ``PairedUnit`` payload onto an AsekoUnit."""
    serial = data.get("serialNumber") or serial_number
    brand = data.get("brandName") or {}
    return AsekoUnit(
        serial_number=serial,
        name=data.get("name") or serial,
        online=data.get("online", False),
        note=data.get("note"),
        brand=brand.get("primary"),
        brand_secondary=brand.get("secondary"),
        status_values=data.get("statusValues") or {},
        status_messages=data.get("statusMessages") or [],
    )
