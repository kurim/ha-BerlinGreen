"""Binärsensor 'Wasser knapp' (an, wenn der Wasserstand niedrig oder leer ist) - praktisch für Benachrichtigungen."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import GreenBoxEntity
from .protocol import water_status


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    d = hass.data["greenbox"][entry.entry_id]
    entities = [GreenBoxWaterLow(d)]
    if not getattr(d, "uses_bluetooth", True):  # Taster-Zustand liefert nur die Custom-Firmware (MQTT)
        entities.append(GreenBoxButtonPressed(d))
    async_add_entities(entities)


class GreenBoxWaterLow(GreenBoxEntity, BinarySensorEntity):
    _attr_translation_key = "water_low"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, device) -> None:
        super().__init__(device, "water_low")

    @property
    def is_on(self) -> bool | None:
        status = water_status(self._device.state.water)
        return None if status is None else status in ("low", "empty")

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        return {"status": water_status(self._device.state.water)}  # ok | low | empty


class GreenBoxButtonPressed(GreenBoxEntity, BinarySensorEntity):
    """An, solange die Firmware den Touch-Taster als berührt erkennt."""

    _attr_translation_key = "button_pressed"

    def __init__(self, device) -> None:
        super().__init__(device, "button_pressed")

    @property
    def is_on(self) -> bool | None:
        return self._device.state.button_pressed
