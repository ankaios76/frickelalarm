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
