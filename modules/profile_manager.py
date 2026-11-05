import json
from pathlib import Path

from .file_writer import SETTINGS_FILE, load_settings, update_settings


class ProfileManager:
    def __init__(
        self,
        client,
        device_id: str,
        device_info: dict,
        availability_topic: str,
        special_buttons: dict[tuple[int, int], str],
        settings_path: Path = SETTINGS_FILE,
    ):
        self.client = client
        self.device_info = device_info
        self.availability_topic = availability_topic
        self.settings_path = settings_path
        self.config_topic = f"homeassistant/select/{device_id}/active_profile/config"
        self.state_topic = f"device/{device_id}/profile/state"
        self.command_topic = f"device/{device_id}/profile/set"
        self.add_topic = f"device/{device_id}/profile/add"

        self.valid_buttons = set(special_buttons.values())
        self.valid_buttons.update(
            f"grid_{x}_{y}"
            for x in range(9)
            for y in range(9)
            if (x, y) not in special_buttons
        )
        self.profiles = self._load_profiles()
        settings = load_settings(self.settings_path) or {}
        self.active_profile = settings.get("active_profile", "")
        if self.active_profile not in self.profile_names:
            self.active_profile = self.profile_names[0] if self.profile_names else ""

    @property
    def profile_names(self) -> list[str]:
        return [profile["name"] for profile in self.profiles]

    def _load_profiles(self) -> list[dict[str, str]]:
        settings = load_settings(self.settings_path)
        if settings is None:
            return []

        profiles = settings.get("profiles", [])
        if not isinstance(profiles, list):
            raise ValueError(f"Profiles in {self.settings_path} must be a list.")

        result = []
        names = set()
        buttons = set()
        for profile in profiles:
            if not isinstance(profile, dict):
                raise ValueError(f"Invalid profile in {self.settings_path}: {profile!r}")
            name = profile.get("name")
            button = profile.get("button")
            if (not isinstance(name, str) or not name.strip()
                    or not isinstance(button, str) or button not in self.valid_buttons):
                raise ValueError(f"Invalid profile in {self.settings_path}: {profile!r}")
            name = name.strip()
            if name in names or button in buttons:
                raise ValueError(f"Duplicate profile name or button in {self.settings_path}.")
            names.add(name)
            buttons.add(button)
            result.append({"name": name, "button": button})
        return result

    def publish_discovery(self):
        if not self.profiles:
            return

        config = {
            "name": "Active Profile",
            "unique_id": f"{self.device_info['identifiers'][0]}_active_profile",
            "state_topic": self.state_topic,
            "command_topic": self.command_topic,
            "options": self.profile_names,
            "availability_topic": self.availability_topic,
            "payload_available": "online",
            "payload_not_available": "offline",
            "device": self.device_info
        }
        self.client.publish(self.config_topic, json.dumps(config), retain=True)

    def publish_state(self):
        if self.active_profile:
            self.client.publish(self.state_topic, self.active_profile, retain=True)

    def on_message(self, message) -> bool:
        value = message.payload.decode().strip()
        if message.topic == self.add_topic:
            payload = json.loads(value)
            if not isinstance(payload, dict):
                raise ValueError("Profile creation payload must be a JSON object.")
            self.add_profile(payload.get("name"), payload.get("button"))
            return True

        if message.topic == self.command_topic:
            if value not in self.profile_names:
                raise ValueError(f"Unsupported profile: {value}")
            self._set_active_profile(value)
            return True

        return False

    def add_profile(self, name: object, button: object):
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Profile name must be a non-empty string.")
        if not isinstance(button, str) or button not in self.valid_buttons:
            raise ValueError(f"Unsupported profile button: {button}")

        name = name.strip()
        if name in self.profile_names:
            raise ValueError(f"A profile named {name!r} already exists.")
        if any(profile["button"] == button for profile in self.profiles):
            raise ValueError(f"Button {button!r} is already assigned to a profile.")

        previous_profiles = self.profiles
        previous_active_profile = self.active_profile
        self.profiles = [*self.profiles, {"name": name, "button": button}]
        if not self.active_profile:
            self.active_profile = name
        try:
            self._save_settings()
        except OSError:
            self.profiles = previous_profiles
            self.active_profile = previous_active_profile
            raise
        self.publish_discovery()
        self.publish_state()

    def activate_for_button(self, button: str, event_type: str) -> bool:
        if event_type != "single_click":
            return False

        profile = next(
            (profile for profile in self.profiles if profile["button"] == button),
            None
        )
        if profile is None:
            return False

        self._set_active_profile(profile["name"])
        return True

    def _set_active_profile(self, name: str):
        previous_active_profile = self.active_profile
        self.active_profile = name
        try:
            self._save_settings()
        except OSError:
            self.active_profile = previous_active_profile
            raise
        self.publish_state()

    def _save_settings(self):
        update_settings({
            "profiles": self.profiles,
            "active_profile": self.active_profile
        }, self.settings_path)
