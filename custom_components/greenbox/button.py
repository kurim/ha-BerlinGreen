"""Button: Uhrzeit der Box setzen."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import GreenBoxEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([GreenBoxSyncTime(hass.data["greenbox"][entry.entry_id])])


class GreenBoxSyncTime(GreenBoxEntity, ButtonEntity):
    _attr_translation_key = "sync_time"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, device) -> None:
        super().__init__(device, "sync_time")

    async def async_press(self) -> None:
        await self._device.async_sync_time()
