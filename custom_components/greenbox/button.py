"""Buttons: Uhrzeit setzen und Garten aus der Cloud übernehmen (Bluetooth-Box), Katalog samt Fotos aktualisieren (Cloud-Konto)."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .entity import GreenBoxEntity
from .hub import CONF_CLOUD, DOMAIN


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    if entry.data.get(CONF_CLOUD):
        async_add_entities([UpdateCatalog(hass, entry)])
    else:
        device = hass.data[DOMAIN][entry.entry_id]
        async_add_entities([GreenBoxSyncTime(device), ImportFromCloud(hass.data[DOMAIN]["_garden"], device.address)])


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


class ImportFromCloud(CoordinatorEntity, ButtonEntity):
    """Übernimmt die Bepflanzung dieser Box aus dem Cloud-Konto (überschreibt den lokalen Garten). Nur wählbar, wenn die Cloud die Box kennt."""

    _attr_has_entity_name = True
    _attr_translation_key = "import_from_cloud"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, garden, address: str) -> None:
        super().__init__(garden.coordinator)
        self._garden, self._address = garden, address
        self._attr_unique_id = f"{address}_import_from_cloud"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, address)})  # gehört zum Gerät der Bluetooth-Box

    @property
    def available(self) -> bool:
        return self._address in self._garden.raw_cloud

    async def async_press(self) -> None:
        await self._garden.call("import_from_cloud", {"box": self._address})
