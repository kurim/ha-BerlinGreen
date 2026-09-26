"""Sensoren: Wasserstand (Prozent + Status), Firmware, Hardware-Revision, Temperatur (falls gültig)."""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import GreenBoxEntity
from .garden_sensor import setup_garden_entities
from .hub import CONF_CLOUD
from .protocol import water_status


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    setup_garden_entities(hass, entry, async_add_entities)  # Garten je Box (Cloud-Eintrag: Boxen ohne Bluetooth)
    if entry.data.get(CONF_CLOUD):
        return
    d = hass.data["greenbox"][entry.entry_id]
    async_add_entities(
        [GreenBoxWater(d), GreenBoxWaterStatus(d), GreenBoxFirmware(d), GreenBoxHardware(d), GreenBoxTemperature(d)]
    )


class GreenBoxWater(GreenBoxEntity, SensorEntity):
    _attr_translation_key = "water_level"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, device) -> None:
        super().__init__(device, "water_level")

    @property
    def native_value(self) -> int | None:
        return self._device.state.water


class GreenBoxWaterStatus(GreenBoxEntity, SensorEntity):
    _attr_translation_key = "water_status"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["ok", "low", "empty"]

    def __init__(self, device) -> None:
        super().__init__(device, "water_status")

    @property
    def native_value(self) -> str | None:
        return water_status(self._device.state.water)


class GreenBoxFirmware(GreenBoxEntity, SensorEntity):
    _attr_translation_key = "firmware"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, device) -> None:
        super().__init__(device, "firmware")

    @property
    def native_value(self) -> str | None:
        return self._device.state.firmware_name


class GreenBoxHardware(GreenBoxEntity, SensorEntity):
    _attr_translation_key = "hardware"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, device) -> None:
        super().__init__(device, "hardware")

    @property
    def native_value(self) -> int | None:
        return self._device.state.hardware


class GreenBoxTemperature(GreenBoxEntity, SensorEntity):
    """Ohne Sensor meldet die Box 255; die App wertet nur Werte < 200 aus -> dann 'unbekannt'."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_registry_enabled_default = False  # Einheit/Skalierung nicht verifiziert

    def __init__(self, device) -> None:
        super().__init__(device, "temperature")

    @property
    def native_value(self) -> int | None:
        return self._device.state.temperature_c
