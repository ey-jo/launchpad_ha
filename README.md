# Launchpad Controller for [Home Assistant](https://www.home-assistant.io/) using MQTT

## Description

This project makes it possible to use a Novation Launchpad with Home Assistant
over MQTT. It runs in Python using
[launchpad.py](https://github.com/FMMT666/launchpad.py/tree/master).

## Prerequisites

- Running Home Assistant instance
- Running MQTT broker

## Installation

1. Clone this repository in your home folder:

   ```bash
   git clone https://github.com/ey-jo/launchpad_ha
   ```

2. Rename [.env.example](.env.example) to `.env` and adjust settings if needed.
   You might need to change the path in [launchpad.service](launchpad.service).
3. Execute the [installer](install.sh).

## Starting

Start the service:

```bash
sudo systemctl start launchpad.service
```

The service waits for the network to come online and retries after startup
failures. If it still cannot reach the broker, verify the broker address and
network route from the machine running this service.

## Updating

```bash
git pull
sudo systemctl restart launchpad.service
```

## Configuration in Home Assistant

Set up the Home Assistant MQTT integration and connect it to the same broker as
the Launchpad controller. Copy the files in [blueprints](blueprints) into the
matching folders under `<Home Assistant config>/blueprints/`, preserving the
`automation/launchpad` and `script/launchpad` directories. Reload blueprints
from **Settings → Automations & scenes → Blueprints**, or restart Home Assistant.

The event topic defaults to `device/launchpad/event/state` and the display
command topic defaults to `device/launchpad/light/set`. If `.env` uses a
different `DEVICE_ID`, replace `launchpad` in both topics with that ID.

### Control entities from the Launchpad

Use the [Launchpad entity control blueprint](blueprints/automation/launchpad/entity_control.yaml)
to create an automation for a **button**, **cover**, **fan**, **light**,
**select**, or **switch** entity. The blueprint selects the entity domain and
provides the domain-appropriate mapping fields.

For covers, fans, and lights, choose **row**, **column**, or **button**:

- In row mode, choose a row index (`0..7`), corresponding to grid `y=1..8`.
  Single-clicking grid positions `x=0..7` sets the entity to **1/9 through
  8/9** (about 11.1% to 88.9%). Double-click the leftmost cell to turn the
  entity off; double-click the rightmost cell to set it to 100%. Special
  buttons are ignored.
- In column mode, choose a column index (`0..7`, corresponding to `x`). Grid
  positions `y=1..8` set the entity to **8/9 at the top through 1/9 at the
  bottom**. Double-click the bottom cell to turn the entity off; double-click
  the top cell to set it to 100%. Special buttons are ignored.
- In button mode, the chosen physical button sets the configured single-button
  value using the selected press type.

Enable **Only run when the lock is unlocked** and select any Home Assistant
lock entity to prevent this automation from running while that lock is locked.
The option is disabled by default.

In button mode, lights use the configured single-button value, with 0% turning
them off. The automation mirrors an entity's current value on the selected
row/column: at 60%, about 60% of the eight LEDs are active. Choose an active
and inactive RGB color; black (`[0, 0, 0]`) leaves inactive LEDs unlit. An
optional JSON gradient can assign different active colors along the bar, for
example
`[[0,0,255],[0,255,0],[255,0,0]]`.

Button and switch entities use explicit button mappings (one per line). Button
mappings have the form `button,event_type`, for example
`grid_0_0,single_click`. Switch mappings add the desired action:
`button,event_type,on`, `button,event_type,off`, or
`button,event_type,toggle`. Select mappings have the form
`button,event_type,option`; option names must match the entity. Select options
can have per-option colors via a JSON object such as
`{"Home":[0,255,0],"Away":[255,0,0]}`. Optional per-option RGB sequences are
also accepted as JSON, e.g.
`{"Home":[[0,255,0],[0,0,255]]}`; the sequence runs for the configured number
of cycles when that option becomes selected.

Use the physical labels from the controller: function buttons use names such
as `up`, `session`, `volume`, and `record_arm`; other positions use
`grid_x_y`. Coordinates span 0–8 in both directions, including the top and
right-side function buttons. Press types are `single_click`, `double_click`,
and `long_press`.

The [copy-paste example](ha_templates/automation_entity_control_example.yaml)
shows a cover controlled by the first row.

### Display colors, patterns, and notifications

Create scripts from these blueprints:

- [Static color](blueprints/script/launchpad/set_led.yaml) paints one button,
  row, column, or the whole board, with an optional static, flash, or pulse
  effect.
- [Color pattern](blueprints/script/launchpad/display_pattern.yaml) accepts a
  JSON sequence of RGB colors. Spatial mode distributes colors across the
  chosen layout; timed mode cycles them for the configured duration.
- [Notification blink](blueprints/script/launchpad/notification_blink.yaml)
  flashes or pulses the chosen layout for a duration, then turns those LEDs
  off.
- [Set all LEDs](blueprints/script/launchpad/set_all_leds.yaml) fills or clears
  the board.
- [Scroll text](blueprints/script/launchpad/scroll_text.yaml) displays or
  scrolls text in either direction.

For each script blueprint, choose **Create script**, set its MQTT command topic
if needed, and save. These scripts can be run directly or called from
automations. Optional `ha_templates` examples wrap the blueprints for use in
YAML configuration.

### Lock and availability

The MQTT device creates a **Button Lock** entity, a **Lock Button** selector,
and an **Auto Lock Timer** number entity. The controller starts locked. Hold
the selected lock button to unlock and single-press it to lock again; while
locked, button events are suppressed. Select any button or **Disabled** in
Home Assistant. Do not assign the active lock button to an automation unless
you change or disable the lock button. The auto-lock timer is in seconds; set
it to `0` to disable automatic locking. The Matrix Display light entity's
brightness sets the Launchpad's master light level, which is applied to display
actions and the connection indicator. This value and other settings changed in
Home Assistant are saved in `device_settings.json` beside `main.py` and restored
after a device restart; initial lock values can be set in `.env` using
`LOCK_BUTTON` and `AUTO_LOCK_SECONDS`.

If the MQTT broker disconnects, all Launchpad LEDs blink red until it reconnects.
Lock handling and persisted settings are implemented in
[`lock_manager.py`](lock_manager.py), and press classification is implemented
in [`button_events.py`](button_events.py).
