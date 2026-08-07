"""Sensors for Hologram integration."""
from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.config_entries import ConfigEntry

from .const import DOMAIN


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    device_id = entry.data.get("device_id")

    async_add_entities([
        HologramMessageSensor(coordinator, device_id),
        HologramUsageCurrentBillingCycleSensor(coordinator, device_id),
        HologramUsagePreviousBillingCycleSensor(coordinator, device_id),
    ], True)


class HologramMessageSensor(CoordinatorEntity, Entity):
    def __init__(self, coordinator, device_id):
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_name = f"Hologram {device_id} Last Message"
        self._attr_unique_id = f"hologram_{device_id}_message"

    @property
    def state(self):
        last = self.coordinator.data.get("last_message")
        if not last:
            return "No message"
        return last.get("data", "No data")

    @property
    def extra_state_attributes(self):
        last = self.coordinator.data.get("last_message")
        if not last:
            return {}
        return {
            "logged": last.get("logged"),
            "record_id": last.get("record_id"),
        }


class HologramUsageCurrentBillingCycleSensor(CoordinatorEntity, Entity):
    """Current billing cycle data usage."""
    def __init__(self, coordinator, device_id):
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_name = f"Hologram {device_id} Usage Current Billing Cycle"
        self._attr_unique_id = f"hologram_{device_id}_usage_current"
        self._attr_unit_of_measurement = "MB"

    @property
    def state(self):
        device = self.coordinator.data.get("device", {})
        try:
            links = device.get("links", {}).get("cellular", [])
            if links:
                # Get cur_billing_data_used from first link
                cur_bytes = links[0].get("cur_billing_data_used", 0)
                if cur_bytes:
                    return round(int(cur_bytes) / (1024 * 1024), 2)
        except Exception:
            pass
        return 0

    @property
    def extra_state_attributes(self):
        device = self.coordinator.data.get("device", {})
        attrs = {"device_name": device.get("name", "Unknown")}
        try:
            links = device.get("links", {}).get("cellular", [])
            if links:
                link = links[0]
                attrs["limit_bytes"] = link.get("overagelimit", -1)
                if attrs["limit_bytes"] > 0:
                    attrs["limit_mb"] = round(attrs["limit_bytes"] / (1024 * 1024), 2)
                    cur_bytes = link.get("cur_billing_data_used", 0)
                    if cur_bytes:
                        limit_mb = round(int(attrs["limit_bytes"]) / (1024 * 1024), 2)
                        used_mb = round(int(cur_bytes) / (1024 * 1024), 2)
                        attrs["usage_percent"] = round((used_mb / limit_mb) * 100, 1) if limit_mb > 0 else 0
                attrs["sim"] = link.get("sim", "Unknown")
                attrs["state"] = link.get("state", "Unknown")
                attrs["msisdn"] = link.get("msisdn", "")
        except Exception:
            pass
        return attrs


class HologramUsagePreviousBillingCycleSensor(CoordinatorEntity, Entity):
    """Previous billing cycle data usage."""
    def __init__(self, coordinator, device_id):
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_name = f"Hologram {device_id} Usage Previous Billing Cycle"
        self._attr_unique_id = f"hologram_{device_id}_usage_previous"
        self._attr_unit_of_measurement = "MB"

    @property
    def state(self):
        device = self.coordinator.data.get("device", {})
        try:
            links = device.get("links", {}).get("cellular", [])
            if links:
                last_bytes = links[0].get("last_billing_data_used", 0)
                if last_bytes:
                    return round(int(last_bytes) / (1024 * 1024), 2)
        except Exception:
            pass
        return 0
