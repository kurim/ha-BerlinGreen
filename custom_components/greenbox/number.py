"""Helligkeit (Intensität in %) und optional die einzelnen Streifen (standardmäßig deaktiviert)."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import GreenBoxEntity
from .protocol import DURATION_RANGE, frame_strip, light_from_strips, max_intensity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    device = hass.data["greenbox"][entry.entry_id]
    async_add_entities(
        [
            GreenBoxIntensity(device),
            GreenBoxDuration(device, "workdays"),
            GreenBoxDuration(device, "weekend"),
            *(GreenBoxStrip(device, n) for n in (1, 2, 3)),
        ]
    )


class GreenBoxIntensity(GreenBoxEntity, NumberEntity):
    """Lichtstärke wie in der App. Höchstwert hängt von der Farbtemperatur ab (33 / 66 / 100 / 66 / 33 %)."""

    _attr_translation_key = "intensity"
    _attr_native_min_value = 0
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER

    def __init__(self, device) -> None:
        super().__init__(device, "intensity")

    @property
    def native_max_value(self) -> float:
        return max_intensity(self._device.temp_idx)

    @property
    def native_value(self) -> float | None:
        light = light_from_strips(self._device.state.strips)
        return None if light is None else light[0]

    async def async_set_native_value(self, value: float) -> None:
        await self._device.async_set_light(int(round(value)), self._device.temp_idx)


class GreenBoxStrip(GreenBoxEntity, NumberEntity):
    """Rohwert eines einzelnen Lichtstreifens (0-100) - für Fortgeschrittene."""

    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER
    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False

    def __init__(self, device, strip: int) -> None:
        super().__init__(device, f"strip{strip}")
        self._strip = strip
        self._attr_translation_key = f"strip{strip}"

    @property
    def native_value(self) -> float | None:
        return self._device.state.strips.get(self._strip)

    async def async_set_native_value(self, value: float) -> None:
        percent = int(round(value))
        await self._device.async_write(frame_strip(self._strip, percent))
        self._device.state.strips[self._strip] = percent  # optimistisch
        self.async_write_ha_state()


class GreenBoxDuration(GreenBoxEntity, NumberEntity):
    """Dauer der Lichtphase (App: 12-18 h)."""

    _attr_native_min_value = DURATION_RANGE[0]
    _attr_native_max_value = DURATION_RANGE[1]
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_mode = NumberMode.BOX

    def __init__(self, device, kind: str) -> None:
        super().__init__(device, f"duration_{kind}")
        self._kind = kind
        self._attr_translation_key = f"duration_{kind}"

    @property
    def native_value(self) -> float | None:
        view = self._device.schedule_view(self._kind)
        return None if view is None else view[2]

    async def async_set_native_value(self, value: float) -> None:
        await self._device.async_set_schedule(self._kind, hours=int(round(value)))
