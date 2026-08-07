"""Config flow for Hologram integration."""
from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from aiohttp import BasicAuth
from .const import DOMAIN, API_BASE

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema({
    vol.Required("api_key"): str,
})


class HologramConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        """Initialize the config flow."""
        self.api_key = None
        self.device_id = None
        self.device_name = None
        self.devices = []
        self.sims = []

    async def async_step_user(self, user_input=None):
        """Ask for the API key and list the devices it can access."""
        errors = {}

        if user_input is not None:
            self.api_key = user_input["api_key"]

            try:
                session = async_get_clientsession(self.hass)
                auth = BasicAuth("apikey", self.api_key)
                resp = await session.get(
                    f"{API_BASE}/devices",
                    auth=auth,
                    params={"limit": 250},
                    timeout=10,
                )

                if resp.status == 401:
                    errors["base"] = "invalid_auth"
                elif resp.status != 200:
                    errors["base"] = "connection_error"
                else:
                    body = await resp.json()
                    if not body.get("success"):
                        errors["base"] = "invalid_auth"
                    else:
                        self.devices = [
                            d for d in body.get("data", []) if d.get("id") is not None
                        ]
                        if not self.devices:
                            errors["base"] = "no_devices_found"
                        else:
                            return await self.async_step_select_device()

            except Exception as err:
                _LOGGER.debug("Error listing Hologram devices: %s", err)
                errors["base"] = "connection_error"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_select_device(self, user_input=None):
        """Let the user pick which device to integrate from the discovered list."""
        errors = {}

        if user_input is not None:
            self.device_id = int(user_input["device_id"])
            device = next(
                (d for d in self.devices if d.get("id") == self.device_id), None
            )
            self.device_name = (device or {}).get("name") or f"hologram_{self.device_id}"

            try:
                session = async_get_clientsession(self.hass)
                auth = BasicAuth("apikey", self.api_key)
                url = f"{API_BASE}/devices/{self.device_id}"
                resp = await session.get(url, auth=auth, timeout=10)

                if resp.status != 200:
                    errors["base"] = "device_not_found"
                else:
                    dev_json = await resp.json()
                    if not dev_json.get("success"):
                        errors["base"] = "device_not_found"
                    else:
                        device_data = dev_json.get("data", {})
                        links = device_data.get("links", {}).get("cellular", [])

                        if not links:
                            errors["base"] = "no_sims_found"
                        else:
                            self.sims = [
                                {
                                    "id": str(link.get("id", "")),
                                    "sim": link.get("sim", "Unknown"),
                                    "msisdn": link.get("msisdn", "Unknown"),
                                    "state": link.get("state", "Unknown"),
                                }
                                for link in links
                            ]
                            return await self.async_step_select_sims()

            except Exception as err:
                _LOGGER.debug(
                    "Error fetching Hologram device %s: %s", self.device_id, err
                )
                errors["base"] = "connection_error"

        return self.async_show_form(
            step_id="select_device",
            data_schema=self._get_device_schema(),
            errors=errors,
        )

    async def async_step_select_sims(self, user_input=None):
        """Handle SIM selection."""
        if user_input is not None:
            selected_sim_ids = user_input.get("sims", [])

            if not selected_sim_ids:
                return self.async_show_form(
                    step_id="select_sims",
                    data_schema=self._get_sims_schema(),
                    errors={"base": "no_sims_selected"},
                )

            unique_id = f"{self.device_id}_{','.join(selected_sim_ids)}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=self.device_name,
                data={
                    "api_key": self.api_key,
                    "device_id": self.device_id,
                    "name": self.device_name,
                    "selected_sims": selected_sim_ids,
                },
            )

        return self.async_show_form(
            step_id="select_sims",
            data_schema=self._get_sims_schema(),
        )

    def _get_device_schema(self):
        """Generate schema for device selection."""
        device_options = {
            str(d["id"]): f"{d.get('name') or 'Unnamed'} ({d['id']})"
            for d in self.devices
        }

        return vol.Schema({
            vol.Required("device_id"): vol.In(device_options),
        })

    def _get_sims_schema(self):
        """Generate schema for SIM selection."""
        sim_options = {
            sim["id"]: f"{sim['msisdn']} ({sim['sim']}) - {sim['state']}"
            for sim in self.sims
        }

        return vol.Schema({
            vol.Required("sims"): cv.multi_select(sim_options),
        })
