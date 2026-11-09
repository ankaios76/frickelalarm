"""Alarm-Bedienfeld (alarm_control_panel) für Frickelalarm.

Phase 2 – Engine: Zustandsmaschine mit Ausgangsverzögerung (arming),
Eingangsverzögerung (pending) und echtem Auslösen (triggered) auf Basis der
je Modus ausgewählten Sensoren. Zustand übersteht Neustarts (RestoreEntity).
"""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
    AlarmControlPanelState,
    CodeFormat,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, STATE_ON
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
)
from homeassistant.helpers.restore_state import RestoreEntity
import homeassistant.util.dt as dt_util

from .const import (
    CONF_ALWAYS,
    CONF_CODE,
    CONF_CODE_ARM_REQUIRED,
    CONF_CODE_DISARM_REQUIRED,
    CONF_DELAYED,
    CONF_ENTITY_ID,
    CONF_ENTRY_DELAY,
    CONF_EXIT_DELAY,
    CONF_MODES,
    CONF_SENSORS,
    CONF_TRIGGER_DURATION,
    DEFAULT_ENTRY_DELAY,
    DEFAULT_EXIT_DELAY,
    DEFAULT_NAME,
    DEFAULT_TRIGGER_DURATION,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

_ARMED_STATES = {
    AlarmControlPanelState.ARMED_HOME,
    AlarmControlPanelState.ARMED_AWAY,
    AlarmControlPanelState.ARMED_NIGHT,
    AlarmControlPanelState.ARMED_VACATION,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Das Bedienfeld dieses Bereichs anlegen."""
    async_add_entities([FrickelalarmPanel(entry)])


class FrickelalarmPanel(AlarmControlPanelEntity, RestoreEntity):
    """Ein Alarmbereich als Bedienfeld inkl. Alarm-Engine."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_should_poll = False
    _attr_supported_features = (
        AlarmControlPanelEntityFeature.ARM_HOME
        | AlarmControlPanelEntityFeature.ARM_AWAY
        | AlarmControlPanelEntityFeature.ARM_NIGHT
        | AlarmControlPanelEntityFeature.ARM_VACATION
        | AlarmControlPanelEntityFeature.TRIGGER
    )

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = entry.entry_id
        self._attr_alarm_state = AlarmControlPanelState.DISARMED
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get(CONF_NAME, DEFAULT_NAME),
            manufacturer="Frickelfabrik",
            model="Alarmbereich",
        )
        # Engine-Laufzeitstatus
        self._arm_mode: AlarmControlPanelState | None = None
        self._reason: str | None = None
        self._timer_end = None
        self._cancel_arming = None
        self._cancel_pending = None
        self._cancel_trigger = None
        self._unsub_sensors = None

    # --- Konfiguration (aus Optionen) -------------------------------------
    @property
    def _sensors(self) -> list[dict[str, Any]]:
        return self._entry.options.get(CONF_SENSORS, []) or []

    @property
    def _exit_delay(self) -> int:
        return int(self._entry.options.get(CONF_EXIT_DELAY, DEFAULT_EXIT_DELAY))

    @property
    def _entry_delay(self) -> int:
        return int(self._entry.options.get(CONF_ENTRY_DELAY, DEFAULT_ENTRY_DELAY))

    @property
    def _trigger_duration(self) -> int:
        return int(
            self._entry.options.get(CONF_TRIGGER_DURATION, DEFAULT_TRIGGER_DURATION)
        )

    @property
    def _code(self) -> str:
        return str(self._entry.options.get(CONF_CODE, "") or "")

    @property
    def code_format(self) -> CodeFormat | None:
        if not self._code:
            return None
        return CodeFormat.NUMBER if self._code.isdigit() else CodeFormat.TEXT

    @property
    def code_arm_required(self) -> bool:
        return bool(self._code) and bool(
            self._entry.options.get(CONF_CODE_ARM_REQUIRED, False)
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {"konfigurierte_sensoren": len(self._sensors)}
        if self._reason:
            attrs["ausloeser"] = self._reason
        if self._timer_end is not None:
            remaining = (self._timer_end - dt_util.utcnow()).total_seconds()
            attrs["restzeit_s"] = max(0, int(remaining))
        offen = []
        for sensor in self._sensors:
            state = self.hass.states.get(sensor[CONF_ENTITY_ID])
            if state is not None and state.state == STATE_ON:
                offen.append(state.name or sensor[CONF_ENTITY_ID])
        attrs["offene_sensoren"] = offen
        return attrs

    # --- Lifecycle --------------------------------------------------------
    async def async_added_to_hass(self) -> None:
        """Letzten Zustand wiederherstellen und Sensoren beobachten."""
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) is not None:
            try:
                restored = AlarmControlPanelState(last.state)
            except ValueError:
                restored = AlarmControlPanelState.DISARMED
            # Flüchtige Zustände nicht wiederherstellen
            if restored in (
                AlarmControlPanelState.ARMING,
                AlarmControlPanelState.PENDING,
                AlarmControlPanelState.TRIGGERED,
            ):
                restored = AlarmControlPanelState.DISARMED
            self._attr_alarm_state = restored
            if restored in _ARMED_STATES:
                self._arm_mode = restored
        self._subscribe()

    async def async_will_remove_from_hass(self) -> None:
        self._clear_timers()
        if self._unsub_sensors is not None:
            self._unsub_sensors()
            self._unsub_sensors = None

    @callback
    def _subscribe(self) -> None:
        if self._unsub_sensors is not None:
            self._unsub_sensors()
            self._unsub_sensors = None
        entity_ids = [s[CONF_ENTITY_ID] for s in self._sensors]
        if entity_ids:
            self._unsub_sensors = async_track_state_change_event(
                self.hass, entity_ids, self._sensor_changed
            )

    # --- Timer-Verwaltung -------------------------------------------------
    @callback
    def _clear_timers(self) -> None:
        for cancel in (
            self._cancel_arming,
            self._cancel_pending,
            self._cancel_trigger,
        ):
            if cancel is not None:
                cancel()
        self._cancel_arming = None
        self._cancel_pending = None
        self._cancel_trigger = None
        self._timer_end = None

    @callback
    def _set(self, state: AlarmControlPanelState) -> None:
        self._attr_alarm_state = state
        self.async_write_ha_state()

    # --- Sensor-Logik -----------------------------------------------------
    @callback
    def _sensor_changed(self, event: Event[EventStateChangedData]) -> None:
        new_state = event.data["new_state"]
        old_state = event.data["old_state"]
        if new_state is None or new_state.state != STATE_ON:
            return
        if old_state is not None and old_state.state == STATE_ON:
            return  # war schon aktiv – keine neue Flanke

        entity_id = event.data["entity_id"]
        cfg = next(
            (s for s in self._sensors if s[CONF_ENTITY_ID] == entity_id), None
        )
        if cfg is None:
            return

        name = new_state.name or entity_id
        state = self._attr_alarm_state
        always = bool(cfg.get(CONF_ALWAYS, False))

        if state == AlarmControlPanelState.TRIGGERED:
            return

        # "Immer scharf" (z. B. Rauch/Sabotage) löst in jedem Zustand aus
        if always:
            self._trigger(name)
            return

        # Während Ausgangsverzögerung bewusst ignorieren (man verlässt gerade)
        if state in (
            AlarmControlPanelState.DISARMED,
            AlarmControlPanelState.ARMING,
        ):
            return

        # Nur Sensoren, die im aktuellen Modus scharf sind
        mode = self._arm_mode.value if self._arm_mode else None
        if mode not in cfg.get(CONF_MODES, []):
            return

        if state == AlarmControlPanelState.PENDING:
            # Läuft schon Eingangsverzögerung; Sofort-Sensor eskaliert direkt
            if not cfg.get(CONF_DELAYED, False):
                self._trigger(name)
            return

        # Scharf: verzögerter Sensor startet pending, sonst Sofortalarm
        if cfg.get(CONF_DELAYED, False) and self._entry_delay > 0:
            self._start_pending(name)
        else:
            self._trigger(name)

    # --- Zustandsübergänge ------------------------------------------------
    def _validate(self, code: str | None, required: bool) -> None:
        if not self._code or not required:
            return
        if str(code or "") != self._code:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="invalid_code"
            )

    async def _arm(self, target: AlarmControlPanelState, code: str | None) -> None:
        self._validate(code, self.code_arm_required)
        self._clear_timers()
        self._arm_mode = target
        self._reason = None
        if self._exit_delay > 0:
            self._set(AlarmControlPanelState.ARMING)
            self._timer_end = dt_util.utcnow() + timedelta(seconds=self._exit_delay)
            self._cancel_arming = async_call_later(
                self.hass, self._exit_delay, self._finish_arming
            )
        else:
            self._finish_arming_now()

    @callback
    def _finish_arming(self, _now) -> None:
        self._cancel_arming = None
        self._finish_arming_now()

    @callback
    def _finish_arming_now(self) -> None:
        self._timer_end = None
        if self._arm_mode is not None:
            self._set(self._arm_mode)

    @callback
    def _start_pending(self, reason: str) -> None:
        self._reason = reason
        self._timer_end = dt_util.utcnow() + timedelta(seconds=self._entry_delay)
        self._cancel_pending = async_call_later(
            self.hass, self._entry_delay, self._pending_elapsed
        )
        self._set(AlarmControlPanelState.PENDING)

    @callback
    def _pending_elapsed(self, _now) -> None:
        self._cancel_pending = None
        self._trigger(self._reason or "Sensor")

    @callback
    def _trigger(self, reason: str) -> None:
        self._clear_timers()
        self._reason = reason
        _LOGGER.info("Frickelalarm '%s' ausgelöst durch: %s", self.name, reason)
        if self._trigger_duration > 0:
            self._timer_end = dt_util.utcnow() + timedelta(
                seconds=self._trigger_duration
            )
            self._cancel_trigger = async_call_later(
                self.hass, self._trigger_duration, self._trigger_elapsed
            )
        self._set(AlarmControlPanelState.TRIGGERED)

    @callback
    def _trigger_elapsed(self, _now) -> None:
        self._cancel_trigger = None
        self._timer_end = None
        # Nach Ablauf der Alarmdauer in den vorherigen Modus zurück (wiederschärfen)
        if self._arm_mode is not None:
            self._set(self._arm_mode)
        else:
            self._set(AlarmControlPanelState.DISARMED)

    # --- Dienste des Bedienfelds -----------------------------------------
    async def async_alarm_disarm(self, code: str | None = None) -> None:
        self._validate(
            code, bool(self._entry.options.get(CONF_CODE_DISARM_REQUIRED, False))
        )
        self._clear_timers()
        self._arm_mode = None
        self._reason = None
        self._set(AlarmControlPanelState.DISARMED)

    async def async_alarm_arm_home(self, code: str | None = None) -> None:
        await self._arm(AlarmControlPanelState.ARMED_HOME, code)

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        await self._arm(AlarmControlPanelState.ARMED_AWAY, code)

    async def async_alarm_arm_night(self, code: str | None = None) -> None:
        await self._arm(AlarmControlPanelState.ARMED_NIGHT, code)

    async def async_alarm_arm_vacation(self, code: str | None = None) -> None:
        await self._arm(AlarmControlPanelState.ARMED_VACATION, code)

    async def async_alarm_trigger(self, code: str | None = None) -> None:
        self._trigger("manuell ausgelöst")
