"""Tests für die Alarm-Engine (Zustandsmaschine, Bypass, Events)."""

from datetime import timedelta

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
import homeassistant.util.dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.frickelalarm.const import (
    CONF_ALWAYS,
    CONF_CODE,
    CONF_CODE_ARM_REQUIRED,
    CONF_DELAYED,
    CONF_ENTITY_ID,
    CONF_ENTRY_DELAY,
    CONF_EXIT_DELAY,
    CONF_MODES,
    CONF_SENSORS,
    CONF_TRIGGER_DURATION,
    DOMAIN,
)

MODES = ["armed_home", "armed_away", "armed_night", "armed_vacation"]


def _opts(**over):
    o = dict(
        code="",
        code_arm_required=False,
        code_disarm_required=False,
        exit_delay=0,
        entry_delay=0,
        trigger_duration=0,
        sensors=[],
    )
    o.update(over)
    return o


def _sensor(entity_id, *, delayed=False, always=False, modes=MODES):
    return {
        CONF_ENTITY_ID: entity_id,
        CONF_MODES: modes,
        CONF_DELAYED: delayed,
        CONF_ALWAYS: always,
    }


async def _setup(hass: HomeAssistant, options):
    entry = MockConfigEntry(
        domain=DOMAIN, title="Test", data={"name": "Test"}, options=options, unique_id="t"
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    reg = er.async_get(hass)
    eid = next(
        e.entity_id
        for e in reg.entities.values()
        if e.config_entry_id == entry.entry_id
    )
    return entry, eid


async def _call(hass, domain, service, data):
    await hass.services.async_call(domain, service, data, blocking=True)
    await hass.async_block_till_done()


def _state(hass, eid):
    return hass.states.get(eid).state


async def test_immediate_sensor_triggers(hass: HomeAssistant) -> None:
    hass.states.async_set("binary_sensor.motion", "off")
    _, eid = await _setup(hass, _opts(sensors=[_sensor("binary_sensor.motion")]))
    await _call(hass, "alarm_control_panel", "alarm_arm_away", {"entity_id": eid})
    assert _state(hass, eid) == "armed_away"
    hass.states.async_set("binary_sensor.motion", "on")
    await hass.async_block_till_done()
    assert _state(hass, eid) == "triggered"


async def test_exit_and_entry_delay(hass: HomeAssistant) -> None:
    hass.states.async_set("binary_sensor.door", "off")
    _, eid = await _setup(
        hass,
        _opts(
            exit_delay=30,
            entry_delay=30,
            sensors=[_sensor("binary_sensor.door", delayed=True)],
        ),
    )
    await _call(hass, "alarm_control_panel", "alarm_arm_away", {"entity_id": eid})
    assert _state(hass, eid) == "arming"

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=31))
    await hass.async_block_till_done()
    assert _state(hass, eid) == "armed_away"

    hass.states.async_set("binary_sensor.door", "on")
    await hass.async_block_till_done()
    assert _state(hass, eid) == "pending"

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=31))
    await hass.async_block_till_done()
    assert _state(hass, eid) == "triggered"


async def test_always_sensor_triggers_when_disarmed(hass: HomeAssistant) -> None:
    hass.states.async_set("binary_sensor.smoke", "off")
    _, eid = await _setup(
        hass, _opts(sensors=[_sensor("binary_sensor.smoke", always=True, modes=[])])
    )
    assert _state(hass, eid) == "disarmed"
    hass.states.async_set("binary_sensor.smoke", "on")
    await hass.async_block_till_done()
    assert _state(hass, eid) == "triggered"


async def test_mode_gating(hass: HomeAssistant) -> None:
    hass.states.async_set("binary_sensor.motion", "off")
    _, eid = await _setup(
        hass,
        _opts(sensors=[_sensor("binary_sensor.motion", modes=["armed_away"])]),
    )
    await _call(hass, "alarm_control_panel", "alarm_arm_night", {"entity_id": eid})
    assert _state(hass, eid) == "armed_night"
    hass.states.async_set("binary_sensor.motion", "on")
    await hass.async_block_till_done()
    # im Nachtmodus nicht scharf -> kein Alarm
    assert _state(hass, eid) == "armed_night"


