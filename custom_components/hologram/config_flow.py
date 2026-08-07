"""Config flow for Hologram integration."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
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

    async def async_step_user(self, user_input=None):
        """Handle a flow initiated by the user."""
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=STEP_USER_DATA_SCHEMA,
            )

        unique_id = str(user_input["device_id"])
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=user_input.get("name", f"hologram_{unique_id}"),
            data=user_input,
        )
