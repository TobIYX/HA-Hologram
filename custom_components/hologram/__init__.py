"""Hologram integration - DataUpdateCoordinator."""
from __future__ import annotations

import logging
from datetime import timedelta
from aiohttp import BasicAuth

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, API_BASE, DEFAULT_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "switch", "notify"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up hologram from a config entry."""
    api_key = entry.data.get("api_key")
    device_id = entry.data.get("device_id")
    org_id = entry.data.get("orgid")

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

            # Filter to selected SIMs only
            selected_sims = entry.data.get("selected_sims", [])
            if selected_sims:
                links = device.get("links", {}).get("cellular", [])
                filtered_links = [
                    link for link in links
                    if str(link.get("id")) in selected_sims
                ]
                device["links"] = {"cellular": filtered_links}

            # Get organization balance
            balance = None
            if org_id is not None:
                url_balance = f"{API_BASE}/organizations/{org_id}/balance"
                resp = await session.get(url_balance, auth=auth, timeout=10)
                if resp.status == 200:
                    balance_json = await resp.json()
                    if balance_json.get("success"):
                        balance = balance_json.get("data")

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
                "balance": balance,
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

    # forward to sensor/switch/notify platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
