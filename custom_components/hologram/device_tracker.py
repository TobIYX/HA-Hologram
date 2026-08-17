"""Device tracker for Hologram integration - approximate device location."""
from __future__ import annotations

from homeassistant.components.device_tracker import SourceType
from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .entity import HologramEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    slow_coordinator = data["slow_coordinator"]
    device_id = entry.data.get("device_id")
    device_name = entry.title or entry.data.get("name") or f"hologram_{device_id}"

    async_add_entities([HologramDeviceLocationTracker(slow_coordinator, device_id, device_name)])


class HologramDeviceLocationTracker(HologramEntity, TrackerEntity):
    """Cell-tower-based location estimate for the device (not GPS).

    Only available on Hologram's professional plan - if the device isn't
    present in the locations response, this stays "unavailable" rather
    than erroring.
    """

    _attr_source_type = SourceType.GPS

    def __init__(self, coordinator, device_id, device_name):
        super().__init__(coordinator, device_id, device_name)
        self._attr_name = f"Hologram {device_id} Location"
        self._attr_unique_id = f"hologram_{device_id}_location"

    def _location(self):
        return self.coordinator.data.get("locations", {}).get(str(self._device_id))

    @property
    def available(self):
        return self.coordinator.last_update_success and self._location() is not None

    @property
    def latitude(self):
        return (self._location() or {}).get("latitude")

    @property
    def longitude(self):
        return (self._location() or {}).get("longitude")

    @property
    def extra_state_attributes(self):
        return {"location_method": "cell-tower estimate, not GPS"}
