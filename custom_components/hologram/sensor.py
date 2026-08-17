"""Sensors for Hologram integration."""
from __future__ import annotations

from datetime import date

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.config_entries import ConfigEntry

from .const import DOMAIN
from .entity import HologramEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    slow_coordinator = data["slow_coordinator"]
    device_id = entry.data.get("device_id")
    device_name = entry.title or entry.data.get("name") or f"hologram_{device_id}"

    entities = [
        HologramUsageCurrentBillingCycleSensor(coordinator, device_id, device_name),
        HologramUsagePreviousBillingCycleSensor(coordinator, device_id, device_name),
    ]
    if entry.data.get("orgid") is not None:
        entities.append(HologramBalanceSensor(slow_coordinator, device_id, device_name))

    links = coordinator.data.get("device", {}).get("links", {}).get("cellular", [])
    for link in links:
        link_id = link.get("id")
        entities.append(HologramSimHistorySensor(slow_coordinator, device_id, device_name, link_id, coordinator))
        entities.append(HologramSimSmsUsageSensor(slow_coordinator, device_id, device_name, link_id, coordinator))
        entities.append(HologramSimDailyUsageSensor(slow_coordinator, device_id, device_name, link_id, coordinator))
        entities.append(HologramSimMonthlyUsageSensor(slow_coordinator, device_id, device_name, link_id, coordinator))

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
                    return round(int(cur_bytes) / 1_000_000, 2)
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
                    attrs["limit_mb"] = round(attrs["limit_bytes"] / 1_000_000, 2)
                    cur_bytes = link.get("cur_billing_data_used", 0)
                    if cur_bytes:
                        limit_mb = round(int(attrs["limit_bytes"]) / 1_000_000, 2)
                        used_mb = round(int(cur_bytes) / 1_000_000, 2)
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
                    return round(int(last_bytes) / 1_000_000, 2)
        except Exception:
            pass
        return 0


class HologramSimEntity(HologramEntity):
    """Shared base for per-SIM sensors bound to the slow coordinator.

    Keeps a plain (unsubscribed) reference to the fast coordinator purely
    for cosmetic labeling (msisdn) - available/refresh state still comes
    from whichever coordinator this entity is bound to via super().__init__.
    """

    def __init__(self, coordinator, device_id, device_name, link_id, link_coordinator):
        super().__init__(coordinator, device_id, device_name)
        self._link_id = link_id
        self._link_coordinator = link_coordinator

    def _msisdn(self):
        links = self._link_coordinator.data.get("device", {}).get("links", {}).get("cellular", [])
        link = next((l for l in links if l.get("id") == self._link_id), None)
        return (link or {}).get("msisdn") or self._link_id


class HologramSimHistorySensor(HologramSimEntity, Entity):
    """Most recent state change for a SIM (pause/resume history)."""

    def __init__(self, coordinator, device_id, device_name, link_id, link_coordinator):
        super().__init__(coordinator, device_id, device_name, link_id, link_coordinator)
        self._attr_unique_id = f"hologram_{device_id}_sim_{link_id}_history"

    @property
    def name(self):
        return f"Hologram {self._device_id} SIM {self._msisdn()} History"

    def _record(self):
        return self.coordinator.data.get("history", {}).get(self._link_id)

    @property
    def state(self):
        record = self._record()
        return (record or {}).get("newstate")

    @property
    def extra_state_attributes(self):
        record = self._record()
        if not record:
            return {}
        return {
            "timestamp": record.get("timestamp"),
            "old_state": record.get("oldstate"),
            "reason": record.get("reason"),
        }


class HologramSimSmsUsageSensor(HologramSimEntity, Entity):
    """Count of recent SMS messages for a SIM (most recent 500 records)."""

    def __init__(self, coordinator, device_id, device_name, link_id, link_coordinator):
        super().__init__(coordinator, device_id, device_name, link_id, link_coordinator)
        self._attr_unique_id = f"hologram_{device_id}_sim_{link_id}_sms_usage"

    @property
    def name(self):
        return f"Hologram {self._device_id} SIM {self._msisdn()} SMS Usage"

    def _records(self):
        records = self.coordinator.data.get("sms_usage", [])
        return [r for r in records if r.get("linkid") == self._link_id]

    @property
    def state(self):
        return len(self._records())

    @property
    def extra_state_attributes(self):
        records = self._records()
        if not records:
            return {}
        latest = records[0]
        return {
            "last_message_timestamp": latest.get("timestamp"),
            "last_message_direction": latest.get("direction"),
        }


class HologramSimDailyUsageSensor(HologramSimEntity, Entity):
    """Data usage today (calendar day, not billing cycle)."""

    def __init__(self, coordinator, device_id, device_name, link_id, link_coordinator):
        super().__init__(coordinator, device_id, device_name, link_id, link_coordinator)
        self._attr_unique_id = f"hologram_{device_id}_sim_{link_id}_usage_today"
        self._attr_unit_of_measurement = "MB"

    @property
    def name(self):
        return f"Hologram {self._device_id} SIM {self._msisdn()} Usage Today"

    @property
    def state(self):
        today = date.today().isoformat()
        records = self.coordinator.data.get("daily_usage", [])
        total = sum(
            int(r.get("bytes") or 0)
            for r in records
            if r.get("linkid") == self._link_id and r.get("date") == today
        )
        return round(total / 1_000_000, 2)


class HologramSimMonthlyUsageSensor(HologramSimEntity, Entity):
    """Data usage this calendar month (not billing cycle)."""

    def __init__(self, coordinator, device_id, device_name, link_id, link_coordinator):
        super().__init__(coordinator, device_id, device_name, link_id, link_coordinator)
        self._attr_unique_id = f"hologram_{device_id}_sim_{link_id}_usage_month"
        self._attr_unit_of_measurement = "MB"

    @property
    def name(self):
        return f"Hologram {self._device_id} SIM {self._msisdn()} Usage This Month"

    @property
    def state(self):
        today = date.today()
        records = self.coordinator.data.get("monthly_usage", [])
        total = sum(
            int(r.get("bytes") or 0)
            for r in records
            if r.get("linkid") == self._link_id
            and int(r.get("month") or 0) == today.month
            and int(r.get("year") or 0) == today.year
        )
        return round(total / 1_000_000, 2)
