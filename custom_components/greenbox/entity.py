"""Gemeinsame Basis für alle GreenBox-Entitäten."""
from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .device import GreenBoxDevice


class GreenBoxEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, device: GreenBoxDevice, key: str) -> None:
        self._device = device
        self._attr_unique_id = f"{device.address}_{key}"
        st = device.state
        self._attr_device_info = DeviceInfo(
            identifiers={("greenbox", device.address)},
            name=device.name,
            manufacturer="Berlin Green",
            model="GreenBox",
            sw_version=st.firmware_name,
            connections={("bluetooth", device.address)},
        )

    @property
    def available(self) -> bool:
        return self._device.connected

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._device.register_callback(self._handle_update))

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()
