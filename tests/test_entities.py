"""Entity tests: which entities a unit gets and how they follow the account."""

from __future__ import annotations

from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.aseko_cloud.const import DOMAIN

from .conftest import make_entry, mock_units, unit_payload


async def _setup(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, units: list[dict]
) -> MockConfigEntry:
    mock_units(aioclient_mock, units)
    entry = make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _repoll(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    entry: MockConfigEntry,
    units: list[dict],
) -> None:
    aioclient_mock.clear_requests()
    mock_units(aioclient_mock, units)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()


def _device(hass: HomeAssistant, serial: str) -> dr.DeviceEntry | None:
    return next(
        (
            device
            for entry in hass.config_entries.async_entries(DOMAIN)
            for device in dr.async_entries_for_config_entry(
                dr.async_get(hass), entry.entry_id
            )
            if (DOMAIN, serial) in device.identifiers
        ),
        None,
    )


def _entity_id(hass: HomeAssistant, platform: str, unique_id: str) -> str | None:
    return er.async_get(hass).async_get_entity_id(platform, DOMAIN, unique_id)


def _state(hass: HomeAssistant, platform: str, unique_id: str) -> str:
    entity_id = _entity_id(hass, platform, unique_id)
    assert entity_id is not None, unique_id
    return hass.states.get(entity_id).state


