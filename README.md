# Launchpad Controller for [Home Assistant](https://www.home-assistant.io/) using MQTT  

## Description
This Project makes it possible to use a Novation Launchpad with Home Assistant using Home Assistant.
It is running in Python using [launchpad.py](https://github.com/FMMT666/launchpad.py/tree/master).

## Prerequisites
- Running Home Assistant Instance
- Running MQTT Broker

## Installation
1. Clone this repository in your home folder:
```bash
git clone https://github.com/ey-jo/launchpad_ha
```

2. Rename [.env.example](.env.example) to [.env](.env) and make adjustments if necessary. You might need to change the path in [launchpad.service](launchpad.service)

3. Execute the [installer](install.sh)

## Starting
Start the service
```bash
sudo systemctl start launchpad.service
```

## Updating
```bash
git pull
sudo systemctl restart launchpad.service
```

## Configuration in Home Assistant
A couple of examples can be found in [ha_templates](ha_templates).

The MQTT device creates a **Button Lock** entity, a **Lock Button** selector, and
an **Auto Lock Timer** number entity through MQTT discovery. Select any Launchpad
button (or **Disabled**) in **Lock Button**. While locked, button events are
suppressed; hold the selected button to unlock, and press it once to lock again.
The timer is in seconds and locks the device again after it has been unlocked;
set it to `0` to disable automatic locking. These settings can be changed at any
time in Home Assistant and are saved in `device_settings.json` beside `main.py`.

The initial values can also be set in `.env` with `LOCK_BUTTON` and
`AUTO_LOCK_SECONDS`. The device starts locked; it can be unlocked from Home
Assistant or with a long press of the selected button.

Lock discovery, event handling, and persisted lock settings are implemented in
[`lock_manager.py`](lock_manager.py); `main.py` delegates lock messages and
button events to it. Press classification (single, double, and long presses) is
handled separately in [`button_events.py`](button_events.py). A regular
single-click event is sent after the double-click window expires so a double
click does not also trigger a single-click automation; the configured lock
button still locks immediately on a single press.

The sample `.env.example` uses `DEVICE_ID=launchpad`, which is also the device
ID used in the MQTT topics in [ha_templates](ha_templates).