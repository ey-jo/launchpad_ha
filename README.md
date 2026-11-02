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
The recommended setup uses the reusable blueprints below. The files in
[ha_templates](ha_templates) are optional copy-paste examples; you do not need
to install or use them when you use the blueprints.

### Install the blueprints

Home Assistant must have its MQTT integration set up and connected to the same
broker as the Launchpad controller.

Copy the blueprint files from this repository into your Home Assistant
configuration directory, preserving these paths:

```text
<Home Assistant config>/
└── blueprints/
    ├── automation/
    │   └── launchpad/
    │       └── button_action.yaml
    └── script/
        └── launchpad/
            ├── scroll_text.yaml
            ├── set_all_leds.yaml
            └── set_led.yaml
```

For example, with the File editor add-on, create the folders under
`/config/blueprints/` and upload or paste the files into them. You can also
transfer the files using a network share or another file-management method.
After copying, open **Settings → Automations & scenes → Blueprints** and reload
the blueprints if that option is available; otherwise restart Home Assistant.

### Control lights, covers, switches, and other devices

Use the [Launchpad button action blueprint](blueprints/automation/launchpad/button_action.yaml)
to create one automation per button/press combination:

1. In **Settings → Automations & scenes → Blueprints**, find **Launchpad button
   action** and choose **Create automation**.
2. Select the Launchpad button and **single click**, **double click**, or
   **long press**.
3. In **Actions**, choose **Add action** and select the device or action you
   want. For example, use a light's **Toggle** action, **Turn on** with a
   brightness level, a cover's **Open** or **Close** action, or a switch,
   scene, or script action.
4. Save the automation. Repeat with a different button or press type to add
   more controls.

The event topic defaults to `device/launchpad/event/state`. If your `.env` has
a different `DEVICE_ID`, replace `launchpad` in the topic with that ID.

The controller starts locked. With the default `LOCK_BUTTON="up"`, hold the
Launchpad's **up** button to unlock it; a single press locks it again. While
locked, button events do not trigger automations. You can change the lock
button or disable it using the **Lock Button** entity in Home Assistant. Do not
assign an automation to the active lock button unless you disable or change the
lock button.

### Control the Launchpad display

Create scripts from these script blueprints in **Settings → Automations &
scenes → Blueprints**:

- [`Set LED`](blueprints/script/launchpad/set_led.yaml): set one grid position,
  color, and effect.
- [`Set all LEDs`](blueprints/script/launchpad/set_all_leds.yaml): fill the
  board with a color and brightness, or clear it.
- [`Scroll text`](blueprints/script/launchpad/scroll_text.yaml): display text
  with a chosen direction and color.

For each blueprint, choose **Create script**, set the MQTT command topic, and
save. The default is `device/launchpad/light/set`; replace `launchpad` with
your `DEVICE_ID` if needed. The created scripts can be run from Home Assistant
or called by automations. Their fields let you enter positions, colors,
brightness, effects, and text.

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

If the MQTT broker disconnects, all Launchpad LEDs blink red until the
connection is restored.

Lock discovery, event handling, and persisted lock settings are implemented in
[`lock_manager.py`](lock_manager.py); `main.py` delegates lock messages and
button events to it. Press classification (single, double, and long presses) is
handled separately in [`button_events.py`](button_events.py). A regular
single-click event is sent after the double-click window expires so a double
click does not also trigger a single-click automation; the configured lock
button still locks immediately on a single press.

The sample `.env.example` uses `DEVICE_ID=launchpad`, which is also the device
ID used in the MQTT topics in [ha_templates](ha_templates).