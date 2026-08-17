"""Notify platform for Hologram - send a message to a device via cloud-to-device SMS."""
from __future__ import annotations

import logging

from homeassistant.components.notify import NotifyEntity
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

    async_add_entities([HologramNotify(coordinator, device_id, device_name, auth)])


class HologramNotify(HologramEntity, NotifyEntity):
    """Send a message to the device, delivered as an inbound SMS via the Hologram cloud."""

    def __init__(self, coordinator, device_id, device_name, auth):
        super().__init__(coordinator, device_id, device_name)
        self._auth = auth
        self._attr_name = f"Hologram {device_id} Send Message"
        self._attr_unique_id = f"hologram_{device_id}_notify"

    async def async_send_message(self, message: str, title: str | None = None) -> None:
        session = async_get_clientsession(self.hass)
        url = f"{API_BASE}/sms/incoming"
        body = f"{title}: {message}" if title else message
        payload = {"deviceid": self._device_id, "body": body}

        try:
            resp = await session.post(url, json=payload, auth=self._auth, timeout=10)
        except Exception as err:
            raise HomeAssistantError(
                f"Error contacting Hologram API for device {self._device_id}: {err}"
            ) from err

        if resp.status != 200:
            text = await resp.text()
            raise HomeAssistantError(
                f"Failed to send message to device {self._device_id}: {resp.status} {text}"
            )

        response_body = await resp.json()
        if not response_body.get("success"):
            raise HomeAssistantError(
                f"Hologram API error sending message to device {self._device_id}: {response_body.get('error')}"
            )
