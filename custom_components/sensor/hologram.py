"""Deprecated local hologram sensor shim.

This file is a compatibility shim. The hologram integration has moved to
custom_components/hologram (config flow + DataUpdateCoordinator). Please
remove this platform file to avoid duplicate entities.
"""

import logging

_LOGGER = logging.getLogger(__name__)


def setup_platform(hass, config, add_entities, discovery_info=None):
    _LOGGER.warning("Deprecated hologram platform in custom_components/sensor/hologram.py detected. Use the hologram integration (config flow) instead.")
    return
