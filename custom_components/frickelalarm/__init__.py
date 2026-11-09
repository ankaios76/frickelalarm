"""Frickelalarm – Alarmanlagen-Integration für Home Assistant.

Phase 1: lädt, legt pro Config-Eintrag einen Alarmbereich (alarm_control_panel) an
und unterstützt scharf/unscharf mit optionalem Code. Die Alarm-Engine
(Verzögerungen, Sensoren, Aktionen) folgt in den nächsten Phasen.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Einen Alarmbereich einrichten."""
    hass.data.setdefault(DOMAIN, {})
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Einen Alarmbereich entladen."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Neu laden, wenn Optionen geändert wurden."""
    await hass.config_entries.async_reload(entry.entry_id)
