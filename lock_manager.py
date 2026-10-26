import json
import os
import time
from pathlib import Path


MAX_AUTO_LOCK_SECONDS = 86400
SETTINGS_FILE = Path(__file__).with_name("device_settings.json")


class LockManager:
    def __init__(self, client, device_id: str, device_info: dict, availability_topic: str,
                 special_buttons: dict, initial_button: str, initial_auto_lock_seconds: int):
        self.client = client
        self.device_info = device_info
        self.availability_topic = availability_topic

        self.config_topic = f"homeassistant/lock/{device_id}/button_lock/config"
        self.button_config_topic = f"homeassistant/select/{device_id}/lock_button/config"
        self.timer_config_topic = f"homeassistant/number/{device_id}/auto_lock_seconds/config"
        self.state_topic = f"device/{device_id}/lock/state"
        self.command_topic = f"device/{device_id}/lock/set"
        self.button_state_topic = f"device/{device_id}/lock/button/state"
        self.button_command_topic = f"device/{device_id}/lock/button/set"
        self.timer_state_topic = f"device/{device_id}/lock/auto_lock_seconds/state"
        self.timer_command_topic = f"device/{device_id}/lock/auto_lock_seconds/set"
        self.event_state_topic = f"device/{device_id}/event/state"

        self.button_options = ["Disabled", *special_buttons.values()]
        self.button_options.extend(
            f"grid_{x}_{y}"
            for x in range(9)
            for y in range(9)
            if (x, y) not in special_buttons
        )

        self.lock_button = initial_button
        self.auto_lock_seconds = initial_auto_lock_seconds
        self.locked = True
        self.auto_lock_deadline = None
        self.load_settings()

    def publish_discovery(self):
        entities = [
            (
                self.config_topic,
                {
                    "name": "Button Lock",
                    "unique_id": f"{self.device_info['identifiers'][0]}_button_lock",
                    "state_topic": self.state_topic,
                    "command_topic": self.command_topic,
                    "payload_lock": "LOCK",
                    "payload_unlock": "UNLOCK",
                    "state_locked": "LOCKED",
                    "state_unlocked": "UNLOCKED",
                    "device": self.device_info
                }
            ),
            (
                self.button_config_topic,
                {
                    "name": "Lock Button",
                    "unique_id": f"{self.device_info['identifiers'][0]}_lock_button",
                    "state_topic": self.button_state_topic,
                    "command_topic": self.button_command_topic,
                    "options": self.button_options,
                    "device": self.device_info
                }
            ),
            (
                self.timer_config_topic,
                {
                    "name": "Auto Lock Timer",
                    "unique_id": f"{self.device_info['identifiers'][0]}_auto_lock_seconds",
                    "state_topic": self.timer_state_topic,
                    "command_topic": self.timer_command_topic,
                    "min": 0,
                    "max": MAX_AUTO_LOCK_SECONDS,
                    "step": 1,
                    "mode": "box",
                    "unit_of_measurement": "s",
                    "device": self.device_info
                }
            )
        ]

        for topic, config in entities:
            config.update({
                "availability_topic": self.availability_topic,
                "payload_available": "online",
                "payload_not_available": "offline"
            })
            self.client.publish(topic, json.dumps(config), retain=True)

    def publish_state(self):
        self.client.publish(
            self.state_topic,
            "LOCKED" if self.locked else "UNLOCKED",
            retain=True
        )
        self.client.publish(self.button_state_topic, self.lock_button, retain=True)
        self.client.publish(
            self.timer_state_topic,
            str(self.auto_lock_seconds),
            retain=True
        )

    def on_message(self, message) -> bool:
        value = message.payload.decode().strip()
        if message.topic == self.command_topic:
            if value == "LOCK":
                self.set_locked(True)
            elif value == "UNLOCK":
                self.set_locked(False)
            else:
                raise ValueError(f"Unsupported lock command: {value}")
            return True

        if message.topic == self.button_command_topic:
            if value not in self.button_options:
                raise ValueError(f"Unsupported lock button: {value}")
            previous_button = self.lock_button
            self.lock_button = value
            try:
                self.save_settings()
            except OSError:
                self.lock_button = previous_button
                raise
            self.client.publish(self.button_state_topic, self.lock_button, retain=True)
            return True

        if message.topic == self.timer_command_topic:
            seconds = int(value)
            if not 0 <= seconds <= MAX_AUTO_LOCK_SECONDS:
                raise ValueError(
                    f"Auto-lock timer must be between 0 and {MAX_AUTO_LOCK_SECONDS} seconds."
                )
            previous_seconds = self.auto_lock_seconds
            self.auto_lock_seconds = seconds
            try:
                self.save_settings()
            except OSError:
                self.auto_lock_seconds = previous_seconds
                raise
            self.client.publish(self.timer_state_topic, str(seconds), retain=True)
            self.reset_auto_lock_deadline()
            return True

        return False

    def send_button_event(self, button_label: str, event_type: str):
        if self.lock_button != "Disabled" and button_label == self.lock_button:
            if self.locked and event_type == "long_press":
                print(f"Launchpad unlocked with long press of {button_label}.")
                self.set_locked(False)
                return
            if not self.locked and event_type == "single_click":
                print(f"Launchpad locked with single press of {button_label}.")
                self.set_locked(True)
                return

        if self.locked:
            return

        payload = {
            "event_type": event_type,
            "button": button_label
        }
        self.client.publish(self.event_state_topic, json.dumps(payload))

    def load_settings(self):
        if SETTINGS_FILE.exists():
            with SETTINGS_FILE.open(encoding="utf-8") as settings_file:
                settings = json.load(settings_file)
            if not isinstance(settings, dict):
                raise ValueError(f"{SETTINGS_FILE} must contain a JSON object.")
            self.lock_button = settings.get("lock_button", self.lock_button)
            self.auto_lock_seconds = int(
                settings.get("auto_lock_seconds", self.auto_lock_seconds)
            )

        if self.lock_button not in self.button_options:
            raise ValueError(f"LOCK_BUTTON must be one of {self.button_options}.")
        if not 0 <= self.auto_lock_seconds <= MAX_AUTO_LOCK_SECONDS:
            raise ValueError(
                f"AUTO_LOCK_SECONDS must be between 0 and {MAX_AUTO_LOCK_SECONDS}."
            )

    def save_settings(self):
        settings = {
            "lock_button": self.lock_button,
            "auto_lock_seconds": self.auto_lock_seconds
        }
        temporary_file = SETTINGS_FILE.with_name(f".{SETTINGS_FILE.name}.tmp")
        try:
            with temporary_file.open("w", encoding="utf-8") as settings_file:
                json.dump(settings, settings_file, indent=2)
                settings_file.write("\n")
                settings_file.flush()
                os.fsync(settings_file.fileno())
            os.replace(temporary_file, SETTINGS_FILE)
        finally:
            temporary_file.unlink(missing_ok=True)

    def set_locked(self, locked: bool):
        self.locked = locked
        self.reset_auto_lock_deadline()
        self.publish_state()

    def reset_auto_lock_deadline(self):
        if not self.locked and self.auto_lock_seconds > 0:
            self.auto_lock_deadline = time.monotonic() + self.auto_lock_seconds
        else:
            self.auto_lock_deadline = None

    def check_auto_lock(self):
        if self.auto_lock_deadline is not None and time.monotonic() >= self.auto_lock_deadline:
            print("Launchpad locked by auto-lock timer.")
            self.set_locked(True)
