"""Number entities for Hologram integration - adjustable per-SIM limits."""
from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, API_BASE
from .entity import HologramEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    auth = data["auth"]
    device_id = entry.data.get("device_id")
    device_name = entry.title or entry.data.get("name") or f"hologram_{device_id}"

    links = coordinator.data.get("device", {}).get("links", {}).get("cellular", [])
    entities = []
    for link in links:
        link_id = link.get("id")
        entities.append(HologramSimOverageLimitNumber(coordinator, device_id, device_name, link_id, auth))
        entities.append(HologramSimSmsLimitNumber(coordinator, device_id, device_name, link_id, auth))
        entities.append(HologramSimThresholdNumber(coordinator, device_id, device_name, link_id, auth))

    async_add_entities(entities, True)


class HologramSimLimitNumber(HologramEntity, NumberEntity):
    """Shared base for a single writable numeric limit on a SIM."""

    _api_path = None  # set by subclass, e.g. "limit/overage"
    _limit_field = "limit"  # POST body field name - the /threshold endpoint uses "threshold" instead

    def __init__(self, coordinator, device_id, device_name, link_id, auth):
        super().__init__(coordinator, device_id, device_name)
        self._link_id = link_id
        self._auth = auth

    def _link(self):
        links = self.coordinator.data.get("device", {}).get("links", {}).get("cellular", [])
        return next((l for l in links if l.get("id") == self._link_id), None)

    @property
    def available(self):
        return self.coordinator.last_update_success and self._link() is not None

    async def _post_limit(self, raw_value: int):
        session = async_get_clientsession(self.hass)
        url = f"{API_BASE}/links/cellular/{self._link_id}/{self._api_path}"
        try:
            resp = await session.post(url, json={self._limit_field: raw_value}, auth=self._auth, timeout=10)
        except Exception as err:
            raise HomeAssistantError(
                f"Error contacting Hologram API for SIM {self._link_id}: {err}"
            ) from err

        if resp.status != 200:
            text = await resp.text()
            raise HomeAssistantError(
                f"Failed to set limit for SIM {self._link_id}: {resp.status} {text}"
            )

        body = await resp.json()
        if not body.get("success"):
            raise HomeAssistantError(
                f"Hologram API error setting limit for SIM {self._link_id}: {body.get('error')}"
            )

        await self.coordinator.async_request_refresh()


class HologramSimOverageLimitNumber(HologramSimLimitNumber):
    """Data overage limit (bytes on the API, shown in MB). -1 = unlimited."""

    _api_path = "limit/overage"
    _attr_native_min_value = -1
    _attr_native_max_value = 1_000_000
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "MB"

    def __init__(self, coordinator, device_id, device_name, link_id, auth):
        super().__init__(coordinator, device_id, device_name, link_id, auth)
        self._attr_unique_id = f"hologram_{device_id}_sim_{link_id}_overage_limit"

    @property
    def name(self):
        link = self._link()
        msisdn = (link or {}).get("msisdn") or self._link_id
        return f"Hologram {self._device_id} SIM {msisdn} Overage Limit"

    @property
    def native_value(self):
        link = self._link()
        if not link:
            return None
        raw = link.get("overagelimit", -1)
        if raw is None or int(raw) < 0:
            return -1
        return round(int(raw) / 1_000_000, 2)

    async def async_set_native_value(self, value: float) -> None:
        raw_value = -1 if value < 0 else round(value * 1_000_000)
        await self._post_limit(raw_value)


class HologramSimSmsLimitNumber(HologramSimLimitNumber):
    """SMS limit (plain count). -1 = unlimited."""

    _api_path = "limit/sms"
    _attr_native_min_value = -1
    _attr_native_max_value = 100_000
    _attr_native_step = 1

    def __init__(self, coordinator, device_id, device_name, link_id, auth):
        super().__init__(coordinator, device_id, device_name, link_id, auth)
        self._attr_unique_id = f"hologram_{device_id}_sim_{link_id}_sms_limit"

    @property
    def name(self):
        link = self._link()
        msisdn = (link or {}).get("msisdn") or self._link_id
        return f"Hologram {self._device_id} SIM {msisdn} SMS Limit"

    @property
    def native_value(self):
        link = self._link()
        if not link:
            return None
        return int(link.get("smslimit", -1))

    async def async_set_native_value(self, value: float) -> None:
        await self._post_limit(round(value))


class HologramSimThresholdNumber(HologramSimLimitNumber):
    """Data usage alert threshold (bytes on the API, shown in MB).

    Unlike overage/SMS limits, the API docs don't explicitly confirm -1 is
    a valid "no alarm" sentinel here, so this stays non-negative until
    that's verified live.
    """

    _api_path = "threshold"
    _limit_field = "threshold"
    _attr_native_min_value = 0
    _attr_native_max_value = 1_000_000
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "MB"

    def __init__(self, coordinator, device_id, device_name, link_id, auth):
        super().__init__(coordinator, device_id, device_name, link_id, auth)
        self._attr_unique_id = f"hologram_{device_id}_sim_{link_id}_data_threshold"

    @property
    def name(self):
        link = self._link()
        msisdn = (link or {}).get("msisdn") or self._link_id
        return f"Hologram {self._device_id} SIM {msisdn} Data Threshold"

    @property
    def native_value(self):
        link = self._link()
        if not link:
            return None
        raw = link.get("datathreshold", 0)
        if raw is None or int(raw) < 0:
            return 0
        return round(int(raw) / 1_000_000, 2)

    async def async_set_native_value(self, value: float) -> None:
        raw_value = max(0, round(value * 1_000_000))
        await self._post_limit(raw_value)
