"""Buttons: Uhrzeit der Box setzen (Bluetooth-Box) und Katalog samt Fotos aktualisieren (Cloud-Konto)."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import GreenBoxEntity
from .hub import CONF_CLOUD, DOMAIN


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    if entry.data.get(CONF_CLOUD):
        async_add_entities([UpdateCatalog(hass, entry)])
    else:
        async_add_entities([GreenBoxSyncTime(hass.data[DOMAIN][entry.entry_id])])


class GreenBoxSyncTime(GreenBoxEntity, ButtonEntity):
    _attr_translation_key = "sync_time"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, device) -> None:
        super().__init__(device, "sync_time")

    async def async_press(self) -> None:
        await self._device.async_sync_time()


class UpdateCatalog(ButtonEntity):
    """Lädt Pflanzenkatalog und Fotos aus dem Cloud-Konto (wie der Dienst greenbox.update_catalog)."""

    _attr_has_entity_name = True
    _attr_translation_key = "update_catalog"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self._attr_unique_id = f"{entry.entry_id}_update_catalog"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)}, name=entry.title, manufacturer="Berlin Green")

    async def async_press(self) -> None:
        await self.hass.data[DOMAIN]["_garden"].call("update_catalog", {})
