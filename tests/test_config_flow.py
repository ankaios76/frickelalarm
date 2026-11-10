"""Tests für den Config- und Options-Flow."""

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.frickelalarm.const import (
    CONF_ENTRY_DELAY,
    CONF_EXIT_DELAY,
    CONF_TRIGGER_DURATION,
    DOMAIN,
)


async def test_user_flow_creates_entry(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "Haus"}
    )
    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["title"] == "Haus"
    assert result2["options"][CONF_EXIT_DELAY] == 30


async def test_duplicate_name_aborts(hass: HomeAssistant) -> None:
    existing = MockConfigEntry(
        domain=DOMAIN, title="Haus", data={"name": "Haus"}, unique_id="haus"
    )
    existing.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "Haus"}
    )
    assert result2["type"] == FlowResultType.ABORT
    assert result2["reason"] == "already_configured"


async def test_options_menu_times(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Haus",
        data={"name": "Haus"},
        options={CONF_EXIT_DELAY: 30, CONF_ENTRY_DELAY: 30, CONF_TRIGGER_DURATION: 120},
        unique_id="haus",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.MENU
    assert "times" in result["menu_options"]
    assert "actions" in result["menu_options"]

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "times"}
    )
    assert result2["type"] == FlowResultType.FORM

    result3 = await hass.config_entries.options.async_configure(
        result2["flow_id"],
        {CONF_EXIT_DELAY: 10, CONF_ENTRY_DELAY: 15, CONF_TRIGGER_DURATION: 60},
    )
    assert result3["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_EXIT_DELAY] == 10
    assert entry.options[CONF_ENTRY_DELAY] == 15


async def test_options_per_mode_delays(hass: HomeAssistant) -> None:
    from custom_components.frickelalarm.const import CONF_EXIT_DELAYS, CONF_ENTRY_DELAYS

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Haus",
        data={"name": "Haus"},
        options={CONF_EXIT_DELAY: 30, CONF_ENTRY_DELAY: 30, CONF_TRIGGER_DURATION: 120},
        unique_id="haus",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert "per_mode_delays" in result["menu_options"]
    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "per_mode_delays"}
    )
    assert result2["type"] == FlowResultType.FORM

    # Nur "Abwesend" bekommt eine eigene Ausgangsverzögerung; Rest bleibt global
    result3 = await hass.config_entries.options.async_configure(
        result2["flow_id"], {"exit_armed_away": 45}
    )
    assert result3["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_EXIT_DELAYS] == {"armed_away": 45}
    assert entry.options[CONF_ENTRY_DELAYS] == {}
