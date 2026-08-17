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

from .const import DOMAIN, API_BASE, DEFAULT_SCAN_INTERVAL, SLOW_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "switch", "notify", "device_tracker", "number"]


def _unwrap_single(data):
    """Some Hologram endpoints wrap even a single-object "data" in a one-item list."""
    if isinstance(data, list):
        return data[0] if data else None
    return data


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up hologram from a config entry."""
    api_key = entry.data.get("api_key")
    device_id = entry.data.get("device_id")
    org_id = entry.data.get("orgid")
    selected_sims = entry.data.get("selected_sims", [])

    session = async_get_clientsession(hass)
    auth = BasicAuth("apikey", api_key)

    async def async_update_data() -> dict:
        """Fetch live device/SIM state - polled frequently."""
        try:
            # Get device details (includes links with all SIM info: state,
            # overagelimit, smslimit, datathreshold, cur/last_billing_data_used)
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
            if selected_sims:
                links = device.get("links", {}).get("cellular", [])
                filtered_links = [
                    link for link in links
                    if str(link.get("id")) in selected_sims
                ]
                device["links"] = {"cellular": filtered_links}

            return {"device": device}

        except UpdateFailed:
            raise
        except Exception as err:
            _LOGGER.error("Update error: %s", err)
            raise UpdateFailed(str(err))

    async def async_update_data_slow() -> dict:
        """Fetch slow-changing account/history data - polled infrequently."""
        balance = None
        if org_id is not None:
            try:
                url_balance = f"{API_BASE}/organizations/{org_id}/balance"
                resp = await session.get(url_balance, auth=auth, timeout=10)
                if resp.status == 200:
                    balance_json = await resp.json()
                    if balance_json.get("success"):
                        balance = balance_json.get("data")
            except Exception as err:
                _LOGGER.debug("Error fetching Hologram balance: %s", err)

        locations = {}
        try:
            resp = await session.get(f"{API_BASE}/devices/locations", auth=auth, timeout=10)
            if resp.status == 200:
                loc_json = await resp.json()
                if loc_json.get("success"):
                    locations = {
                        str(d.get("deviceid")): d for d in loc_json.get("data", []) if d.get("deviceid") is not None
                    }
        except Exception as err:
            _LOGGER.debug("Error fetching Hologram device locations: %s", err)

        history = {}
        link_details = {}
        for link_id in selected_sims:
            try:
                resp = await session.get(
                    f"{API_BASE}/links/cellular/{link_id}/history",
                    auth=auth,
                    params={"limit": 1},
                    timeout=10,
                )
                if resp.status == 200:
                    hist_json = await resp.json()
                    if hist_json.get("success") and hist_json.get("data"):
                        # Keyed by int to match link ids as read from the device
                        # detail response elsewhere (selected_sims itself is
                        # string-typed, only used here to build the URL)
                        history[int(link_id)] = hist_json["data"][0]
            except Exception as err:
                _LOGGER.debug("Error fetching history for SIM %s: %s", link_id, err)

            try:
                # GET /devices/{id} doesn't reliably reflect datathreshold, even
                # though it does for overagelimit/smslimit - read it from the
                # single-link endpoint instead, which does.
                resp = await session.get(
                    f"{API_BASE}/links/cellular/{link_id}",
                    auth=auth,
                    timeout=10,
                )
                if resp.status == 200:
                    link_json = await resp.json()
                    if link_json.get("success") and link_json.get("data"):
                        detail = _unwrap_single(link_json["data"])
                        if isinstance(detail, dict):
                            link_details[int(link_id)] = detail
            except Exception as err:
                _LOGGER.debug("Error fetching link details for SIM %s: %s", link_id, err)

        sms_usage = []
        if selected_sims:
            try:
                resp = await session.get(
                    f"{API_BASE}/usage/sms",
                    auth=auth,
                    params={"linkids": ",".join(selected_sims), "limit": 500},
                    timeout=15,
                )
                if resp.status == 200:
                    sms_json = await resp.json()
                    if sms_json.get("success"):
                        sms_usage = sms_json.get("data", [])
            except Exception as err:
                _LOGGER.debug("Error fetching Hologram SMS usage: %s", err)

        daily_usage = []
        monthly_usage = []
        if selected_sims:
            try:
                resp = await session.get(
                    f"{API_BASE}/usage/data/daily",
                    auth=auth,
                    params={"linkids": ",".join(selected_sims), "limit": 60},
                    timeout=15,
                )
                if resp.status == 200:
                    daily_json = await resp.json()
                    if daily_json.get("success"):
                        daily_usage = daily_json.get("data", [])
            except Exception as err:
                _LOGGER.debug("Error fetching Hologram daily usage: %s", err)

            try:
                resp = await session.get(
                    f"{API_BASE}/usage/data/monthly",
                    auth=auth,
                    params={"linkids": ",".join(selected_sims), "limit": 12},
                    timeout=15,
                )
                if resp.status == 200:
                    monthly_json = await resp.json()
                    if monthly_json.get("success"):
                        monthly_usage = monthly_json.get("data", [])
            except Exception as err:
                _LOGGER.debug("Error fetching Hologram monthly usage: %s", err)

        return {
            "balance": balance,
            "locations": locations,
            "history": history,
            "link_details": link_details,
            "sms_usage": sms_usage,
            "daily_usage": daily_usage,
            "monthly_usage": monthly_usage,
        }

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

    slow_coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"hologram_{device_id}_slow",
        update_method=async_update_data_slow,
        update_interval=timedelta(seconds=SLOW_SCAN_INTERVAL),
    )

    try:
        await slow_coordinator.async_config_entry_first_refresh()
    except Exception as err:
        _LOGGER.warning("Initial slow-data refresh failed for %s: %s", device_id, err)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        "slow_coordinator": slow_coordinator,
        "auth": auth,
        "device_id": device_id,
    }

    # forward to sensor/switch/notify/device_tracker/number platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
