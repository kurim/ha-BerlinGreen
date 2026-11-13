"""Sensoren: Wasserstand (Prozent + Status), Firmware, Hardware-Revision, Temperatur (falls gültig), Taster-Rohwerte (nur MQTT)."""
from __future__ import annotations

from time import monotonic

from homeassistant.components.sensor import RestoreSensor, SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfEnergy, UnitOfPower, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import GreenBoxEntity
from .garden_sensor import setup_garden_entities
from .hub import CONF_CLOUD, box_key
from .protocol import water_status


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    # Garten je Box (Cloud-Eintrag: Boxen ohne Bluetooth); MQTT-Box erst, wenn die Firmware ihre Bluetooth-Adresse gemeldet hat
    if entry.data.get(CONF_CLOUD) or box_key(entry):
        setup_garden_entities(hass, entry, async_add_entities)
    if entry.data.get(CONF_CLOUD):
        return
    d = hass.data["greenbox"][entry.entry_id]
    async_add_entities(
        [GreenBoxWater(d), GreenBoxWaterStatus(d), GreenBoxFirmware(d), GreenBoxTemperature(d)]
    )
    if getattr(d, "uses_bluetooth", True):  # Hardware-Revision kommt nur von der Original-Firmware (BLE-Typ 'r'), nicht über MQTT
        async_add_entities([GreenBoxHardware(d)])
    else:  # Taster-Rohwerte liefert nur die Custom-Firmware (MQTT)
        async_add_entities([GreenBoxPower(d), GreenBoxEnergy(d), GreenBoxButtonTouch(d), GreenBoxButtonBaseline(d)])


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


class GreenBoxPower(GreenBoxEntity, SensorEntity):
    """Geschätzte Leistungsaufnahme aus den Streifenwerten (Messreihe in BerlinGreen-FW), keine Messung."""

    _attr_translation_key = "power"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, device) -> None:
        super().__init__(device, "power")

    @property
    def native_value(self) -> float | None:
        return self._device.state.power


class GreenBoxEnergy(GreenBoxEntity, RestoreSensor):
    """Energie in kWh: Summe aus der geschätzten Leistung (zuletzt gemeldeter Wert gilt bis zur nächsten Meldung)."""

    _attr_translation_key = "energy"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 3

    def __init__(self, device) -> None:
        super().__init__(device, "energy")
        self._kwh = 0.0
        self._last: float | None = None  # monotonic-Zeit der letzten Integration

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_sensor_data()) and last.native_value is not None:
            self._kwh = float(last.native_value)

    @callback
    def _handle_update(self) -> None:
        now = monotonic()
        power = self._device.state.power
        # shortcut: Rechteckregel über das Meldeintervall (Firmware meldet Änderungen sofort, sonst alle 60 s)
        if self._last is not None and power is not None:
            self._kwh += power * (now - self._last) / 3_600_000
        self._last = now
        super()._handle_update()

    @property
    def native_value(self) -> float:
        return round(self._kwh, 4)


class GreenBoxButtonTouch(GreenBoxEntity, SensorEntity):
    """Rohwert des Touch-Tasters (IO12): niedrig = berührt. Im Verlauf sieht man, ob spontane Auslösungen vom Taster kommen."""

    _attr_translation_key = "button_touch"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, device) -> None:
        super().__init__(device, "button_touch")

    @property
    def native_value(self) -> int | None:
        return self._device.state.touch_button


class GreenBoxButtonBaseline(GreenBoxEntity, SensorEntity):
    """Nachlaufende Baseline des Tasters; die Firmware löst aus, wenn der Rohwert unter Baseline minus Schwelle fällt."""

    _attr_translation_key = "button_baseline"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, device) -> None:
        super().__init__(device, "button_baseline")

    @property
    def native_value(self) -> int | None:
        return self._device.state.touch_base
