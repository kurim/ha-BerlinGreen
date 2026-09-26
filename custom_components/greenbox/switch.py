"""Schalter 'Bei niedrigem Wasser blinken' (ff06)."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import GreenBoxEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([GreenBoxBlink(hass.data["greenbox"][entry.entry_id])])


class GreenBoxBlink(GreenBoxEntity, SwitchEntity):
    _attr_translation_key = "blink_on_low_water"

    def __init__(self, device) -> None:
        super().__init__(device, "blink_on_low_water")

    @property
    def is_on(self) -> bool | None:
        return self._device.state.blink_on_low_water

    async def async_turn_on(self, **kwargs) -> None:
        await self._device.async_set_blink(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._device.async_set_blink(False)
