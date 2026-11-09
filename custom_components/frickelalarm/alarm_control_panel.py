"""Alarm-Bedienfeld (alarm_control_panel) für Frickelalarm.

Phase 2 – Engine: Zustandsmaschine mit Ausgangsverzögerung (arming),
Eingangsverzögerung (pending) und echtem Auslösen (triggered) auf Basis der
je Modus ausgewählten Sensoren. Zustand übersteht Neustarts (RestoreEntity).
"""

from __future__ import annotations

import dataclasses
from datetime import timedelta
import logging
from typing import Any

import voluptuous as vol

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
    AlarmControlPanelState,
    CodeFormat,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_NAME,
    STATE_HOME,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import (
    Event,
    EventStateChangedData,
    HomeAssistant,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_change,
)
from homeassistant.helpers.restore_state import ExtraStoredData, RestoreEntity
from homeassistant.helpers.template import Template
import homeassistant.util.dt as dt_util

from .const import (
    ARM_MODES,
    CONF_ALWAYS,
    CONF_AUTO_ARM,
    CONF_AUTO_ARM_DELAY,
    CONF_AUTO_ARM_MODE,
    CONF_AUTO_DISARM,
    CONF_AUTO_DISARM_DURING_ALARM,
    CONF_CODE,
    CONF_CODE_ARM_REQUIRED,
    CONF_CODE_DISARM_REQUIRED,
    CONF_DELAYED,
    CONF_ENTITY_ID,
    CONF_ENTRY_DELAY,
    CONF_EXIT_DELAY,
    CONF_MODES,
    CONF_NIGHT_END,
    CONF_NIGHT_REQUIRE_HOME,
    CONF_NIGHT_SCHEDULE,
    CONF_NIGHT_START,
    CONF_OPEN_ON_ARM,
    CONF_NOTIFY_EVENTS,
    CONF_NOTIFY_MESSAGE,
    CONF_NOTIFY_SERVICE,
    CONF_PRESENCE,
    CONF_SENSORS,
    CONF_SIRENS,
    CONF_TAMPER,
    CONF_TAMPER_TRIGGERS,
    CONF_TRIGGER_DURATION,
    DEFAULT_AUTO_ARM_DELAY,
    DEFAULT_AUTO_ARM_MODE,
    DEFAULT_AUTO_DISARM_DURING_ALARM,
    DEFAULT_OPEN_ON_ARM,
    DEFAULT_TAMPER,
    DEFAULT_TAMPER_TRIGGERS,
    DEFAULT_ENTRY_DELAY,
    DEFAULT_EXIT_DELAY,
    DEFAULT_NAME,
    DEFAULT_NIGHT_END,
    DEFAULT_NIGHT_START,
    DEFAULT_NOTIFY_MESSAGE,
    DEFAULT_TRIGGER_DURATION,
    DOMAIN,
    NOTIFY_EVENTS,
    SAFE_DEFAULT_MODES,
    SIGNAL_OPTIONS_UPDATED,
)

_LOGGER = logging.getLogger(__name__)

_ARMED_STATES = {
    AlarmControlPanelState.ARMED_HOME,
    AlarmControlPanelState.ARMED_AWAY,
    AlarmControlPanelState.ARMED_NIGHT,
    AlarmControlPanelState.ARMED_VACATION,
}

_UNAVAILABLE_STATES = (STATE_UNAVAILABLE, STATE_UNKNOWN)


