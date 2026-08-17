"""Switches for Hologram integration - pause/resume individual SIMs."""
from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, API_BASE

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    auth = data["auth"]
    device_id = entry.data.get("device_id")

    links = coordinator.data.get("device", {}).get("links", {}).get("cellular", [])
    async_add_entities(
        [
            HologramSimSwitch(coordinator, device_id, link.get("id"), auth)
            for link in links
        ],
        True,
    )


class HologramSimSwitch(CoordinatorEntity, SwitchEntity):
    """Pause/resume a single Hologram SIM (cellular link)."""

    def __init__(self, coordinator, device_id, link_id, auth):
        super().__init__(coordinator)
        self._device_id = device_id
        self._link_id = link_id
        self._auth = auth
        self._attr_unique_id = f"hologram_{device_id}_sim_{link_id}"

    def _link(self):
        links = self.coordinator.data.get("device", {}).get("links", {}).get("cellular", [])
        return next((l for l in links if l.get("id") == self._link_id), None)

    @property
    def name(self):
        link = self._link()
        msisdn = (link or {}).get("msisdn") or self._link_id
        return f"Hologram {self._device_id} SIM {msisdn}"

    @property
    def available(self):
        return self.coordinator.last_update_success and self._link() is not None

    @property
    def is_on(self):
        link = self._link()
        if not link:
            return None
        return "PAUSE" not in str(link.get("state", "")).upper()

    @property
    def extra_state_attributes(self):
        link = self._link()
        if not link:
            return {}
        return {
            "hologram_state": link.get("state"),
            "sim": link.get("sim"),
            "msisdn": link.get("msisdn"),
        }

    async def async_turn_on(self, **kwargs):
        await self._set_state("live")

    async def async_turn_off(self, **kwargs):
        await self._set_state("pause")

    async def _set_state(self, state: str):
        session = async_get_clientsession(self.hass)
        url = f"{API_BASE}/links/cellular/{self._link_id}/state"
        try:
            resp = await session.post(url, json={"state": state}, auth=self._auth, timeout=10)
        except Exception as err:
            raise HomeAssistantError(
                f"Error contacting Hologram API for SIM {self._link_id}: {err}"
            ) from err

        if resp.status != 200:
            text = await resp.text()
            raise HomeAssistantError(
                f"Failed to set state {state} for SIM {self._link_id}: {resp.status} {text}"
            )

        body = await resp.json()
        if not body.get("success"):
            raise HomeAssistantError(
                f"Hologram API error setting state for SIM {self._link_id}: {body.get('error')}"
            )

        await self.coordinator.async_request_refresh()
