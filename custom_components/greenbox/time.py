"""Startzeiten der Lichtphase (Ortszeit, Werktage/Wochenende)."""
from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import GreenBoxEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    device = hass.data["greenbox"][entry.entry_id]
    async_add_entities([GreenBoxStart(device, "workdays"), GreenBoxStart(device, "weekend")])


class GreenBoxStart(GreenBoxEntity, TimeEntity):
    def __init__(self, device, kind: str) -> None:
        super().__init__(device, f"start_{kind}")
        self._kind = kind
        self._attr_translation_key = f"start_{kind}"

    @property
    def native_value(self) -> time | None:
        view = self._device.schedule_view(self._kind)
        return None if view is None else time(view[0], view[1])

    async def async_set_value(self, value: time) -> None:
        await self._device.async_set_schedule(self._kind, hour=value.hour, minute=value.minute)
