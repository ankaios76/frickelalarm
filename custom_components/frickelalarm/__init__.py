"""Frickelalarm – Alarmanlagen-Integration für Home Assistant.

Richtet pro Config-Eintrag einen Alarmbereich (alarm_control_panel) mit eigener
Alarm-Engine ein und liefert die Lovelace-Karte (frickelalarm-card) gleich mit.
"""

from __future__ import annotations

import logging
import os

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    CONF_CODE,
    CONF_CODE_HASH,
    CONF_CODE_IS_NUMBER,
    CONF_CODE_SALT,
    CONF_CODE_SET,
    DOMAIN,
    PLATFORMS,
    SIGNAL_OPTIONS_UPDATED,
)

_LOGGER = logging.getLogger(__name__)

CARD_VERSION = "0.9.1"
CARD_URL = "/frickelalarm_static/frickelalarm-card.js"


async def _register_frontend(hass: HomeAssistant) -> None:
    """Die Lovelace-Karte ausliefern und als Modul registrieren (einmalig)."""
    if hass.data[DOMAIN].get("_frontend_registered"):
        return
    try:
        from homeassistant.components.frontend import add_extra_js_url
        from homeassistant.components.http import StaticPathConfig

        path = os.path.join(os.path.dirname(__file__), "frontend", "frickelalarm-card.js")
        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL, path, False)]
        )
        add_extra_js_url(hass, f"{CARD_URL}?v={CARD_VERSION}")
        hass.data[DOMAIN]["_frontend_registered"] = True
        _LOGGER.debug("Frickelalarm-Karte registriert: %s", CARD_URL)
    except Exception:  # noqa: BLE001 - Karte darf die Integration nie blockieren
        _LOGGER.warning("Frickelalarm: Lovelace-Karte konnte nicht registriert werden", exc_info=True)


@callback
def _migrate_code(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Alten Klartext-Code zu einem Hash migrieren (#6). Danach kein Klartext mehr."""
    o = entry.options
    if CONF_CODE not in o:
        return
    from .alarm_control_panel import _hash_code, _new_salt

    code = (o.get(CONF_CODE) or "").strip()
    new = {k: v for k, v in o.items() if k != CONF_CODE}
    if code:
        salt = _new_salt()
        new[CONF_CODE_HASH] = _hash_code(code, salt)
        new[CONF_CODE_SALT] = salt
        new[CONF_CODE_IS_NUMBER] = code.isdigit()
        new[CONF_CODE_SET] = True
    else:
        new[CONF_CODE_SET] = False
    hass.config_entries.async_update_entry(entry, options=new)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Einen Alarmbereich einrichten."""
    hass.data.setdefault(DOMAIN, {})
    _migrate_code(hass, entry)
    await _register_frontend(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Einen Alarmbereich entladen."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Optionen geändert: die Entität aktualisiert sich live.

    Bewusst KEIN async_reload – ein Reload würde die Entität neu aufbauen und dabei
    einen laufenden Alarm (arming/pending/triggered) verlieren. Die Properties lesen
    die Optionen live; die Entität muss nur Sensoren/Automatik neu verdrahten.
    """
    async_dispatcher_send(hass, SIGNAL_OPTIONS_UPDATED.format(entry.entry_id))