async def test_only_reported_fields_get_entities(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A unit gets sensors only for the statusValues fields it reports."""
    await _setup(hass, aioclient_mock, [unit_payload()])

    assert _state(hass, "sensor", "SN1_water_temperature") == "25.0"
    assert _entity_id(hass, "sensor", "SN1_ph") is None
    assert _entity_id(hass, "sensor", "SN1_filtration_period_start") is None


async def test_filtration_period(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """The upcoming filtration period maps to start/end sensors and non-stop."""
    period = {"isNonstop": False, "isNext": True, "start": "10:00", "end": "12:00"}
    await _setup(
        hass,
        aioclient_mock,
        [unit_payload(statusValues={"upcomingFiltrationPeriod": period})],
    )

    assert _state(hass, "sensor", "SN1_filtration_period_start") == "10:00"
    assert _state(hass, "sensor", "SN1_filtration_period_end") == "12:00"
    assert _state(hass, "binary_sensor", "SN1_filtration_nonstop") == STATE_OFF


async def test_nonstop_filtration_has_no_start_or_end(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Non-stop filtration reports no start/end, so those are unknown."""
    period = {"isNonstop": True, "isNext": False}
    await _setup(
        hass,
        aioclient_mock,
        [unit_payload(statusValues={"upcomingFiltrationPeriod": period})],
    )

    assert _state(hass, "sensor", "SN1_filtration_period_start") == STATE_UNKNOWN
    assert _state(hass, "sensor", "SN1_filtration_period_end") == STATE_UNKNOWN
    assert _state(hass, "binary_sensor", "SN1_filtration_nonstop") == STATE_ON


async def test_enum_values(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Known enum values are lower-cased; an unknown one becomes unknown."""
    await _setup(
        hass,
        aioclient_mock,
        [unit_payload(statusValues={"mode": "PARTY", "poolFlow": "SIDEWAYS"})],
    )

    assert _state(hass, "sensor", "SN1_mode") == "party"
    assert _state(hass, "sensor", "SN1_pool_flow") == STATE_UNKNOWN


async def test_problem_exposes_message_detail(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """The problem sensor turns on for an ERROR and carries the message detail."""
    message = {
        "type": "BACKWASH_ERROR",
        "severity": "ERROR",
        "message": "Backwash error",
        "detail": "Check the backwash valve",
    }
    await _setup(hass, aioclient_mock, [unit_payload(statusMessages=[message])])

    entity_id = _entity_id(hass, "binary_sensor", "SN1_problem")
    state = hass.states.get(entity_id)
    assert state.state == STATE_ON
    assert state.attributes["messages"] == [message]


async def test_device_links_to_aseko_account(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Each unit is a device that links to the Aseko account portal."""
    await _setup(hass, aioclient_mock, [unit_payload()])

    device = _device(hass, "SN1")
    assert device is not None
    assert device.configuration_url == "https://account.aseko.cloud/"


async def test_unit_paired_later_appears_without_reload(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A unit paired in the Aseko app gets its entities on the next poll."""
    entry = await _setup(hass, aioclient_mock, [unit_payload()])
    assert _entity_id(hass, "sensor", "SN2_water_temperature") is None

    await _repoll(hass, aioclient_mock, entry, [unit_payload(), unit_payload("SN2")])

    assert _state(hass, "sensor", "SN2_water_temperature") == "25.0"
    assert _device(hass, "SN2")


async def test_metric_reported_later_appears_without_reload(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A field the unit starts reporting later gets its entity on the next poll."""
    entry = await _setup(hass, aioclient_mock, [unit_payload()])

    await _repoll(
        hass,
        aioclient_mock,
        entry,
        [unit_payload(statusValues={"waterTemperature": 25.0, "ph": 7.2})],
    )

    assert _state(hass, "sensor", "SN1_ph") == "7.2"


async def test_unpaired_unit_is_removed_and_can_return(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Unpairing removes the device and entities; re-pairing brings them back."""
    entry = await _setup(hass, aioclient_mock, [unit_payload(), unit_payload("SN2")])

    await _repoll(hass, aioclient_mock, entry, [unit_payload()])

    assert _device(hass, "SN2") is None
    assert _entity_id(hass, "sensor", "SN2_water_temperature") is None
    assert _device(hass, "SN1")

    await _repoll(hass, aioclient_mock, entry, [unit_payload(), unit_payload("SN2")])

    assert _state(hass, "sensor", "SN2_water_temperature") == "25.0"


async def test_failed_poll_keeps_devices(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """A failed poll must not be mistaken for every unit being unpaired."""
    entry = await _setup(hass, aioclient_mock, [unit_payload()])

    aioclient_mock.clear_requests()
    aioclient_mock.get(
        "https://api.aseko.cloud/api/v1/paired-units", exc=TimeoutError
    )
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert _device(hass, "SN1")
    assert _state(hass, "sensor", "SN1_water_temperature") == "unavailable"


async def test_empty_listing_keeps_devices(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """An empty unit listing must not be mistaken for every unit being unpaired."""
    entry = await _setup(hass, aioclient_mock, [unit_payload()])

    await _repoll(hass, aioclient_mock, entry, [])

    assert _device(hass, "SN1")
    assert _state(hass, "sensor", "SN1_water_temperature") == "unavailable"


async def test_unit_photo(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    hass_client: ClientSessionGenerator,
) -> None:
    """A unit of a family with a photo shows it, served by Home Assistant."""
    await _setup(
        hass,
        aioclient_mock,
        [unit_payload(brandName={"primary": "ASIN AQUA", "secondary": "Net+"})],
    )

    client = await hass_client()
    response = await client.get(
        hass.states.get(_entity_id(hass, "image", "SN1_photo")).attributes[
            "entity_picture"
        ]
    )
    assert response.status == 200
    assert response.content_type == "image/webp"
    assert await response.read()


async def test_unit_without_photo(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """Units of a family without a photo, or with no family yet, show none."""
    await _setup(
        hass,
        aioclient_mock,
        [
            unit_payload("SN1", brandName={"primary": "COVREX", "secondary": "Dosing"}),
            unit_payload("SN2"),
        ],
    )

    for serial in ("SN1", "SN2"):
        state = hass.states.get(_entity_id(hass, "image", f"{serial}_photo"))
        assert "entity_picture" not in state.attributes


async def test_unit_photo_follows_family(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    hass_client: ClientSessionGenerator,
) -> None:
    """The photo appears once a unit reports a family that has one."""
    entry = await _setup(hass, aioclient_mock, [unit_payload()])
    entity_id = _entity_id(hass, "image", "SN1_photo")

    await _repoll(
        hass,
        aioclient_mock,
        entry,
        [unit_payload(brandName={"primary": "ASIN AQUA", "secondary": "Pro"})],
    )

    client = await hass_client()
    response = await client.get(hass.states.get(entity_id).attributes["entity_picture"])
    assert response.status == 200
