import json
import os
from threading import Event

import paho.mqtt.client as mqtt

from .launchpad import LaunchpadController
from .lock_manager import LockManager, parse_auto_lock_seconds


def validate_mqtt_settings(broker: str | None, port: str) -> tuple[str, int]:
    broker = (broker or "").strip()
    if not broker or any(character.isspace() for character in broker):
        raise ValueError("BROKER must be set to a valid MQTT broker hostname or IP address.")

    try:
        parsed_port = int(port)
    except ValueError as exc:
        raise ValueError("PORT must be an integer between 1 and 65535.") from exc

    if not 1 <= parsed_port <= 65535:
        raise ValueError("PORT must be an integer between 1 and 65535.")

    return broker, parsed_port


class MQTTHandler:
    def __init__(
        self,
        controller_instance: LaunchpadController,
        broker: str | None,
        port: str,
        username: str | None,
        password: str | None,
        device_id: str,
        device_name: str,
        special_buttons: dict[tuple[int, int], str],
    ):
        self.lp_ctrl = controller_instance
        self.broker = broker
        self.port = port
        self.client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self.client.username_pw_set(username, password)

        self.light_config_topic = f"homeassistant/light/{device_id}/matrix_light/config"
        self.event_config_topic = f"homeassistant/event/{device_id}/matrix_click/config"
        self.light_state_topic = f"device/{device_id}/light/state"
        self.light_command_topic = f"device/{device_id}/light/set"
        self.event_state_topic = f"device/{device_id}/event/state"
        self.availability_topic = f"device/{device_id}/availability"
        self.device_info = {
            "identifiers": [device_id],
            "name": device_name,
            "model": "Launchpad Mk2",
            "manufacturer": "Novation"
        }

        self.client.will_set(self.availability_topic, "offline", qos=1, retain=True)
        self.connected = Event()
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message
        self.lock_manager = LockManager(
            self.client,
            device_id,
            self.device_info,
            self.availability_topic,
            special_buttons,
            os.environ.get("LOCK_BUTTON", "up"),
            parse_auto_lock_seconds(os.environ.get("AUTO_LOCK_SECONDS", "0"))
        )

        self.current_brightness = self.lock_manager.light_brightness
        self.current_r = 255
        self.current_g = 255
        self.current_b = 255

    def start(self):
        broker, port = validate_mqtt_settings(self.broker, self.port)
        self.client.connect(broker, port, 60)
        self.client.loop_start()

    def stop(self):
        self.publish_availability("offline")
        self.client.loop_stop()
        self.client.disconnect()

    def on_connect(self, _client, _userdata, _flags, reason_code, _properties):
        if reason_code != 0:
            print(f"Failed to connect to MQTT Broker: {reason_code}")
            return

        self.connected.set()
        print(f"Connected to MQTT Broker: {reason_code}")
        self.client.subscribe(self.light_command_topic)
        self.client.subscribe(self.lock_manager.command_topic)
        self.client.subscribe(self.lock_manager.button_command_topic)
        self.client.subscribe(self.lock_manager.timer_command_topic)
        self.publish_discovery()
        self.publish_availability("online")
        self.client.publish(
            self.light_state_topic,
            json.dumps({"state": "OFF", "brightness": self.current_brightness}),
            retain=True
        )
        self.lock_manager.publish_state()

    def publish_availability(self, availability: str):
        self.client.publish(self.availability_topic, availability, retain=True)

    def on_disconnect(self, _client, _userdata, rc, _properties, _):
        self.connected.clear()
        if rc != 0:
            print(f"Unexpected MQTT disconnect (rc={rc}); broker last will will publish offline.")
        else:
            print("MQTT disconnected cleanly.")

    def publish_discovery(self):
        light_config = {
            "name": "Matrix Display",
            "unique_id": f"{self.device_info['identifiers'][0]}_matrix_light",
            "state_topic": self.light_state_topic,
            "command_topic": self.light_command_topic,
            "availability_topic": self.availability_topic,
            "payload_available": "online",
            "payload_not_available": "offline",
            "schema": "json",
            "color_mode": True,
            "supported_color_modes": ["rgb"],
            "brightness": True,
            "effect": True,
            "effect_list": ["static", "flash", "pulse", "clear"],
            "device": self.device_info
        }
        self.client.publish(self.light_config_topic, json.dumps(light_config), retain=True)

        event_config = {
            "name": "Matrix Button Press",
            "unique_id": f"{self.device_info['identifiers'][0]}_matrix_event",
            "state_topic": self.event_state_topic,
            "event_types": ["single_click", "double_click", "long_press"],
            "device": self.device_info
        }
        self.client.publish(self.event_config_topic, json.dumps(event_config), retain=True)
        self.lock_manager.publish_discovery()
        print("Home Assistant Discovery Configurations Sent.")

    def on_message(self, _client, _userdata, msg):
        try:
            if self.lock_manager.on_message(msg):
                return

            payload = json.loads(msg.payload.decode())
            print(f"Received Command: {payload}")

            if "brightness" in payload:
                self.current_brightness = self.lock_manager.set_light_brightness(
                    payload["brightness"]
                )

            if "color" in payload:
                self.current_r = payload["color"].get("r", 255)
                self.current_g = payload["color"].get("g", 255)
                self.current_b = payload["color"].get("b", 255)

            mode = payload.get("effect", "static")
            state = payload.get("state", "ON")

            if state == "OFF" or mode == "clear":
                self.lp_ctrl.clear()
                self.client.publish(
                    self.light_state_topic,
                    json.dumps({"state": "OFF", "brightness": self.current_brightness}),
                    retain=True
                )
                return

            if "text" in payload:
                text_val = str(payload["text"])
                direction_val = payload.get("direction", "left")
                self.lp_ctrl.display_text(
                    text_val, self.current_r, self.current_g, self.current_b,
                    self.current_brightness, direction_val
                )
            elif "x" in payload and "y" in payload:
                self.lp_ctrl.set_led_xy(
                    int(payload["x"]), int(payload["y"]), self.current_r,
                    self.current_g, self.current_b, self.current_brightness, mode
                )
            else:
                self.lp_ctrl.set_all_leds(
                    self.current_r, self.current_g, self.current_b, self.current_brightness
                )

            state_payload = payload.copy()
            state_payload["brightness"] = self.current_brightness
            self.client.publish(self.light_state_topic, json.dumps(state_payload), retain=True)

        except Exception as e:
            print(f"Error handling MQTT message on {msg.topic}: {e}")

    def send_button_event(self, button_label: str, event_type: str):
        self.lock_manager.send_button_event(button_label, event_type)

    def update_connection_indicator(self):
        self.lp_ctrl.blink_all_leds_red(
            not self.connected.is_set(), self.current_brightness
        )
