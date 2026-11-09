"""Config- und Options-Flow für Frickelalarm (UI-Einrichtung)."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
    TimeSelector,
)

from .const import (
    ARM_MODE_LABELS,
    ARM_MODES,
    CONF_ALWAYS,
    CONF_AUTO_ARM,
    CONF_AUTO_ARM_DELAY,
    CONF_AUTO_ARM_MODE,
    CONF_AUTO_DISARM,
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
    CONF_NOTIFY_EVENTS,
    CONF_NOTIFY_MESSAGE,
    CONF_NOTIFY_SERVICE,
    CONF_OPEN_ON_ARM,
    CONF_PRESENCE,
    CONF_SENSORS,
    CONF_SIRENS,
    CONF_TAMPER,
    CONF_TRIGGER_DURATION,
    DEFAULT_AUTO_ARM_DELAY,
    DEFAULT_AUTO_ARM_MODE,
    DEFAULT_ENTRY_DELAY,
    DEFAULT_EXIT_DELAY,
    DEFAULT_NAME,
    DEFAULT_NIGHT_END,
    DEFAULT_NIGHT_START,
    DEFAULT_NOTIFY_MESSAGE,
    DEFAULT_OPEN_ON_ARM,
    DEFAULT_TAMPER,
    DEFAULT_TRIGGER_DURATION,
    DOMAIN,
    NOTIFY_EVENT_LABELS,
    NOTIFY_EVENTS,
    OPEN_ON_ARM_LABELS,
    OPEN_ON_ARM_OPTIONS,
)

_SECONDS = NumberSelector(
    NumberSelectorConfig(min=0, max=600, step=1, mode=NumberSelectorMode.BOX)
)


class FrickelalarmConfigFlow(ConfigFlow, domain=DOMAIN):
    """Ersteinrichtung: ein Alarmbereich pro Eintrag."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input[CONF_NAME].strip()
            await self.async_set_unique_id(name.casefold())
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=name,
                data={CONF_NAME: name},
                options={
                    CONF_CODE: (user_input.get(CONF_CODE) or "").strip(),
                    CONF_CODE_ARM_REQUIRED: user_input.get(CONF_CODE_ARM_REQUIRED, False),
                    CONF_CODE_DISARM_REQUIRED: user_input.get(
                        CONF_CODE_DISARM_REQUIRED, False
                    ),
                    CONF_SENSORS: [],
                    CONF_EXIT_DELAY: DEFAULT_EXIT_DELAY,
                    CONF_ENTRY_DELAY: DEFAULT_ENTRY_DELAY,
                    CONF_TRIGGER_DURATION: DEFAULT_TRIGGER_DURATION,
                    CONF_SIRENS: [],
                    CONF_NOTIFY_SERVICE: "",
                    CONF_NOTIFY_MESSAGE: DEFAULT_NOTIFY_MESSAGE,
                    CONF_NOTIFY_EVENTS: ["triggered"],
                },
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                vol.Optional(CONF_CODE, default=""): str,
                vol.Optional(CONF_CODE_ARM_REQUIRED, default=False): bool,
                vol.Optional(CONF_CODE_DISARM_REQUIRED, default=False): bool,
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return FrickelalarmOptionsFlow()


