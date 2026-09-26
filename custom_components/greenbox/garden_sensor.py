"""Garten-Sensoren: je Box "Garten" (für die Card) sowie je Pflanz-Slot (8) und Microgreen-Feld (6) ein Phasen-Sensor."""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .garden import PHASES
from .hub import DOMAIN, Garden

SUMMARY_ATTRS = ("name", "box_key", "source", "type", "layout", "mix", "mix_id", "schedule", "has_package", "harvest_ready",
                 "microgreens_planted", "microgreens_ready", "mushrooms", "mushrooms_planted", "mushrooms_ready", "slots", "microgreens", "microgreen_modules",
                 "mode", "plant_slot_ids", "sync")


def setup_garden_entities(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    garden: Garden = hass.data[DOMAIN]["_garden"]
    coordinator = garden.coordinator
    known: set[str] = set()

    @callback
    def add_new() -> None:
        """Auch Boxen, die später dazukommen (z. B. neu im Cloud-Konto), bekommen ihre Entitäten."""
        new: list[SensorEntity] = []
        for box_id in garden.keys_for(entry):
            if box_id in known or box_id not in (coordinator.data or {}):
                continue
            known.add(box_id)
            box = coordinator.data[box_id]
            new.append(GardenSummary(coordinator, box_id))
            new.extend(SlotSensor(coordinator, box_id, s["slot"], "slots") for s in box["slots"])
            new.extend(SlotSensor(coordinator, box_id, s["slot"], "microgreens") for s in box["microgreens"])
        if new:
            async_add_entities(new)

    add_new()
    entry.async_on_unload(coordinator.async_add_listener(add_new))


class _Base(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, box_id: str) -> None:
        super().__init__(coordinator)
        self._box_id = box_id
        box = coordinator.data[box_id]
        if box.get("ble"):
            # Gerät gehört der Bluetooth-Box (gleiche Kennung = Adresse): nur zuordnen, Namen dort nicht überschreiben
            self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, box_id)})
        else:
            self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, box_id)}, name=box["name"], manufacturer="Berlin Green", model="GreenBox")

    @property
    def _box(self) -> dict | None:
        return self.coordinator.data.get(self._box_id)

    @property
    def available(self) -> bool:
        return super().available and self._box is not None


class GardenSummary(_Base, SensorEntity):
    _attr_translation_key = "garden"

    def __init__(self, coordinator, box_id: str) -> None:
        super().__init__(coordinator, box_id)
        self._attr_unique_id = f"{box_id}_garden"

    @property
    def native_value(self) -> int | None:
        return self._box["planted_count"] if self._box else None

    @property
    def extra_state_attributes(self) -> dict:
        b = self._box or {}
        return {k: b.get(k) for k in SUMMARY_ATTRS}


class SlotSensor(_Base, SensorEntity):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = PHASES

    def __init__(self, coordinator, box_id: str, slot: int, kind: str) -> None:
        super().__init__(coordinator, box_id)
        self._slot = slot
        self._kind = kind  # "slots" (Mix-Paket) oder "microgreens" (Microgreen-Modul)
        self._attr_unique_id = f"{box_id}_slot{slot}" if kind == "slots" else f"{box_id}_microgreen{slot}"
        self._attr_translation_key = "slot" if kind == "slots" else "microgreen"
        self._attr_translation_placeholders = {"slot": str(slot + 1)}  # Anzeige 1-8, intern 0-7 wie in der Cloud

    @property
    def _data(self) -> dict | None:
        items = (self._box or {}).get(self._kind) or []
        return items[self._slot] if self._slot < len(items) else None

    @property
    def native_value(self) -> str | None:
        d = self._data
        return d["phase"] if d else None

    @property
    def extra_state_attributes(self) -> dict:
        d = dict(self._data or {})
        d.pop("phase", None)
        d.pop("state_only", None)
        return d
