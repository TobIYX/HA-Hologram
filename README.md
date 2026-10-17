# HA-Hologram

**Status: Public Beta (v0.1.0)** — functional and actively used, but young; expect rough edges and breaking changes before a 1.0.

A Home Assistant custom integration for [Hologram](https://www.hologram.io/) IoT SIM cards — usage tracking, account balance, SIM pause/resume, sending messages to devices, and more, via the Hologram Dashboard REST API.

**This is not affiliated with, endorsed by, or supported by Hologram.** "Hologram" and its logo are trademarks of their respective owner, used here only to identify the service this integration connects to.

## AI-assisted development

This integration was built largely through "vibe coding" — iterating with an AI coding assistant (Claude), including writing most of the code, researching the Hologram API, and debugging issues against a live account. It has been tested by the maintainer on their own setup, but has **not** had a formal human-led code review or security audit. Use at your own risk, and please open an issue if you hit something that looks wrong — reports and pull requests are welcome.

## Features

- **Sensors** per SIM: current/previous billing-cycle usage, today's/this month's usage, SMS usage count, last pause/resume event
- **Switches**: pause/resume SIMs. As of Hologram's 2026 API changes, this acts at the **device** level (Hologram deprecated the per-SIM state endpoint) — on a device with more than one selected SIM, toggling any one switch pauses/resumes all SIMs on that device
- **Notify**: send a message to a device (delivered as an inbound SMS via the Hologram cloud)
- **Number**: adjust each SIM's data overage limit, SMS limit, and usage alert threshold directly from Home Assistant
- **Device tracker**: approximate device location (cell-tower based, not GPS)
- **Organization balance** sensor (useful for prepaid accounts)
- Auto-discovery during setup: enter your API key, pick an organization (if you have more than one) and device, then choose which SIMs to track — no manual IDs needed
- Multiple devices/SIMs are supported by adding the integration again per device

## Installation

### HACS (recommended)

1. In HACS, add this repository as a [custom repository](https://hacs.xyz/docs/faq/custom_repositories/) (category: Integration)
2. Install "Hologram", then restart Home Assistant

### Manual

1. Copy `custom_components/hologram` into your Home Assistant `custom_components` directory
2. Restart Home Assistant

## Setup

Settings → Devices & Services → Add Integration → "Hologram", then enter your [Hologram API key](https://dashboard.hologram.io/) and follow the prompts.

## Known limitations

- Only tested against a single Hologram account/plan. The (unofficial, community-maintained) Hologram API docs have turned out to be inaccurate in a few places during development (e.g. request field names, response shapes) — behavior may differ on other plans or account types.
- Changing a SIM's paid data plan is intentionally not implemented — too risky for an automatable entity given the real billing consequences of a mistaken change.
- Pause/resume switches act on the whole device, not the individual SIM, as of Hologram's 2026 deprecation of the per-SIM state endpoint (see Features above).

## Origin

This project started as a private continuation of [oxygenlithium/ha-hologram](https://github.com/oxygenlithium/ha-hologram) by Oli Crask, which provided the original minimal `custom_components/sensor/hologram.py` platform. All functionality since has been rewritten as a proper Home Assistant integration (config flow, `DataUpdateCoordinator`, multiple entity platforms), but the origin and its [MIT license](LICENSE) are credited and preserved here.
