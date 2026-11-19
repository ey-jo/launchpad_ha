import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


def _provide_missing_runtime_modules():
    try:
        import paho.mqtt.client
    except ModuleNotFoundError:
        paho = types.ModuleType("paho")
        mqtt_package = types.ModuleType("paho.mqtt")
        mqtt_client = types.ModuleType("paho.mqtt.client")
        mqtt_client.Client = lambda **_kwargs: None
        mqtt_client.CallbackAPIVersion = types.SimpleNamespace(VERSION2=2)
        mqtt_package.client = mqtt_client
        paho.mqtt = mqtt_package
        sys.modules.update({
            "paho": paho,
            "paho.mqtt": mqtt_package,
            "paho.mqtt.client": mqtt_client
        })

    try:
        import launchpad_py
    except ModuleNotFoundError:
        launchpad_py = types.ModuleType("launchpad_py")
        launchpad_py.LaunchpadMk2 = object
        sys.modules["launchpad_py"] = launchpad_py


_provide_missing_runtime_modules()

from modules.lock_manager import LockManager
from modules.mqtt_handler import MQTTHandler


SPECIAL_BUTTONS = {(0, 0): "up"}


class FakeMQTTClient:
    def __init__(self):
        self.published = []

    def username_pw_set(self, *_args):
        pass

    def will_set(self, *_args, **_kwargs):
        pass

    def publish(self, *args, **kwargs):
        self.published.append((args, kwargs))


class FakeController:
    def __init__(self):
        self.calls = []

    def clear(self):
        self.calls.append(("clear",))

    def set_all_leds(self, *args):
        self.calls.append(("all", args))

    def set_led_xy(self, *args):
        self.calls.append(("xy", args))

    def set_led_xy_by_code(self, *args):
        self.calls.append(("code", args))

    def display_text(self, *args):
        self.calls.append(("text", args))


class MQTTMessage:
    topic = "device/launchpad/light/set"

    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()


def make_handler():
    controller = FakeController()
    client = FakeMQTTClient()
    with (
        patch("modules.mqtt_handler.mqtt.Client", return_value=client),
        patch("modules.lock_manager.load_settings", return_value=None),
        patch("modules.profile_manager.load_settings", return_value=None)
    ):
        handler = MQTTHandler(
            controller,
            "broker",
            "1883",
            None,
            None,
            "launchpad",
            "Launchpad",
            SPECIAL_BUTTONS
        )
    handler.lock_manager.set_light_brightness = lambda value: int(value)
    return handler, controller, client


class BrightnessRefreshTests(unittest.TestCase):
    def test_brightness_only_command_refreshes_without_filling_board(self):
        handler, controller, client = make_handler()

        handler.on_message(
            None, None, MQTTMessage({"state": "ON", "brightness": 100})
        )

        self.assertEqual(controller.calls, [])
        self.assertIn(
            ((handler.light_refresh_topic, "brightness_changed"), {}),
            client.published
        )

    def test_brightness_change_with_unchanged_color_does_not_fill_board(self):
        handler, controller, client = make_handler()

        handler.on_message(
            None,
            None,
            MQTTMessage({
                "state": "ON",
                "brightness": 100,
                "color": {"r": 255, "g": 255, "b": 255}
            })
        )

        self.assertEqual(controller.calls, [])
        self.assertIn(
            ((handler.light_refresh_topic, "brightness_changed"), {}),
            client.published
        )

    def test_color_change_still_fills_board_and_refreshes_brightness(self):
        handler, controller, client = make_handler()

        handler.on_message(
            None,
            None,
            MQTTMessage({
                "state": "ON",
                "brightness": 100,
                "color": {"r": 0, "g": 0, "b": 255}
            })
        )

        self.assertEqual(controller.calls[0][0], "all")
        self.assertIn(
            ((handler.light_refresh_topic, "brightness_changed"), {}),
            client.published
        )

    def test_lock_indicator_uses_full_red_palette_code(self):
        handler, controller, _client = make_handler()
        indicator_message = MQTTMessage({
            "lock_indicator": True,
            "x": 0,
            "y": 0,
            "color": {"r": 255, "g": 0, "b": 0}
        })

        handler.on_message(None, None, indicator_message)

        self.assertEqual(controller.calls, [("code", (0, 0, 5))])

    def test_board_clear_while_locked_republishes_lock_indicator(self):
        handler, controller, client = make_handler()

        handler.on_message(None, None, MQTTMessage({"state": "OFF"}))

        self.assertEqual(controller.calls, [("clear",)])
        indicator_payloads = [
            json.loads(args[1])
            for args, _kwargs in client.published
            if args[0] == handler.light_command_topic
        ]
        self.assertEqual(indicator_payloads[0]["color"], {"r": 255, "g": 0, "b": 0})


