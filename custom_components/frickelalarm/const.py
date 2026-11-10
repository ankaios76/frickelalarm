"""Konstanten für die Frickelalarm-Integration."""

from __future__ import annotations

DOMAIN = "frickelalarm"
PLATFORMS: list[str] = ["alarm_control_panel"]

DEFAULT_NAME = "Frickelalarm"

# Code-Optionen
CONF_CODE = "code"
CONF_CODE_ARM_REQUIRED = "code_arm_required"
CONF_CODE_DISARM_REQUIRED = "code_disarm_required"

# Sensoren / Engine
CONF_SENSORS = "sensors"          # Liste von Sensor-Dicts (siehe unten)
CONF_ENTITY_ID = "entity_id"
CONF_MODES = "modes"              # Liste der Modi, in denen der Sensor scharf ist
CONF_DELAYED = "delayed"          # nutzt die Eingangsverzögerung (verzögerter Sensor)
CONF_ALWAYS = "always"            # immer scharf, auch wenn unscharf (z. B. Rauch/Sabotage)

# Zeiten (Sekunden)
CONF_EXIT_DELAY = "exit_delay"
CONF_ENTRY_DELAY = "entry_delay"
CONF_TRIGGER_DURATION = "trigger_duration"

DEFAULT_EXIT_DELAY = 30
DEFAULT_ENTRY_DELAY = 30
DEFAULT_TRIGGER_DURATION = 120

# Die scharfen Modi (entsprechen AlarmControlPanelState-Werten)
ARM_MODES: list[str] = [
    "armed_home",
    "armed_away",
    "armed_night",
    "armed_vacation",
]

# Lesbare Labels für die Modus-Auswahl im Options-Flow
ARM_MODE_LABELS: dict[str, str] = {
    "armed_home": "Zuhause (armed_home)",
    "armed_away": "Abwesend (armed_away)",
    "armed_night": "Nacht (armed_night)",
    "armed_vacation": "Urlaub (armed_vacation)",
}

# Reaktionen (Phase 3)
CONF_SIRENS = "sirens"            # Aktoren (switch/siren/light), bei Alarm an, danach aus
CONF_NOTIFY_SERVICE = "notify_service"   # z. B. "notify.mobile_app_x" oder "persistent_notification.create"
CONF_NOTIFY_MESSAGE = "notify_message"   # Nachrichtentext (Jinja-Template, {{ name }} / {{ reason }})
CONF_NOTIFY_EVENTS = "notify_events"     # bei welchen Ereignissen benachrichtigt wird

DEFAULT_NOTIFY_MESSAGE = "Frickelalarm {{ name }}: {{ event }}{% if reason %} ({{ reason }}){% endif %}"

# Ereignisse, bei denen eine Benachrichtigung gesendet werden kann
NOTIFY_EVENTS: list[str] = ["triggered", "pending", "armed", "disarmed"]
NOTIFY_EVENT_LABELS: dict[str, str] = {
    "triggered": "Alarm ausgelöst (triggered)",
    "pending": "Eingangsverzögerung läuft (pending)",
    "armed": "Scharf geschaltet (armed)",
    "disarmed": "Unscharf geschaltet (disarmed)",
}

# Automatik (Phase 8): Präsenz- und Zeitsteuerung
CONF_AUTO_ARM = "auto_arm"               # scharf, wenn alle weg
CONF_AUTO_DISARM = "auto_disarm"         # unscharf, wenn erste Person heimkommt
CONF_PRESENCE = "presence"               # person/device_tracker-Entitäten
CONF_AUTO_ARM_MODE = "auto_arm_mode"     # Zielmodus beim Auto-Scharfschalten
CONF_AUTO_ARM_DELAY = "auto_arm_delay"   # Sekunden Verzögerung nach „alle weg"
CONF_NIGHT_SCHEDULE = "night_schedule"   # Nachtmodus nach Zeitplan
CONF_NIGHT_START = "night_start"         # "HH:MM:SS"
CONF_NIGHT_END = "night_end"             # "HH:MM:SS"
CONF_NIGHT_REQUIRE_HOME = "night_require_home"  # nur scharf, wenn jemand zuhause

DEFAULT_AUTO_ARM_MODE = "armed_away"
DEFAULT_AUTO_ARM_DELAY = 120
DEFAULT_NIGHT_START = "23:00:00"
DEFAULT_NIGHT_END = "06:30:00"

# Sabotage + offene Sensoren beim Scharfschalten (Phase 9)
CONF_TAMPER = "tamper_detection"     # Meldung, wenn ein Sensor unerreichbar wird
CONF_OPEN_ON_ARM = "open_on_arm"     # Umgang mit offenen Sensoren beim Scharfschalten
DEFAULT_TAMPER = True
DEFAULT_OPEN_ON_ARM = "allow"
OPEN_ON_ARM_OPTIONS = ["allow", "bypass", "block"]
OPEN_ON_ARM_LABELS = {
    "allow": "Trotzdem scharf schalten (Standard)",
    "bypass": "Offene Sensoren umgehen & melden",
    "block": "Scharfschalten verhindern",
}

# Härtung / Review-Fixes (Phase 10)
CONF_TAMPER_TRIGGERS = "tamper_triggers"               # Sabotage löst Alarm aus
CONF_AUTO_DISARM_DURING_ALARM = "auto_disarm_during_alarm"  # Auto-unscharf auch bei Alarm
DEFAULT_TAMPER_TRIGGERS = False
DEFAULT_AUTO_DISARM_DURING_ALARM = False
# Sichere Standard-Modi, wenn add_sensor ohne modes aufgerufen wird (nicht armed_home)
SAFE_DEFAULT_MODES = ["armed_away", "armed_vacation"]

# Signal: Optionen geändert (Entität aktualisiert sich live, ohne Reload)
SIGNAL_OPTIONS_UPDATED = DOMAIN + "_options_updated_{}"

# Code-Hashing (Phase 11, #6): kein Klartext mehr in den Optionen
CONF_CODE_HASH = "code_hash"
CONF_CODE_SALT = "code_salt"
CONF_CODE_IS_NUMBER = "code_is_number"
CONF_CODE_SET = "code_set"

# Persönliche / Gast-PINs (#10): Liste von {name, hash, salt, is_number, valid_until}
CONF_PINS = "pins"

# Ein-/Ausgangsverzögerung je Modus (#8): {mode: sekunden} als Overrides, sonst global
CONF_EXIT_DELAYS = "exit_delays"
CONF_ENTRY_DELAYS = "entry_delays"
