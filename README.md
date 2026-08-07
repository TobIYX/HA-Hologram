# HA-Hologram

A Home Assistant custom integration for [Hologram](https://www.hologram.io/) IoT SIM cards: usage tracking, billing cycle data, and (in progress) full control over your Hologram devices via the Dashboard REST API.

## Origin

This project started as a private continuation of [oxygenlithium/ha-hologram](https://github.com/oxygenlithium/ha-hologram) by Oli Crask, which provided the original minimal `custom_components/sensor/hologram.py` platform. All functionality since has been rewritten as a proper Home Assistant integration (config flow, `DataUpdateCoordinator`, services), but the origin and its [MIT license](LICENSE) are credited and preserved here.

## Status

Private work-in-progress. The goal is a full-featured Hologram integration (usage sensors, device auto-discovery, pause/resume SIMs, and more) that may eventually be published for the Home Assistant community.
