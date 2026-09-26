"""Schalter: 'Bei niedrigem Wasser blinken' (ff06) und 'Mit Cloud synchronisieren' (Cloud-Modus je Box)."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .entity import GreenBoxEntity
from .hub import CONF_CLOUD, DOMAIN, Garden


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    garden: Garden = hass.data[DOMAIN]["_garden"]
    if not entry.data.get(CONF_CLOUD):
        device = hass.data[DOMAIN][entry.entry_id]
        async_add_entities([GreenBoxBlink(device), CloudSync(garden, device.address)])
        return
    known: set[str] = set()

    @callback
    def add_new() -> None:
        """Auch Boxen ohne Bluetooth (nur im Cloud-Konto) bekommen den Schalter; neue Boxen kommen später dazu."""
        new = [CloudSync(garden, k) for k in garden.keys_for(entry) if k not in known and k in garden.raw_cloud]
        known.update(s.box_key for s in new)
        if new:
            async_add_entities(new)

    add_new()
    entry.async_on_unload(garden.coordinator.async_add_listener(add_new))


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


class CloudSync(CoordinatorEntity, SwitchEntity):
    """Cloud-Modus einer Box. An: Pflanzen-Änderungen gehen an die Cloud (die App zeigt dasselbe). Aus: alles lokal."""

    _attr_has_entity_name = True
    _attr_translation_key = "cloud_sync"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, garden: Garden, box_key: str) -> None:
        super().__init__(garden.coordinator)
        self._garden, self.box_key = garden, box_key
        self._attr_unique_id = f"{box_key}_cloud_sync"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, box_key)})

    @property
    def is_on(self) -> bool:
        return self.box_key in self._garden.local.get("cloud_sync", [])

    @property
    def available(self) -> bool:
        return self.box_key in self._garden.raw_cloud or self.is_on  # ohne Cloud lässt er sich nicht einschalten

    async def async_turn_on(self, **kwargs) -> None:
        await self._garden.async_set_sync(self.box_key, True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._garden.async_set_sync(self.box_key, False)