async def test_bypass(hass: HomeAssistant) -> None:
    hass.states.async_set("binary_sensor.motion", "off")
    _, eid = await _setup(hass, _opts(sensors=[_sensor("binary_sensor.motion")]))
    await _call(hass, "alarm_control_panel", "alarm_arm_away", {"entity_id": eid})
    await _call(
        hass, DOMAIN, "bypass", {"entity_id": eid, "sensors": ["binary_sensor.motion"]}
    )
    hass.states.async_set("binary_sensor.motion", "on")
    await hass.async_block_till_done()
    assert _state(hass, eid) == "armed_away"  # umgangen

    await _call(hass, "alarm_control_panel", "alarm_disarm", {"entity_id": eid})
    assert _state(hass, eid) == "disarmed"
    # Bypass nach Unscharfschalten aufgehoben
    await _call(hass, "alarm_control_panel", "alarm_arm_away", {"entity_id": eid})
    hass.states.async_set("binary_sensor.motion", "off")
    await hass.async_block_till_done()
    hass.states.async_set("binary_sensor.motion", "on")
    await hass.async_block_till_done()
    assert _state(hass, eid) == "triggered"


async def test_event_fired_with_reason(hass: HomeAssistant) -> None:
    events = []
    hass.bus.async_listen("frickelalarm_triggered", lambda e: events.append(e))
    hass.states.async_set("binary_sensor.motion", "off")
    _, eid = await _setup(hass, _opts(sensors=[_sensor("binary_sensor.motion")]))
    await _call(hass, "alarm_control_panel", "alarm_arm_away", {"entity_id": eid})
    hass.states.async_set("binary_sensor.motion", "on")
    await hass.async_block_till_done()
    assert len(events) == 1
    assert events[0].data["reason"]
    assert events[0].data["mode"] == "armed_away"


async def test_config_services(hass: HomeAssistant) -> None:
    hass.states.async_set("binary_sensor.motion", "off")
    entry, eid = await _setup(hass, _opts())

    # get_config liefert den aktuellen Stand
    resp = await hass.services.async_call(
        DOMAIN, "get_config", {"entity_id": eid}, blocking=True, return_response=True
    )
    assert resp[eid]["sensors"] == []
    assert resp[eid]["exit_delay"] == 0

    # add_sensor schreibt in die Optionen
    await _call(
        hass,
        DOMAIN,
        "add_sensor",
        {"entity_id": eid, "sensor": "binary_sensor.motion", "modes": ["armed_away"]},
    )
    assert any(s["entity_id"] == "binary_sensor.motion" for s in entry.options["sensors"])

    # set_times schreibt in die Optionen
    await _call(hass, DOMAIN, "set_times", {"entity_id": eid, "exit_delay": 0})
    assert entry.options["exit_delay"] == 0

    # der per Dienst hinzugefügte Sensor ist nach dem Reload wirklich aktiv
    await _call(hass, "alarm_control_panel", "alarm_arm_away", {"entity_id": eid})
    assert _state(hass, eid) == "armed_away"
    hass.states.async_set("binary_sensor.motion", "on")
    await hass.async_block_till_done()
    assert _state(hass, eid) == "triggered"

    await _call(hass, "alarm_control_panel", "alarm_disarm", {"entity_id": eid})
    await _call(
        hass, DOMAIN, "remove_sensor", {"entity_id": eid, "sensor": "binary_sensor.motion"}
    )
    assert entry.options["sensors"] == []


async def test_code_required_rejects_wrong_code(hass: HomeAssistant) -> None:
    _, eid = await _setup(
        hass, _opts(**{CONF_CODE: "1234", CONF_CODE_ARM_REQUIRED: True})
    )
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "alarm_control_panel",
            "alarm_arm_away",
            {"entity_id": eid, "code": "0000"},
            blocking=True,
        )
    assert _state(hass, eid) == "disarmed"
    await _call(
        hass,
        "alarm_control_panel",
        "alarm_arm_away",
        {"entity_id": eid, "code": "1234"},
    )
    assert _state(hass, eid) == "armed_away"
