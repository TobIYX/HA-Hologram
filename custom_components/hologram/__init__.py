"""Hologram integration - DataUpdateCoordinator + services."""
from __future__ import annotations

import asyncio
import logging
import json
from datetime import timedelta
from aiohttp import BasicAuth

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, API_BASE, DEFAULT_SCAN_INTERVAL, SERVICE_PAUSE, SERVICE_UNPAUSE

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up hologram from a config entry."""
    api_key = entry.data.get("api_key")
    device_id = entry.data.get("device_id")

    session = async_get_clientsession(hass)
    auth = BasicAuth("apikey", api_key)

    async def async_update_data() -> dict:
        """Fetch all available device data from Hologram."""
        try:
            # Get device details (includes links with all SIM info)
            url = f"{API_BASE}/devices/{device_id}"
            resp = await session.get(url, auth=auth, timeout=10)
            if resp.status != 200:
                text = await resp.text()
                raise UpdateFailed(f"Error fetching device: {resp.status} {text}")
            dev_json = await resp.json()
            if not dev_json.get("success", False):
                raise UpdateFailed(f"Device API error: {dev_json.get('error')}")
            device = dev_json.get("data") or {}

            # Get last message
            url_msg = f"{API_BASE}/csr/data"
            params = {"deviceid": device_id, "limit": 1}
            resp = await session.get(url_msg, params=params, auth=auth, timeout=10)
            last_msg = None
            if resp.status == 200:
                msg_json = await resp.json()
                if msg_json.get("success") and msg_json.get("data"):
                    last_msg = msg_json.get("data")[0]

            # Get all usage data (no time filter - let API return what it has)
            usage_data = []
            links = []
            try:
                for l in (device.get("links") or {}).get("cellular", []):
                    if l and l.get("id"):
                        links.append(str(l.get("id")))
            except Exception:
                pass

            if links:
                url_usage = f"{API_BASE}/usage/data/"
                params = {"linkids": ",".join(links), "limit": 500}
                resp = await session.get(url_usage, params=params, auth=auth, timeout=30)
                if resp.status == 200:
                    usage_json = await resp.json()
                    if usage_json.get("success") and usage_json.get("data"):
                        usage_data = usage_json.get("data", [])

            return {
                "device": device,
                "last_message": last_msg,
                "usage_data": usage_data,
                "links": links,
            }

        except UpdateFailed:
            raise
        except Exception as err:
            _LOGGER.error("Update error: %s", err)
            raise UpdateFailed(str(err))

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"hologram_{device_id}",
        update_method=async_update_data,
        update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
    )

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        raise ConfigEntryNotReady from err

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        "auth": auth,
        "device_id": device_id
    }

    # forward to sensor platform
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # register services to pause/unpause by device id
    async def _set_state(call, state: str):
        deviceid = call.data.get("device_id") or device_id
        url = f"{API_BASE}/devices/{deviceid}/state"
        try:
            resp = await session.post(url, json={"state": state}, auth=auth, timeout=10)
            if resp.status != 200:
                text = await resp.text()
                _LOGGER.error("Failed to set state %s for %s: %s %s", state, deviceid, resp.status, text)
                return
            j = await resp.json()
            if not j.get("success"):
                _LOGGER.error("API error setting state: %s", j.get("error"))
        except Exception as err:
            _LOGGER.error("Error calling Hologram state API: %s", err)

    hass.services.async_register(DOMAIN, SERVICE_PAUSE, lambda call: asyncio.create_task(_set_state(call, "pause")))
    hass.services.async_register(DOMAIN, SERVICE_UNPAUSE, lambda call: asyncio.create_task(_set_state(call, "live")))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
