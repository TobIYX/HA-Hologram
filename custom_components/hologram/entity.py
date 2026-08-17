"""Shared base entity - groups all Hologram sensors/switches under one HA device per Hologram device."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


class HologramEntity(CoordinatorEntity):
    """Base entity that ties itself to the HA device representing one Hologram device."""

    def __init__(self, coordinator, device_id, device_name):
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(device_id))},
            name=device_name,
            manufacturer="Hologram",
            model="Cellular IoT Device",
            configuration_url="https://dashboard.hologram.io/",
        )