class FrickelalarmOptionsFlow(OptionsFlow):
    """Einstellungen nachträglich ändern – menügeführt."""

    def __init__(self) -> None:
        self._pending_entities: list[str] = []
        self._collected: list[dict[str, Any]] = []
        self._existing: dict[str, dict[str, Any]] = {}
        self._index = 0

    def _save(self, new: dict[str, Any]) -> ConfigFlowResult:
        """Teil-Einstellungen in die bestehenden Optionen mischen und speichern."""
        data = {**self.config_entry.options, **new}
        return self.async_create_entry(title="", data=data)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="init",
            menu_options=["general", "sensors", "times", "actions", "automation"],
        )

    # --- Automatik (Präsenz + Zeitplan) -----------------------------------
    async def async_step_automation(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(
                {
                    CONF_AUTO_ARM: user_input.get(CONF_AUTO_ARM, False),
                    CONF_AUTO_DISARM: user_input.get(CONF_AUTO_DISARM, False),
                    CONF_PRESENCE: list(user_input.get(CONF_PRESENCE, [])),
                    CONF_AUTO_ARM_MODE: user_input.get(
                        CONF_AUTO_ARM_MODE, DEFAULT_AUTO_ARM_MODE
                    ),
                    CONF_AUTO_ARM_DELAY: int(
                        user_input.get(CONF_AUTO_ARM_DELAY, DEFAULT_AUTO_ARM_DELAY)
                    ),
                    CONF_NIGHT_SCHEDULE: user_input.get(CONF_NIGHT_SCHEDULE, False),
                    CONF_NIGHT_START: user_input.get(
                        CONF_NIGHT_START, DEFAULT_NIGHT_START
                    ),
                    CONF_NIGHT_END: user_input.get(CONF_NIGHT_END, DEFAULT_NIGHT_END),
                    CONF_NIGHT_REQUIRE_HOME: user_input.get(
                        CONF_NIGHT_REQUIRE_HOME, False
                    ),
                }
            )

        opts = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_AUTO_ARM, default=opts.get(CONF_AUTO_ARM, False)
                ): BooleanSelector(),
                vol.Optional(
                    CONF_AUTO_DISARM, default=opts.get(CONF_AUTO_DISARM, False)
                ): BooleanSelector(),
                vol.Optional(
                    CONF_PRESENCE, default=opts.get(CONF_PRESENCE, [])
                ): EntitySelector(
                    EntitySelectorConfig(
                        domain=["person", "device_tracker"], multiple=True
                    )
                ),
                vol.Optional(
                    CONF_AUTO_ARM_MODE,
                    default=opts.get(CONF_AUTO_ARM_MODE, DEFAULT_AUTO_ARM_MODE),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(value=m, label=ARM_MODE_LABELS[m])
                            for m in ARM_MODES
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    CONF_AUTO_ARM_DELAY,
                    default=opts.get(CONF_AUTO_ARM_DELAY, DEFAULT_AUTO_ARM_DELAY),
                ): NumberSelector(
                    NumberSelectorConfig(min=0, max=3600, step=1, mode=NumberSelectorMode.BOX)
                ),
                vol.Optional(
                    CONF_NIGHT_SCHEDULE, default=opts.get(CONF_NIGHT_SCHEDULE, False)
                ): BooleanSelector(),
                vol.Optional(
                    CONF_NIGHT_START,
                    default=opts.get(CONF_NIGHT_START, DEFAULT_NIGHT_START),
                ): TimeSelector(),
                vol.Optional(
                    CONF_NIGHT_END, default=opts.get(CONF_NIGHT_END, DEFAULT_NIGHT_END)
                ): TimeSelector(),
                vol.Optional(
                    CONF_NIGHT_REQUIRE_HOME,
                    default=opts.get(CONF_NIGHT_REQUIRE_HOME, False),
                ): BooleanSelector(),
            }
        )
        return self.async_show_form(step_id="automation", data_schema=schema)

    # --- Reaktionen (Aktoren + Benachrichtigung) --------------------------
    async def async_step_actions(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(
                {
                    CONF_SIRENS: list(user_input.get(CONF_SIRENS, [])),
                    CONF_NOTIFY_SERVICE: user_input.get(CONF_NOTIFY_SERVICE, ""),
                    CONF_NOTIFY_MESSAGE: (
                        user_input.get(CONF_NOTIFY_MESSAGE) or DEFAULT_NOTIFY_MESSAGE
                    ),
                    CONF_NOTIFY_EVENTS: list(
                        user_input.get(CONF_NOTIFY_EVENTS, ["triggered"])
                    ),
                }
            )

        opts = self.config_entry.options
        notify_services = sorted(
            self.hass.services.async_services().get("notify", {}).keys()
        )
        svc_options = [
            SelectOptionDict(value="", label="— keine Benachrichtigung —"),
            SelectOptionDict(
                value="persistent_notification.create",
                label="Dauerhafte Benachrichtigung in Home Assistant",
            ),
        ]
        svc_options += [
            SelectOptionDict(value=f"notify.{s}", label=f"notify.{s}")
            for s in notify_services
        ]

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SIRENS, default=opts.get(CONF_SIRENS, [])
                ): EntitySelector(
                    EntitySelectorConfig(
                        domain=["switch", "siren", "light", "input_boolean"],
                        multiple=True,
                    )
                ),
                vol.Optional(
                    CONF_NOTIFY_SERVICE, default=opts.get(CONF_NOTIFY_SERVICE, "")
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=svc_options, mode=SelectSelectorMode.DROPDOWN
                    )
                ),
                vol.Optional(
                    CONF_NOTIFY_MESSAGE,
                    default=opts.get(CONF_NOTIFY_MESSAGE, DEFAULT_NOTIFY_MESSAGE),
                ): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.TEXT, multiline=True)
                ),
                vol.Optional(
                    CONF_NOTIFY_EVENTS,
                    default=opts.get(CONF_NOTIFY_EVENTS, ["triggered"]),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(value=e, label=NOTIFY_EVENT_LABELS[e])
                            for e in NOTIFY_EVENTS
                        ],
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="actions", data_schema=schema)

    # --- Allgemein (Code) -------------------------------------------------
    async def async_step_general(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(
                {
                    CONF_CODE: (user_input.get(CONF_CODE) or "").strip(),
                    CONF_CODE_ARM_REQUIRED: user_input.get(
                        CONF_CODE_ARM_REQUIRED, False
                    ),
                    CONF_CODE_DISARM_REQUIRED: user_input.get(
                        CONF_CODE_DISARM_REQUIRED, False
                    ),
                    CONF_TAMPER: user_input.get(CONF_TAMPER, DEFAULT_TAMPER),
                    CONF_OPEN_ON_ARM: user_input.get(
                        CONF_OPEN_ON_ARM, DEFAULT_OPEN_ON_ARM
                    ),
                }
            )

        opts = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(CONF_CODE, default=opts.get(CONF_CODE, "")): str,
                vol.Optional(
                    CONF_CODE_ARM_REQUIRED,
                    default=opts.get(CONF_CODE_ARM_REQUIRED, False),
                ): bool,
                vol.Optional(
                    CONF_CODE_DISARM_REQUIRED,
                    default=opts.get(CONF_CODE_DISARM_REQUIRED, False),
                ): bool,
                vol.Optional(
                    CONF_TAMPER, default=opts.get(CONF_TAMPER, DEFAULT_TAMPER)
                ): BooleanSelector(),
                vol.Optional(
                    CONF_OPEN_ON_ARM,
                    default=opts.get(CONF_OPEN_ON_ARM, DEFAULT_OPEN_ON_ARM),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(value=o, label=OPEN_ON_ARM_LABELS[o])
                            for o in OPEN_ON_ARM_OPTIONS
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="general", data_schema=schema)

    # --- Zeiten -----------------------------------------------------------
    async def async_step_times(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(
                {
                    CONF_EXIT_DELAY: int(user_input[CONF_EXIT_DELAY]),
                    CONF_ENTRY_DELAY: int(user_input[CONF_ENTRY_DELAY]),
                    CONF_TRIGGER_DURATION: int(user_input[CONF_TRIGGER_DURATION]),
                }
            )

        opts = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_EXIT_DELAY,
                    default=opts.get(CONF_EXIT_DELAY, DEFAULT_EXIT_DELAY),
                ): _SECONDS,
                vol.Required(
                    CONF_ENTRY_DELAY,
                    default=opts.get(CONF_ENTRY_DELAY, DEFAULT_ENTRY_DELAY),
                ): _SECONDS,
                vol.Required(
                    CONF_TRIGGER_DURATION,
                    default=opts.get(
                        CONF_TRIGGER_DURATION, DEFAULT_TRIGGER_DURATION
                    ),
                ): _SECONDS,
            }
        )
        return self.async_show_form(step_id="times", data_schema=schema)

    # --- Sensoren ---------------------------------------------------------
    async def async_step_sensors(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._pending_entities = list(user_input.get(CONF_SENSORS, []))
            self._existing = {
                s[CONF_ENTITY_ID]: s
                for s in self.config_entry.options.get(CONF_SENSORS, [])
            }
            self._collected = []
            self._index = 0
            if not self._pending_entities:
                return self._save({CONF_SENSORS: []})
            return await self.async_step_sensor_config()

        current = [
            s[CONF_ENTITY_ID]
            for s in self.config_entry.options.get(CONF_SENSORS, [])
        ]
        schema = vol.Schema(
            {
                vol.Optional(CONF_SENSORS, default=current): EntitySelector(
                    EntitySelectorConfig(
                        domain=["binary_sensor", "input_boolean"], multiple=True
                    )
                ),
            }
        )
        return self.async_show_form(step_id="sensors", data_schema=schema)

    async def async_step_sensor_config(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entity_id = self._pending_entities[self._index]

        if user_input is not None:
            self._collected.append(
                {
                    CONF_ENTITY_ID: entity_id,
                    CONF_MODES: list(user_input.get(CONF_MODES, [])),
                    CONF_DELAYED: user_input.get(CONF_DELAYED, False),
                    CONF_ALWAYS: user_input.get(CONF_ALWAYS, False),
                }
            )
            self._index += 1
            if self._index < len(self._pending_entities):
                return await self.async_step_sensor_config()
            return self._save({CONF_SENSORS: self._collected})

        prev = self._existing.get(entity_id, {})
        state = self.hass.states.get(entity_id)
        friendly = state.name if state else entity_id

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_MODES, default=prev.get(CONF_MODES, ARM_MODES)
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(value=m, label=ARM_MODE_LABELS[m])
                            for m in ARM_MODES
                        ],
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                    )
                ),
                vol.Optional(
                    CONF_DELAYED, default=prev.get(CONF_DELAYED, False)
                ): BooleanSelector(),
                vol.Optional(
                    CONF_ALWAYS, default=prev.get(CONF_ALWAYS, False)
                ): BooleanSelector(),
            }
        )
        return self.async_show_form(
            step_id="sensor_config",
            data_schema=schema,
            description_placeholders={"sensor": friendly, "entity_id": entity_id},
        )