class LockIndicatorTests(unittest.TestCase):
    def test_lock_clears_board_and_red_indicator_expires_after_three_seconds(self):
        client = FakeMQTTClient()
        with patch("modules.lock_manager.load_settings", return_value=None):
            lock = LockManager(
                client,
                "launchpad",
                {"identifiers": ["launchpad"]},
                "device/launchpad/availability",
                SPECIAL_BUTTONS,
                "up",
                0
            )

        with patch("modules.lock_manager.time.monotonic", return_value=10):
            lock.set_locked(True)

        matrix_commands = [
            json.loads(args[1])
            for args, _kwargs in client.published
            if args[0] == lock.matrix_command_topic
        ]
        self.assertEqual(matrix_commands[0], {"state": "OFF"})
        self.assertEqual(
            matrix_commands[1]["color"],
            {"r": 255, "g": 0, "b": 0}
        )

        with patch("modules.lock_manager.time.monotonic", return_value=13):
            lock.check_auto_lock()

        matrix_commands = [
            json.loads(args[1])
            for args, _kwargs in client.published
            if args[0] == lock.matrix_command_topic
        ]
        self.assertEqual(
            matrix_commands[-1]["color"],
            {"r": 0, "g": 0, "b": 0}
        )

    def test_unlock_indicator_is_green_and_expires_after_three_seconds(self):
        client = FakeMQTTClient()
        with patch("modules.lock_manager.load_settings", return_value=None):
            lock = LockManager(
                client,
                "launchpad",
                {"identifiers": ["launchpad"]},
                "device/launchpad/availability",
                SPECIAL_BUTTONS,
                "up",
                0
            )

        with patch("modules.lock_manager.time.monotonic", return_value=20):
            lock.set_locked(False)

        matrix_commands = [
            json.loads(args[1])
            for args, _kwargs in client.published
            if args[0] == lock.matrix_command_topic
        ]
        self.assertEqual(
            matrix_commands[-1]["color"],
            {"r": 0, "g": 255, "b": 0}
        )

        with patch("modules.lock_manager.time.monotonic", return_value=23):
            lock.check_auto_lock()

        matrix_commands = [
            json.loads(args[1])
            for args, _kwargs in client.published
            if args[0] == lock.matrix_command_topic
        ]
        self.assertEqual(
            matrix_commands[-1]["color"],
            {"r": 0, "g": 0, "b": 0}
        )


class BlueprintRefreshTests(unittest.TestCase):
    def test_lock_entity_is_available_to_template_triggers(self):
        blueprint_dir = (
            Path(__file__).resolve().parents[1]
            / "blueprints/automation"
        )
        for blueprint_path in blueprint_dir.glob("entity_control_*.yaml"):
            with self.subTest(blueprint=blueprint_path.name):
                blueprint = blueprint_path.read_text(encoding="utf-8")
                self.assertIn(
                    "trigger_variables:\n  selected_lock_entity: !input lock_entity",
                    blueprint
                )
                self.assertIn("id: lock_unlocked", blueprint)

    def test_switch_blueprint_toggles_on_single_click_by_default(self):
        blueprint_path = (
            Path(__file__).resolve().parents[1]
            / "blueprints/automation/entity_control_switch.yaml"
        )
        blueprint = blueprint_path.read_text(encoding="utf-8")

        self.assertIn(
            'default: "grid_0_0,single_click,toggle"',
            blueprint
        )
        self.assertIn("- action: switch.toggle", blueprint)


if __name__ == "__main__":
    unittest.main()
