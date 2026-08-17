"""Sensors for Hologram integration."""
from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.config_entries import ConfigEntry

from .const import DOMAIN
from .entity import HologramEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    device_id = entry.data.get("device_id")
    device_name = entry.title or entry.data.get("name") or f"hologram_{device_id}"

    entities = [
        HologramUsageCurrentBillingCycleSensor(coordinator, device_id, device_name),
        HologramUsagePreviousBillingCycleSensor(coordinator, device_id, device_name),
    ]
    if entry.data.get("orgid") is not None:
        entities.append(HologramBalanceSensor(coordinator, device_id, device_name))

    async_add_entities(entities, True)


class HologramBalanceSensor(HologramEntity, Entity):
    """Organization account balance."""
    def __init__(self, coordinator, device_id, device_name):
        super().__init__(coordinator, device_id, device_name)
        self._attr_name = f"Hologram {device_id} Organization Balance"
        self._attr_unique_id = f"hologram_{device_id}_balance"
        self._attr_unit_of_measurement = "USD"

    @property
    def state(self):
        balance = self.coordinator.data.get("balance")
        if not balance:
            return None
        try:
            return round(float(balance.get("balance")), 2)
        except (TypeError, ValueError):
            return None

    @property
    def extra_state_attributes(self):
        balance = self.coordinator.data.get("balance")
        if not balance:
            return {}
        return {
            "promo_balance": balance.get("promobalance"),
            "min_balance": balance.get("minbalance"),
            "pending_charges": balance.get("pendingcharges"),
        }


class HologramUsageCurrentBillingCycleSensor(HologramEntity, Entity):
    """Current billing cycle data usage."""
    def __init__(self, coordinator, device_id, device_name):
        super().__init__(coordinator, device_id, device_name)
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


class HologramUsagePreviousBillingCycleSensor(HologramEntity, Entity):
    """Previous billing cycle data usage."""
    def __init__(self, coordinator, device_id, device_name):
        super().__init__(coordinator, device_id, device_name)
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
