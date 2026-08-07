"""Config flow for Hologram integration."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from aiohttp import BasicAuth
from .const import DOMAIN, API_BASE

STEP_USER_DATA_SCHEMA = vol.Schema({
    vol.Required("api_key"): str,
    vol.Required("device_id"): int,
    vol.Optional("name", default="hologram"): str,
})


class HologramConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        """Initialize the config flow."""
        self.api_key = None
        self.device_id = None
        self.device_name = None
        self.sims = []

    async def async_step_user(self, user_input=None):
        """Handle a flow initiated by the user."""
        errors = {}

        if user_input is not None:
            self.api_key = user_input["api_key"]
            self.device_id = user_input["device_id"]
            self.device_name = user_input.get("name", f"hologram_{self.device_id}")

            # Fetch SIMs from device
            try:
                session = async_get_clientsession(self.hass)
                auth = BasicAuth("apikey", self.api_key)
                url = f"{API_BASE}/devices/{self.device_id}"
                resp = await session.get(url, auth=auth, timeout=10)

                if resp.status != 200:
                    errors["base"] = "device_not_found"
                    return self.async_show_form(
                        step_id="user",
                        data_schema=STEP_USER_DATA_SCHEMA,
                        errors=errors,
                    )

                dev_json = await resp.json()
                if not dev_json.get("success"):
                    errors["base"] = "invalid_auth"
                    return self.async_show_form(
                        step_id="user",
                        data_schema=STEP_USER_DATA_SCHEMA,
                        errors=errors,
                    )

                # Extract SIMs from device data
                device = dev_json.get("data", {})
                links = device.get("links", {}).get("cellular", [])

                if not links:
                    errors["base"] = "no_sims_found"
                    return self.async_show_form(
                        step_id="user",
                        data_schema=STEP_USER_DATA_SCHEMA,
                        errors=errors,
                    )

                # Store SIMs for next step
                self.sims = [
                    {
                        "id": str(link.get("id", "")),
                        "sim": link.get("sim", "Unknown"),
                        "msisdn": link.get("msisdn", "Unknown"),
                        "state": link.get("state", "Unknown"),
                    }
                    for link in links
                ]

                # Move to SIM selection step
                return await self.async_step_select_sims()

            except Exception as err:
                errors["base"] = "connection_error"

        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=STEP_USER_DATA_SCHEMA,
                errors=errors,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
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

    def _get_sims_schema(self):
        """Generate schema for SIM selection."""
        sim_options = {
            sim["id"]: f"{sim['msisdn']} ({sim['sim']}) - {sim['state']}"
            for sim in self.sims
        }

        return vol.Schema({
            vol.Required("sims"): cv.multi_select(sim_options),
        })