@dataclasses.dataclass
class FrickelalarmExtraData(ExtraStoredData):
    """Laufzeitstatus, der einen Neustart übersteht (ergänzt den Entitätszustand)."""

    arm_mode: str | None = None
    reason: str | None = None
    timer_end: float | None = None  # Unix-Zeit, wann der laufende Timer abläuft
    night_active: bool = False
    bypassed: list[str] = dataclasses.field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FrickelalarmExtraData":
        return cls(
            arm_mode=data.get("arm_mode"),
            reason=data.get("reason"),
            timer_end=data.get("timer_end"),
            night_active=bool(data.get("night_active", False)),
            bypassed=list(data.get("bypassed") or []),
        )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Das Bedienfeld dieses Bereichs anlegen und Dienste registrieren."""
    async_add_entities([FrickelalarmPanel(entry)])

    # Dienste nur einmal registrieren (mehrere Bereiche = mehrere Einträge)
    if not hass.services.has_service(DOMAIN, "bypass"):
        platform = entity_platform.async_get_current_platform()
        platform.async_register_entity_service(
            "bypass",
            {vol.Required("sensors"): vol.All(cv.ensure_list, [cv.entity_id])},
            "async_bypass",
        )
        platform.async_register_entity_service(
            "clear_bypass",
            {vol.Optional("sensors"): vol.All(cv.ensure_list, [cv.entity_id])},
            "async_clear_bypass",
        )
        # Konfiguration per Dienst (für UI-Automationen und LLM/MCP-Zugriff)
        platform.async_register_entity_service(
            "add_sensor",
            {
                vol.Required("sensor"): cv.entity_id,
                vol.Optional("modes"): vol.All(cv.ensure_list, [vol.In(ARM_MODES)]),
                vol.Optional("delayed"): cv.boolean,
                vol.Optional("always"): cv.boolean,
            },
            "async_add_sensor",
        )
        platform.async_register_entity_service(
            "remove_sensor",
            {vol.Required("sensor"): cv.entity_id},
            "async_remove_sensor",
        )
        platform.async_register_entity_service(
            "set_times",
            {
                vol.Optional("exit_delay"): cv.positive_int,
                vol.Optional("entry_delay"): cv.positive_int,
                vol.Optional("trigger_duration"): cv.positive_int,
            },
            "async_set_times",
        )
        platform.async_register_entity_service(
            "set_reactions",
            {
                vol.Optional("sirens"): vol.All(cv.ensure_list, [cv.entity_id]),
                vol.Optional("notify_service"): cv.string,
                vol.Optional("notify_message"): cv.string,
                vol.Optional("notify_events"): vol.All(
                    cv.ensure_list, [vol.In(NOTIFY_EVENTS)]
                ),
            },
            "async_set_reactions",
        )
        platform.async_register_entity_service(
            "set_automation",
            {
                vol.Optional("auto_arm"): cv.boolean,
                vol.Optional("auto_disarm"): cv.boolean,
                vol.Optional("night_schedule"): cv.boolean,
            },
            "async_set_automation",
        )
        platform.async_register_entity_service(
            "get_config",
            None,
            "async_get_config",
            supports_response=SupportsResponse.ONLY,
        )
        # Quick-Wins
        platform.async_register_entity_service("panic", None, "async_panic")
        platform.async_register_entity_service("silence", None, "async_silence")
        platform.async_register_entity_service(
            "skip_exit_delay", None, "async_skip_exit_delay"
        )


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
        self._bypassed: set[str] = set()
        # Automatik-Laufzeitstatus
        self._unsub_presence = None
        self._unsub_time: list = []
        self._cancel_autoarm = None
        self._night_active = False

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

    # --- Automatik-Optionen ----------------------------------------------
    @property
    def _presence(self) -> list[str]:
        return self._entry.options.get(CONF_PRESENCE) or []

    @property
    def _auto_arm(self) -> bool:
        return bool(self._entry.options.get(CONF_AUTO_ARM, False))

    @property
    def _auto_disarm(self) -> bool:
        return bool(self._entry.options.get(CONF_AUTO_DISARM, False))

    @property
    def _auto_arm_mode(self) -> str:
        return self._entry.options.get(CONF_AUTO_ARM_MODE, DEFAULT_AUTO_ARM_MODE)

    @property
    def _auto_arm_delay(self) -> int:
        return int(self._entry.options.get(CONF_AUTO_ARM_DELAY, DEFAULT_AUTO_ARM_DELAY))

    @property
    def _night_schedule(self) -> bool:
        return bool(self._entry.options.get(CONF_NIGHT_SCHEDULE, False))

    @property
    def _tamper_enabled(self) -> bool:
        return bool(self._entry.options.get(CONF_TAMPER, DEFAULT_TAMPER))

    @property
    def _open_on_arm(self) -> str:
        return self._entry.options.get(CONF_OPEN_ON_ARM, DEFAULT_OPEN_ON_ARM)

    def _entity_label(self, entity_id: str) -> str:
        state = self.hass.states.get(entity_id)
        return state.name if state is not None else entity_id

    def _entity_state(self, entity_id: str) -> str:
        state = self.hass.states.get(entity_id)
        return state.state if state is not None else "unbekannt"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {
            "modus": self._arm_mode.value if self._arm_mode else None,
            "konfigurierte_sensoren": len(self._sensors),
        }
        if self._reason:
            attrs["ausloeser"] = self._reason
        if self._timer_end is not None:
            remaining = (self._timer_end - dt_util.utcnow()).total_seconds()
            attrs["restzeit_s"] = max(0, int(remaining))

        # Sensor-Übersicht: alles an einem Ort, mit Live-Zustand
        offen: list[str] = []
        sensoren: list[dict[str, Any]] = []
        for sensor in self._sensors:
            eid = sensor[CONF_ENTITY_ID]
            raw = self._entity_state(eid)
            is_open = raw == STATE_ON
            if is_open:
                offen.append(self._entity_label(eid))
            sensoren.append(
                {
                    "name": self._entity_label(eid),
                    "entity_id": eid,
                    "zustand": raw,
                    "offen": is_open,
                    "modi": sensor.get(CONF_MODES, []),
                    "verzoegert": bool(sensor.get(CONF_DELAYED, False)),
                    "immer_scharf": bool(sensor.get(CONF_ALWAYS, False)),
                    "umgangen": eid in self._bypassed,
                }
            )
        attrs["offene_sensoren"] = offen
        attrs["sensoren"] = sensoren
        attrs["umgangene_sensoren"] = sorted(self._bypassed)

        # Aktoren-Übersicht (Sirene/Licht/Schalter) mit Live-Zustand
        aktoren = []
        for eid in self._entry.options.get(CONF_SIRENS) or []:
            aktoren.append(
                {
                    "name": self._entity_label(eid),
                    "entity_id": eid,
                    "zustand": self._entity_state(eid),
                }
            )
        attrs["aktoren"] = aktoren

        # Automatik-Status
        attrs["automatik"] = {
            "auto_scharf": self._auto_arm,
            "auto_unscharf": self._auto_disarm,
            "nachtplan": self._night_schedule,
            "personen_zuhause": self._someone_home(),
        }
        return attrs

    # --- Lifecycle --------------------------------------------------------
    @property
    def extra_restore_state_data(self) -> FrickelalarmExtraData:
        """Laufzeitstatus sichern, damit ein Neustart den Alarm nicht verliert (#1b/#3)."""
        return FrickelalarmExtraData(
            arm_mode=self._arm_mode.value if self._arm_mode else None,
            reason=self._reason,
            timer_end=self._timer_end.timestamp() if self._timer_end else None,
            night_active=self._night_active,
            bypassed=sorted(self._bypassed),
        )

    async def async_added_to_hass(self) -> None:
        """Letzten Zustand (inkl. laufendem Alarm) wiederherstellen und Verdrahtung aufsetzen."""
        await super().async_added_to_hass()

        last = await self.async_get_last_state()
        data: FrickelalarmExtraData | None = None
        if (extra := await self.async_get_last_extra_data()) is not None:
            try:
                data = FrickelalarmExtraData.from_dict(extra.as_dict())
            except Exception:  # noqa: BLE001 - defekte Restore-Daten nie fatal
                data = None
        if last is not None:
            self._restore(last.state, data)

        self._subscribe()
        self._setup_automation()
        # Optionen-Änderung: live aktualisieren statt Reload (laufender Alarm bleibt erhalten)
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_OPTIONS_UPDATED.format(self._entry.entry_id),
                self._on_options_updated,
            )
        )

    @callback
    def _on_options_updated(self) -> None:
        self._subscribe()
        self._setup_automation()
        self.async_write_ha_state()

    @callback
    def _restore(self, state_str: str, data: FrickelalarmExtraData | None) -> None:
        """Zustand nach Neustart fortsetzen – auch arming/pending/triggered."""
        try:
            state = AlarmControlPanelState(state_str)
        except ValueError:
            state = AlarmControlPanelState.DISARMED

        if data is not None:
            if data.arm_mode:
                try:
                    self._arm_mode = AlarmControlPanelState(data.arm_mode)
                except ValueError:
                    self._arm_mode = None
            self._reason = data.reason
            self._night_active = bool(data.night_active)
            self._bypassed = set(data.bypassed or [])

        now = dt_util.utcnow().timestamp()
        remaining = (
            max(0, int(data.timer_end - now)) if (data and data.timer_end) else 0
        )

        if state == AlarmControlPanelState.ARMING:
            target = self._arm_mode or AlarmControlPanelState.ARMED_AWAY
            self._arm_mode = target
            if remaining > 0:
                self._begin_arming(remaining)
            else:
                self._finish_arming_now()
        elif state == AlarmControlPanelState.PENDING:
            if remaining > 0:
                self._begin_pending(remaining, self._reason or "Sensor")
            else:
                self._trigger(self._reason or "Sensor")
        elif state == AlarmControlPanelState.TRIGGERED:
            # Alarm nach Neustart fortsetzen (Rest-Alarmdauer bzw. volle Dauer)
            self._trigger(self._reason or "Alarm", duration=remaining or None)
        elif state in _ARMED_STATES:
            self._arm_mode = state
            self._attr_alarm_state = state
        else:
            self._attr_alarm_state = AlarmControlPanelState.DISARMED

    async def async_will_remove_from_hass(self) -> None:
        self._clear_timers()
        if self._unsub_sensors is not None:
            self._unsub_sensors()
            self._unsub_sensors = None
        self._teardown_automation()

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

    # --- Automatik (Phase 8) ---------------------------------------------
    @staticmethod
    def _parse_time(value: str) -> tuple[int, int, int] | None:
        try:
            parts = [int(x) for x in str(value).split(":")]
            while len(parts) < 3:
                parts.append(0)
            return parts[0], parts[1], parts[2]
        except (ValueError, TypeError):
            return None

    @callback
    def _mode_from_str(self, value: str) -> AlarmControlPanelState:
        try:
            return AlarmControlPanelState(value)
        except ValueError:
            return AlarmControlPanelState.ARMED_AWAY

    @callback
    def _someone_home(self) -> bool:
        if not getattr(self, "hass", None) or not self._presence:
            return False
        for eid in self._presence:
            st = self.hass.states.get(eid)
            if st is not None and st.state == STATE_HOME:
                return True
        return False

    @callback
    def _all_away(self) -> bool:
        if not self._presence:
            return False
        for eid in self._presence:
            st = self.hass.states.get(eid)
            if st is None or st.state in (STATE_HOME, "unknown", "unavailable", ""):
                return False
        return True

    @callback
    def _setup_automation(self) -> None:
        self._teardown_automation()
        if (self._auto_arm or self._auto_disarm) and self._presence:
            self._unsub_presence = async_track_state_change_event(
                self.hass, self._presence, self._presence_changed
            )
        if self._night_schedule:
            start = self._parse_time(
                self._entry.options.get(CONF_NIGHT_START, DEFAULT_NIGHT_START)
            )
            end = self._parse_time(
                self._entry.options.get(CONF_NIGHT_END, DEFAULT_NIGHT_END)
            )
            if start:
                self._unsub_time.append(
                    async_track_time_change(
                        self.hass, self._night_start,
                        hour=start[0], minute=start[1], second=start[2],
                    )
                )
            if end:
                self._unsub_time.append(
                    async_track_time_change(
                        self.hass, self._night_end,
                        hour=end[0], minute=end[1], second=end[2],
                    )
                )

    @callback
    def _teardown_automation(self) -> None:
        if self._unsub_presence is not None:
            self._unsub_presence()
            self._unsub_presence = None
        for unsub in self._unsub_time:
            unsub()
        self._unsub_time = []
        if self._cancel_autoarm is not None:
            self._cancel_autoarm()
            self._cancel_autoarm = None

    @callback
    def _presence_changed(self, event: Event[EventStateChangedData]) -> None:
        new = event.data["new_state"]
        old = event.data["old_state"]
        arrived = (
            new is not None
            and new.state == STATE_HOME
            and (old is None or old.state != STATE_HOME)
        )

        # Heimkehr: geplantes Auto-Scharf abbrechen
        if new is not None and new.state == STATE_HOME and self._cancel_autoarm is not None:
            self._cancel_autoarm()
            self._cancel_autoarm = None

        # Heimkehr: Auto-Unscharf. Standardmäßig NICHT während eines laufenden Alarms
        # (ein GPS-Ausreißer soll keinen Alarm entschärfen, #9).
        if arrived and self._auto_disarm:
            state = self._attr_alarm_state
            during_alarm = state == AlarmControlPanelState.TRIGGERED
            allow_during_alarm = bool(
                self._entry.options.get(CONF_AUTO_DISARM_DURING_ALARM, False)
            )
            if state != AlarmControlPanelState.DISARMED and (
                not during_alarm or allow_during_alarm
            ):
                label = (new.name or "jemand") if new else "jemand"
                _LOGGER.info("Frickelalarm: Auto-unscharf (Heimkehr: %s)", label)
                self._disarm_internal()
                return

        # Alle weg: Auto-Scharf nach Verzögerung planen
        if (
            self._auto_arm
            and self._attr_alarm_state == AlarmControlPanelState.DISARMED
            and self._all_away()
            and self._cancel_autoarm is None
        ):
            if self._auto_arm_delay > 0:
                self._cancel_autoarm = async_call_later(
                    self.hass, self._auto_arm_delay, self._autoarm_elapsed
                )
            else:
                self._autoarm_elapsed(None)

    @callback
    def _autoarm_elapsed(self, _now) -> None:
        self._cancel_autoarm = None
        if (
            self._auto_arm
            and self._attr_alarm_state == AlarmControlPanelState.DISARMED
            and self._all_away()
        ):
            _LOGGER.info("Frickelalarm: Auto-scharf (alle abwesend)")
            self._arm_now(self._mode_from_str(self._auto_arm_mode))

    @callback
    def _night_start(self, _now) -> None:
        if not self._night_schedule:
            return
        require_home = bool(self._entry.options.get(CONF_NIGHT_REQUIRE_HOME, False))
        if require_home and not self._someone_home():
            return
        if self._attr_alarm_state == AlarmControlPanelState.DISARMED:
            _LOGGER.info("Frickelalarm: Nachtmodus (Zeitplan)")
            self._night_active = True
            self._arm_now(AlarmControlPanelState.ARMED_NIGHT)

    @callback
    def _night_end(self, _now) -> None:
        if self._night_active and self._attr_alarm_state == AlarmControlPanelState.ARMED_NIGHT:
            _LOGGER.info("Frickelalarm: Nachtmodus beendet (Zeitplan)")
            self._disarm_internal()
        self._night_active = False

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
        old = self._attr_alarm_state
        self._attr_alarm_state = state
        self.async_write_ha_state()
        if state != old:
            self._fire_event(state)
            self._run_reactions(old, state)

    @callback
    def _fire_event(self, state: AlarmControlPanelState) -> None:
        """Ereignis für Logbuch/Automationen feuern, z. B. frickelalarm_triggered."""
        if state in _ARMED_STATES:
            key = "armed"
        elif state == AlarmControlPanelState.ARMING:
            key = "arming"
        elif state == AlarmControlPanelState.PENDING:
            key = "pending"
        elif state == AlarmControlPanelState.TRIGGERED:
            key = "triggered"
        elif state == AlarmControlPanelState.DISARMED:
            key = "disarmed"
        else:
            return
        self.hass.bus.async_fire(
            f"{DOMAIN}_{key}",
            {
                "entity_id": self.entity_id,
                "name": self._entry.data.get(CONF_NAME, DEFAULT_NAME),
                "mode": self._arm_mode.value if self._arm_mode else None,
                "reason": self._reason or None,
            },
        )

    # --- Reaktionen (Phase 3) --------------------------------------------
    @callback
    def _event_key(self, state: AlarmControlPanelState) -> str | None:
        if state == AlarmControlPanelState.TRIGGERED:
            return "triggered"
        if state == AlarmControlPanelState.PENDING:
            return "pending"
        if state in _ARMED_STATES:
            return "armed"
        if state == AlarmControlPanelState.DISARMED:
            return "disarmed"
        return None  # arming -> keine Reaktion

    @callback
    def _run_reactions(
        self, old: AlarmControlPanelState, new: AlarmControlPanelState
    ) -> None:
        sirens = self._entry.options.get(CONF_SIRENS) or []
        triggered = AlarmControlPanelState.TRIGGERED

        # Aktoren bei Alarm einschalten, beim Verlassen von "triggered" ausschalten
        if sirens:
            if new == triggered and old != triggered:
                self.hass.async_create_task(
                    self.hass.services.async_call(
                        "homeassistant", "turn_on", {"entity_id": sirens}, blocking=False
                    )
                )
            elif old == triggered and new != triggered:
                self.hass.async_create_task(
                    self.hass.services.async_call(
                        "homeassistant", "turn_off", {"entity_id": sirens}, blocking=False
                    )
                )

        # Benachrichtigung je nach Ereignis
        service = str(self._entry.options.get(CONF_NOTIFY_SERVICE, "") or "").strip()
        if not service:
            return
        events = self._entry.options.get(CONF_NOTIFY_EVENTS) or ["triggered"]
        event_key = self._event_key(new)
        if event_key is None or event_key not in events:
            return
        self._notify(service, event_key)

    @callback
    def _send_notification(self, service: str, message: str) -> None:
        """Eine Benachrichtigung über den konfigurierten Dienst verschicken."""
        name = self._entry.data.get(CONF_NAME, DEFAULT_NAME)
        domain, _, svc = service.partition(".")
        if not domain or not svc:
            return
        data = {"message": message, "title": f"Frickelalarm: {name}"}
        self.hass.async_create_task(
            self.hass.services.async_call(domain, svc, data, blocking=False)
        )

    @callback
    def _notify(self, service: str, event_key: str) -> None:
        name = self._entry.data.get(CONF_NAME, DEFAULT_NAME)
        tmpl = str(
            self._entry.options.get(CONF_NOTIFY_MESSAGE, "") or DEFAULT_NOTIFY_MESSAGE
        )
        variables = {"name": name, "reason": self._reason or "", "event": event_key}
        try:
            message = Template(tmpl, self.hass).async_render(
                variables, parse_result=False
            )
        except Exception:  # noqa: BLE001 - Vorlage soll nie den Alarm blockieren
            _LOGGER.warning("Frickelalarm: Nachrichtenvorlage fehlerhaft", exc_info=True)
            message = tmpl
        self._send_notification(service, message)

    @callback
    def _tamper(self, sensor_name: str) -> None:
        """Sabotage/Signalverlust: Sensor ist unerreichbar geworden."""
        _LOGGER.warning("Frickelalarm: Sensor nicht erreichbar: %s", sensor_name)
        self.hass.bus.async_fire(
            f"{DOMAIN}_tamper",
            {
                "entity_id": self.entity_id,
                "name": self._entry.data.get(CONF_NAME, DEFAULT_NAME),
                "sensor": sensor_name,
            },
        )
        self._report(f"Sabotage/Signalverlust: {sensor_name} ist nicht erreichbar")
        # Optional: Sabotage löst den Alarm aus (#4)
        if (
            self._entry.options.get(CONF_TAMPER_TRIGGERS, DEFAULT_TAMPER_TRIGGERS)
            and self._attr_alarm_state != AlarmControlPanelState.TRIGGERED
        ):
            self._trigger(f"Sabotage: {sensor_name}")

    # --- Sensor-Logik -----------------------------------------------------
    @callback
    def _sensor_changed(self, event: Event[EventStateChangedData]) -> None:
        entity_id = event.data["entity_id"]
        new_state = event.data["new_state"]
        old_state = event.data["old_state"]
        cfg = next(
            (s for s in self._sensors if s[CONF_ENTITY_ID] == entity_id), None
        )
        if cfg is None:
            return

        # Sabotage/Signalverlust: erreichbar -> unerreichbar, während scharf
        if (
            self._tamper_enabled
            and self._attr_alarm_state != AlarmControlPanelState.DISARMED
        ):
            was_avail = old_state is not None and old_state.state not in (
                STATE_UNAVAILABLE,
                STATE_UNKNOWN,
            )
            now_unavail = new_state is None or new_state.state in (
                STATE_UNAVAILABLE,
                STATE_UNKNOWN,
            )
            if was_avail and now_unavail:
                self._tamper(
                    old_state.name if old_state and old_state.name else entity_id
                )

        # Auto-Re-Monitor: umgangener Sensor wieder geschlossen -> Umgehung aufheben
        if (
            new_state is not None
            and new_state.state == STATE_OFF
            and entity_id in self._bypassed
        ):
            self._bypassed.discard(entity_id)
            self.async_write_ha_state()

        if new_state is None or new_state.state != STATE_ON:
            return
        if old_state is not None and old_state.state == STATE_ON:
            return  # war schon aktiv – keine neue Flanke

        name = new_state.name or entity_id
        state = self._attr_alarm_state
        always = bool(cfg.get(CONF_ALWAYS, False))

        if state == AlarmControlPanelState.TRIGGERED:
            return

        # Umgangene (bypass) Sensoren ignorieren – außer "immer scharf" (Sicherheit)
        if entity_id in self._bypassed and not always:
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

    @callback
    def _open_active_sensors(self, target: AlarmControlPanelState) -> list[str]:
        """Im Zielmodus scharfe Sensoren, die gerade offen ODER unerreichbar sind."""
        mode = target.value
        open_ids: list[str] = []
        for cfg in self._sensors:
            if cfg.get(CONF_ALWAYS):
                continue
            if mode not in cfg.get(CONF_MODES, []):
                continue
            eid = cfg[CONF_ENTITY_ID]
            st = self.hass.states.get(eid)
            if st is None or st.state == STATE_ON or st.state in _UNAVAILABLE_STATES:
                open_ids.append(eid)
        return open_ids

    @callback
    def _report(self, message: str) -> None:
        """Hinweis über den Benachrichtigungsdienst senden, falls konfiguriert."""
        service = str(self._entry.options.get(CONF_NOTIFY_SERVICE, "") or "").strip()
        if service:
            self._send_notification(service, message)

    async def _arm(self, target: AlarmControlPanelState, code: str | None) -> None:
        self._validate(code, self.code_arm_required)

        # Offene/unerreichbare Sensoren beim Scharfschalten behandeln
        open_ids = self._open_active_sensors(target)
        if open_ids:
            names = ", ".join(self._entity_label(e) for e in open_ids)
            handling = self._open_on_arm
            if handling == "block":
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="sensors_open",
                    translation_placeholders={"sensors": names},
                )
            if handling == "bypass":
                for eid in open_ids:
                    self._bypassed.add(eid)
                self._report(f"Beim Scharfschalten umgangen (offen/unerreichbar): {names}")
            else:  # allow: trotzdem scharf, aber melden (#5)
                self._report(f"Hinweis – beim Scharfschalten offen/unerreichbar: {names}")

        self._clear_timers()
        self._arm_mode = target
        self._reason = None
        if self._exit_delay > 0:
            self._begin_arming(self._exit_delay)
        else:
            self._finish_arming_now()

    @callback
    def _begin_arming(self, seconds: int) -> None:
        self._timer_end = dt_util.utcnow() + timedelta(seconds=seconds)
        self._cancel_arming = async_call_later(self.hass, seconds, self._finish_arming)
        self._set(AlarmControlPanelState.ARMING)

    @callback
    def _finish_arming(self, _now) -> None:
        self._cancel_arming = None
        self._finish_arming_now()

    @callback
    def _finish_arming_now(self) -> None:
        self._timer_end = None
        if self._arm_mode is not None:
            self._set(self._arm_mode)
            self._check_active_open()

    @callback
    def _arm_now(self, target: AlarmControlPanelState) -> None:
        """Sofort scharf schalten (Automatik/Restore: ohne Ausgangsverzögerung/Code)."""
        self._clear_timers()
        self._arm_mode = target
        self._reason = None
        self._set(target)
        self._check_active_open()

    @callback
    def _check_active_open(self) -> None:
        """Nach dem Scharfschalten: ein bereits offener, scharfer Sensor löst aus (#5)."""
        if self._attr_alarm_state not in _ARMED_STATES:
            return
        mode = self._arm_mode.value if self._arm_mode else None
        for cfg in self._sensors:
            if cfg.get(CONF_ALWAYS) or cfg[CONF_ENTITY_ID] in self._bypassed:
                continue
            if mode not in cfg.get(CONF_MODES, []):
                continue
            st = self.hass.states.get(cfg[CONF_ENTITY_ID])
            if st is None or st.state != STATE_ON:
                continue
            name = st.name or cfg[CONF_ENTITY_ID]
            if cfg.get(CONF_DELAYED, False) and self._entry_delay > 0:
                self._start_pending(name)
            else:
                self._trigger(name)
            return

    @callback
    def _start_pending(self, reason: str) -> None:
        self._begin_pending(self._entry_delay, reason)

    @callback
    def _begin_pending(self, seconds: int, reason: str) -> None:
        self._reason = reason
        self._timer_end = dt_util.utcnow() + timedelta(seconds=seconds)
        self._cancel_pending = async_call_later(self.hass, seconds, self._pending_elapsed)
        self._set(AlarmControlPanelState.PENDING)

    @callback
    def _pending_elapsed(self, _now) -> None:
        self._cancel_pending = None
        self._trigger(self._reason or "Sensor")

    @callback
    def _trigger(self, reason: str, duration: int | None = None) -> None:
        self._clear_timers()
        self._reason = reason
        _LOGGER.info("Frickelalarm '%s' ausgelöst durch: %s", self.name, reason)
        dur = self._trigger_duration if duration is None else duration
        if dur > 0:
            self._timer_end = dt_util.utcnow() + timedelta(seconds=dur)
            self._cancel_trigger = async_call_later(self.hass, dur, self._trigger_elapsed)
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
        # Standard: gesetzter Code schützt auch das Unscharfschalten (#6)
        self._validate(
            code, bool(self._entry.options.get(CONF_CODE_DISARM_REQUIRED, True))
        )
        self._disarm_internal()

    @callback
    def _disarm_internal(self) -> None:
        """Unscharf schalten ohne Code-Prüfung (auch für Automatik)."""
        self._clear_timers()
        if self._cancel_autoarm is not None:
            self._cancel_autoarm()
            self._cancel_autoarm = None
        self._arm_mode = None
        self._reason = None
        self._bypassed.clear()
        self._night_active = False
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

    # --- Quick-Wins (Phase 9) --------------------------------------------
    async def async_panic(self) -> None:
        """Sofortiger Alarm, unabhängig vom Modus."""
        self._trigger("Panik ausgelöst")

    async def async_silence(self) -> None:
        """Sirene/Aktoren ausschalten – der Alarm läuft (still) weiter."""
        sirens = self._entry.options.get(CONF_SIRENS) or []
        if sirens and self._attr_alarm_state == AlarmControlPanelState.TRIGGERED:
            self.hass.async_create_task(
                self.hass.services.async_call(
                    "homeassistant", "turn_off", {"entity_id": sirens}, blocking=False
                )
            )

    async def async_skip_exit_delay(self) -> None:
        """Laufende Ausgangsverzögerung sofort beenden (jetzt scharf)."""
        if self._attr_alarm_state == AlarmControlPanelState.ARMING:
            if self._cancel_arming is not None:
                self._cancel_arming()
                self._cancel_arming = None
            self._finish_arming_now()

    # --- Komfort-Dienste (Phase 4) ---------------------------------------
    async def async_bypass(self, sensors: list[str]) -> None:
        """Sensoren temporär ausklammern (bis zum Unscharfschalten)."""
        valid = {s[CONF_ENTITY_ID] for s in self._sensors}
        for eid in sensors:
            if eid in valid:
                self._bypassed.add(eid)
            else:
                _LOGGER.warning(
                    "Frickelalarm: %s ist kein konfigurierter Sensor, nicht umgangen",
                    eid,
                )
        self.async_write_ha_state()

    async def async_clear_bypass(self, sensors: list[str] | None = None) -> None:
        """Umgehung aufheben – für bestimmte Sensoren oder alle."""
        if sensors:
            for eid in sensors:
                self._bypassed.discard(eid)
        else:
            self._bypassed.clear()
        self.async_write_ha_state()

    # --- Konfiguration per Dienst (Phase 7, auch für LLM/MCP) -------------
    @callback
    def _update_options(self, changes: dict[str, Any]) -> None:
        """Optionen ändern; die Entität aktualisiert sich live (Listener → Dispatcher, kein Reload)."""
        new_options = {**self._entry.options, **changes}
        self.hass.config_entries.async_update_entry(self._entry, options=new_options)

    def _require_disarmed(self) -> None:
        """Konfig-Dienste nur im unscharfen Zustand zulassen (#2)."""
        if self._attr_alarm_state != AlarmControlPanelState.DISARMED:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="config_requires_disarmed"
            )

    async def async_add_sensor(
        self,
        sensor: str,
        modes: list[str] | None = None,
        delayed: bool = False,
        always: bool = False,
    ) -> None:
        """Einen Sensor hinzufügen oder (bei gleicher entity_id) aktualisieren."""
        self._require_disarmed()
        # Existenz + passende Domäne prüfen (#7)
        if (
            self.hass.states.get(sensor) is None
            or sensor.split(".")[0] not in ("binary_sensor", "input_boolean")
        ):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_sensor",
                translation_placeholders={"sensor": sensor},
            )
        sensors = [dict(s) for s in self._sensors if s[CONF_ENTITY_ID] != sensor]
        sensors.append(
            {
                CONF_ENTITY_ID: sensor,
                # ohne Angabe sichere Standard-Modi (nicht armed_home, #7)
                CONF_MODES: list(modes) if modes else list(SAFE_DEFAULT_MODES),
                CONF_DELAYED: bool(delayed),
                CONF_ALWAYS: bool(always),
            }
        )
        self._update_options({CONF_SENSORS: sensors})

    async def async_remove_sensor(self, sensor: str) -> None:
        """Einen Sensor entfernen."""
        self._require_disarmed()
        sensors = [s for s in self._sensors if s[CONF_ENTITY_ID] != sensor]
        self._update_options({CONF_SENSORS: sensors})

    async def async_set_times(
        self,
        exit_delay: int | None = None,
        entry_delay: int | None = None,
        trigger_duration: int | None = None,
    ) -> None:
        """Verzögerungen und Alarmdauer setzen (nur angegebene Werte)."""
        self._require_disarmed()
        changes: dict[str, Any] = {}
        if exit_delay is not None:
            changes[CONF_EXIT_DELAY] = int(exit_delay)
        if entry_delay is not None:
            changes[CONF_ENTRY_DELAY] = int(entry_delay)
        if trigger_duration is not None:
            changes[CONF_TRIGGER_DURATION] = int(trigger_duration)
        if changes:
            self._update_options(changes)

    async def async_set_reactions(
        self,
        sirens: list[str] | None = None,
        notify_service: str | None = None,
        notify_message: str | None = None,
        notify_events: list[str] | None = None,
    ) -> None:
        """Reaktionen setzen (nur angegebene Werte)."""
        self._require_disarmed()
        changes: dict[str, Any] = {}
        if sirens is not None:
            changes[CONF_SIRENS] = list(sirens)
        if notify_service is not None:
            changes[CONF_NOTIFY_SERVICE] = notify_service
        if notify_message is not None:
            changes[CONF_NOTIFY_MESSAGE] = notify_message
        if notify_events is not None:
            changes[CONF_NOTIFY_EVENTS] = list(notify_events)
        if changes:
            self._update_options(changes)

    async def async_set_automation(
        self,
        auto_arm: bool | None = None,
        auto_disarm: bool | None = None,
        night_schedule: bool | None = None,
    ) -> None:
        """Automatik-Schalter zur Laufzeit setzen (auch für LLM/MCP)."""
        self._require_disarmed()
        changes: dict[str, Any] = {}
        if auto_arm is not None:
            changes[CONF_AUTO_ARM] = auto_arm
        if auto_disarm is not None:
            changes[CONF_AUTO_DISARM] = auto_disarm
        if night_schedule is not None:
            changes[CONF_NIGHT_SCHEDULE] = night_schedule
        if changes:
            self._update_options(changes)

    async def async_get_config(self) -> ServiceResponse:
        """Aktuelle Konfiguration zurückgeben (für LLM/MCP und Automationen)."""
        o = self._entry.options
        return {
            "name": self._entry.data.get(CONF_NAME, DEFAULT_NAME),
            "state": self._attr_alarm_state.value if self._attr_alarm_state else None,
            "exit_delay": self._exit_delay,
            "entry_delay": self._entry_delay,
            "trigger_duration": self._trigger_duration,
            "code_set": bool(self._code),
            "tamper_detection": self._tamper_enabled,
            "tamper_triggers": bool(
                o.get(CONF_TAMPER_TRIGGERS, DEFAULT_TAMPER_TRIGGERS)
            ),
            "open_on_arm": self._open_on_arm,
            "sensors": self._sensors,
            "sirens": o.get(CONF_SIRENS) or [],
            "notify_service": o.get(CONF_NOTIFY_SERVICE, ""),
            "notify_events": o.get(CONF_NOTIFY_EVENTS) or [],
            "bypassed": sorted(self._bypassed),
            "automation": {
                "auto_arm": self._auto_arm,
                "auto_disarm": self._auto_disarm,
                "presence": self._presence,
                "auto_arm_mode": self._auto_arm_mode,
                "auto_arm_delay": self._auto_arm_delay,
                "night_schedule": self._night_schedule,
                "night_start": o.get(CONF_NIGHT_START, DEFAULT_NIGHT_START),
                "night_end": o.get(CONF_NIGHT_END, DEFAULT_NIGHT_END),
                "night_require_home": bool(o.get(CONF_NIGHT_REQUIRE_HOME, False)),
                "auto_disarm_during_alarm": bool(
                    o.get(CONF_AUTO_DISARM_DURING_ALARM, DEFAULT_AUTO_DISARM_DURING_ALARM)
                ),
            },
        }
