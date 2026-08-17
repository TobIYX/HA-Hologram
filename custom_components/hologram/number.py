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
    slow_coordinator = data["slow_coordinator"]
    auth = data["auth"]
    device_id = entry.data.get("device_id")
    device_name = entry.title or entry.data.get("name") or f"hologram_{device_id}"

    links = coordinator.data.get("device", {}).get("links", {}).get("cellular", [])
    entities = []
    for link in links:
        link_id = link.get("id")
        entities.append(HologramSimOverageLimitNumber(coordinator, device_id, device_name, link_id, auth))
        entities.append(HologramSimSmsLimitNumber(coordinator, device_id, device_name, link_id, auth))
        entities.append(
            HologramSimThresholdNumber(slow_coordinator, device_id, device_name, link_id, auth, coordinator)
        )

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

        # The POST response already contains the server-confirmed, updated SIM
        # object - use it directly instead of an immediate re-GET, which for
        # some fields (e.g. datathreshold) doesn't reflect the change right away.
        # Some Hologram endpoints wrap even a single object in a one-item list.
        updated_link = body.get("data")
        if isinstance(updated_link, list):
            updated_link = updated_link[0] if updated_link else None
        if isinstance(updated_link, dict) and updated_link.get("id") == self._link_id:
            self._apply_link_update(updated_link)
        else:
            await self.coordinator.async_request_refresh()

    def _apply_link_update(self, updated_link: dict):
        """Merge a freshly POSTed link object into the coordinator's cached data."""
        data = self.coordinator.data
        links = data.get("device", {}).get("links", {}).get("cellular", [])
        new_links = [
            {**link, **updated_link} if link.get("id") == self._link_id else link
            for link in links
        ]
        new_data = {
            **data,
            "device": {**data.get("device", {}), "links": {"cellular": new_links}},
        }
        self.coordinator.async_set_updated_data(new_data)


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

    GET /devices/{id} doesn't reliably reflect datathreshold on its embedded
    SIM objects (unlike overagelimit/smslimit, which it does) - confirmed by
    the value not surviving a HA restart or a change made directly on the
    Hologram dashboard. So unlike the other two limits, this entity binds to
    the *slow* coordinator and reads from its dedicated per-link fetch
    (GET /links/cellular/{id}, see __init__.py's link_details) instead of the
    fast coordinator's device-detail data. It keeps a plain reference to the
    fast coordinator only for msisdn-based naming, mirroring sensor.py's
    HologramSimEntity pattern.

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

    def __init__(self, coordinator, device_id, device_name, link_id, auth, device_coordinator):
        # coordinator here is the slow coordinator (availability + link_details source)
        super().__init__(coordinator, device_id, device_name, link_id, auth)
        self._device_coordinator = device_coordinator
        self._attr_unique_id = f"hologram_{device_id}_sim_{link_id}_data_threshold"

    def _link_detail(self):
        return self.coordinator.data.get("link_details", {}).get(self._link_id)

    def _device_link(self):
        links = self._device_coordinator.data.get("device", {}).get("links", {}).get("cellular", [])
        return next((l for l in links if l.get("id") == self._link_id), None)

    @property
    def available(self):
        return self.coordinator.last_update_success and self._link_detail() is not None

    @property
    def name(self):
        link = self._device_link()
        msisdn = (link or {}).get("msisdn") or self._link_id
        return f"Hologram {self._device_id} SIM {msisdn} Data Threshold"

    @property
    def native_value(self):
        link = self._link_detail()
        if not link:
            return None
        raw = link.get("datathreshold", 0)
        if raw is None or int(raw) < 0:
            return 0
        return round(int(raw) / 1_000_000, 2)

    async def async_set_native_value(self, value: float) -> None:
        raw_value = max(0, round(value * 1_000_000))
        await self._post_limit(raw_value)

    def _apply_link_update(self, updated_link: dict):
        """Merge a freshly POSTed link object into the slow coordinator's link_details."""
        data = self.coordinator.data
        new_details = dict(data.get("link_details", {}))
        new_details[self._link_id] = {**new_details.get(self._link_id, {}), **updated_link}
        new_data = {**data, "link_details": new_details}
        self.coordinator.async_set_updated_data(new_data)
