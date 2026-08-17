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
        self.org_id = None
        self.orgs = []
        self.device_id = None
        self.device_name = None
        self.devices = []
        self.sims = []
        self._devices_error = None

    async def _api_get(self, path, params=None):
        """GET helper. Returns (json_body, error_key). error_key is None on success."""
        session = async_get_clientsession(self.hass)
        auth = BasicAuth("apikey", self.api_key)
        try:
            resp = await session.get(f"{API_BASE}{path}", auth=auth, params=params, timeout=10)
        except Exception as err:
            _LOGGER.debug("Error calling Hologram API %s: %s", path, err)
            return None, "connection_error"

        if resp.status == 401:
            return None, "invalid_auth"
        if resp.status != 200:
            return None, "connection_error"

        body = await resp.json()
        if not body.get("success"):
            return None, "invalid_auth"
        return body, None

    async def async_step_user(self, user_input=None):
        """Ask for the API key and figure out which organization(s) it can access."""
        errors = {}

        if user_input is not None:
            self.api_key = user_input["api_key"]

            body, error = await self._api_get("/organizations", {"limit": 100})
            if error:
                errors["base"] = error
            else:
                orgs = body.get("data", [])
                if len(orgs) > 1:
                    self.orgs = orgs
                    return await self.async_step_select_org()

                self.org_id = orgs[0]["id"] if orgs else None
                result = await self._list_devices()
                if result is not None:
                    return result
                errors["base"] = self._devices_error

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_select_org(self, user_input=None):
        """Let the user pick which organization to use, if the API key has access to more than one."""
        errors = {}

        if user_input is not None:
            self.org_id = int(user_input["org_id"])
            result = await self._list_devices()
            if result is not None:
                return result
            errors["base"] = self._devices_error

        return self.async_show_form(
            step_id="select_org",
            data_schema=self._get_org_schema(),
            errors=errors,
        )

    async def _list_devices(self):
        """Fetch the device list for self.org_id and move to device selection.

        Returns the async_step_select_device() result on success, or None on
        failure (with self._devices_error set to the error key to show).
        """
        params = {"limit": 250}
        if self.org_id is not None:
            params["orgid"] = self.org_id

        body, error = await self._api_get("/devices", params)
        if error:
            self._devices_error = error
            return None

        self.devices = [d for d in body.get("data", []) if d.get("id") is not None]
        if not self.devices:
            self._devices_error = "no_devices_found"
            return None

        return await self.async_step_select_device()

    async def async_step_select_device(self, user_input=None):
        """Let the user pick which device to integrate from the discovered list."""
        errors = {}

        if user_input is not None:
            self.device_id = int(user_input["device_id"])
            device = next(
                (d for d in self.devices if d.get("id") == self.device_id), None
            )
            self.device_name = (device or {}).get("name") or f"hologram_{self.device_id}"
            self.org_id = (device or {}).get("orgid", self.org_id)

            body, error = await self._api_get(f"/devices/{self.device_id}")
            if error:
                errors["base"] = "device_not_found" if error == "connection_error" else error
            else:
                device_data = body.get("data", {})
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
                    "orgid": self.org_id,
                    "device_id": self.device_id,
                    "name": self.device_name,
                    "selected_sims": selected_sim_ids,
                },
            )

        return self.async_show_form(
            step_id="select_sims",
            data_schema=self._get_sims_schema(),
        )

    def _get_org_schema(self):
        """Generate schema for organization selection."""
        org_options = {
            str(o["id"]): o.get("name") or str(o["id"])
            for o in self.orgs
        }

        return vol.Schema({
            vol.Required("org_id"): vol.In(org_options),
        })

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
