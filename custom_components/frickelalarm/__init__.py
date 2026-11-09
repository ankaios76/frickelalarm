"""Frickelalarm – Alarmanlagen-Integration für Home Assistant.

Richtet pro Config-Eintrag einen Alarmbereich (alarm_control_panel) mit eigener
Alarm-Engine ein und liefert die Lovelace-Karte (frickelalarm-card) gleich mit.
"""

from __future__ import annotations

import logging
import os

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS

_LOGGER = logging.getLogger(__name__)

CARD_VERSION = "0.9.0"
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


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Einen Alarmbereich einrichten."""
    hass.data.setdefault(DOMAIN, {})
    await _register_frontend(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Einen Alarmbereich entladen."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Neu laden, wenn Optionen geändert wurden."""
    await hass.config_entries.async_reload(entry.entry_id)
