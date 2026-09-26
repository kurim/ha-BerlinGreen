"""Auswahlfelder: Lichtmodus (Automatik/An/Aus), Lichtprofil, Farbtemperatur."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import GreenBoxEntity
from .protocol import (
    OVERRIDE_BY_NAME,
    OVERRIDE_BY_VALUE,
    PRESETS,
    TEMPERATURES,
    frame_override,
    light_from_strips,
    preset_for,
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    device = hass.data["greenbox"][entry.entry_id]
    async_add_entities([GreenBoxOverride(device), GreenBoxPreset(device), GreenBoxColorTemp(device)])


class GreenBoxOverride(GreenBoxEntity, SelectEntity):
    _attr_translation_key = "override"
    _attr_options = ["auto", "on", "off"]

    def __init__(self, device) -> None:
        super().__init__(device, "override")

    @property
    def current_option(self) -> str | None:
        return OVERRIDE_BY_VALUE.get(self._device.state.override)

    async def async_select_option(self, option: str) -> None:
        value = OVERRIDE_BY_NAME[option]
        await self._device.async_write(frame_override(value))
        self._device.state.override = value  # optimistisch; die Box bestätigt per Notify
        self.async_write_ha_state()


class GreenBoxPreset(GreenBoxEntity, SelectEntity):
    """Profile der App: Wachstum 100 % / Medium 50 % / Ambient 33 % warm / Nachtlicht 5 % kalt."""

    _attr_translation_key = "preset"
    _attr_options = list(PRESETS)

    def __init__(self, device) -> None:
        super().__init__(device, "preset")

    @property
    def current_option(self) -> str | None:
        return preset_for(self._device.state.strips)  # None = benutzerdefiniert

    async def async_select_option(self, option: str) -> None:
        intensity, temp_idx = PRESETS[option]
        await self._device.async_set_light(intensity, temp_idx)


class GreenBoxColorTemp(GreenBoxEntity, SelectEntity):
    _attr_translation_key = "color_temperature"
    _attr_options = [str(k) for k in TEMPERATURES]

    def __init__(self, device) -> None:
        super().__init__(device, "color_temperature")

    @property
    def current_option(self) -> str | None:
        light = light_from_strips(self._device.state.strips)
        if light is None:
            return None  # benutzerdefinierte Streifenwerte
        return str(TEMPERATURES[self._device.temp_idx])

    async def async_select_option(self, option: str) -> None:
        temp_idx = TEMPERATURES.index(int(option))
        light = light_from_strips(self._device.state.strips)
        intensity = light[0] if light else 0
        # ist das Licht aus (Intensität 0), nur die Auswahl merken; sonst gleiche Intensität neu verteilen
        if intensity > 0:
            await self._device.async_set_light(intensity, temp_idx)
        else:
            self._device.temp_idx = temp_idx
            self.async_write_ha_state()
