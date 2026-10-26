import os
import json
import time
from threading import Event
from time import sleep
import paho.mqtt.client as mqtt
from dotenv import load_dotenv
from launchpad_py import LaunchpadMk2
from color import get_closest_color
from button_events import ButtonEventProcessor
from lock_manager import LockManager

# Load environment variables
load_dotenv()
BROKER = os.environ.get("BROKER")
PORT = int(os.environ.get("PORT", 1883))
USERNAME = os.environ.get("USERNAME")
PASSWORD = os.environ.get("PASSWORD")
DEVICE_ID = os.environ.get("DEVICE_ID", "launchpad_mk2")
DEVICE_NAME = os.environ.get("DEVICE_NAME", "Launchpad Matrix Controller")

# MQTT Discovery Topics
LIGHT_CONFIG_TOPIC = f"homeassistant/light/{DEVICE_ID}/matrix_light/config"
EVENT_CONFIG_TOPIC = f"homeassistant/event/{DEVICE_ID}/matrix_click/config"

# State and Command Topics
LIGHT_STATE_TOPIC = f"device/{DEVICE_ID}/light/state"
LIGHT_COMMAND_TOPIC = f"device/{DEVICE_ID}/light/set"
EVENT_STATE_TOPIC = f"device/{DEVICE_ID}/event/state"
AVAILABILITY_TOPIC = f"device/{DEVICE_ID}/availability"

DEVICE_INFO = {
    "identifiers": [DEVICE_ID],
    "name": DEVICE_NAME,
    "model": "Launchpad Mk2",
    "manufacturer": "Novation"
}

SPECIAL_BUTTONS = {
    (0, 0): "up", (1, 0): "down", (2, 0): "left", (3, 0): "right",
    (4, 0): "session", (5, 0): "user_1", (6, 0): "user_2", (7, 0): "mixer",
    (8, 1): "volume", (8, 2): "pan", (8, 3): "send_a", (8, 4): "send_b",
    (8, 5): "stop", (8, 6): "mute", (8, 7): "solo", (8, 8): "record_arm"
}


class LaunchpadController:
    def __init__(self):
        self.lp = LaunchpadMk2()
        if not self.lp.Open():
            raise RuntimeError("Could not open Launchpad Mk2 connection.")
        self.lp.ButtonFlush()
        self.lp.Reset()
        self._red_blink_on = False
        self._last_red_blink = 0.0

    def scale_color(self, r: int, g: int, b: int, brightness: int) -> tuple[int, int, int]:
        """Scales raw RGB values down based on Home Assistant's brightness scale (0-255)."""
        # Brightness factor scale: 0.0 to 1.0
        factor = brightness / 255.0
        return int(r * factor), int(g * factor), int(b * factor)

    def set_led_xy(self, x: int, y: int, r: int, g: int, b: int, brightness: int, mode: str = "single"):
        # Apply mathematical brightness scaling before calculating the target MIDI code
        r, g, b = self.scale_color(r, g, b, brightness)
        colorcode = get_closest_color(r, g, b)
        
        if mode == "flash":
            self.lp.LedCtrlFlashXYByCode(x, y, colorcode)
        elif mode == "pulse":
            self.lp.LedCtrlPulseXYByCode(x, y, colorcode)
        else:
            self.lp.LedCtrlXYByCode(x, y, colorcode)

    def display_text(self, text: str, r: int, g: int, b: int, brightness: int, direction_str: str):
        r, g, b = self.scale_color(r, g, b, brightness)
        colorcode = get_closest_color(r, g, b)
        direction = -1 if direction_str.lower() == "right" else 1

        if len(text) == 1:
            print(f"Displaying character: '{text}' (Code: {colorcode}, Dir: {direction})")
            self.lp.LedCtrlChar(text, colorcode, direction)
        else:
            print(f"Scrolling string: '{text}' (Code: {colorcode}, Dir: {direction})")
            self.lp.LedCtrlString(text, colorcode, direction, 1)

    def set_all_leds(self, r: int, g: int, b: int, brightness: int):
        r, g, b = self.scale_color(r, g, b, brightness)
        colorcode = get_closest_color(r, g, b)
        self.lp.LedAllOn(colorcode)

    def clear(self):
        self.lp.Reset()

    def blink_all_leds_red(self, enabled: bool):
        if not enabled:
            if self._red_blink_on:
                self.clear()
                self._red_blink_on = False
            return

        current_time = time.monotonic()
        if current_time - self._last_red_blink < 0.5:
            return

        self._last_red_blink = current_time
        self._red_blink_on = not self._red_blink_on
        if self._red_blink_on:
            self.set_all_leds(255, 0, 0, 255)
        else:
            self.clear()

    def get_input(self) -> tuple[int, int, int] | None:
        state = self.lp.ButtonStateXY()
        if state and len(state) >= 3:
            x, y, pressure = state
            return x, y, min(pressure, 1)
        return None


class MQTTHandler:
    def __init__(self, controller_instance: LaunchpadController):
        self.lp_ctrl = controller_instance
        self.client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self.client.username_pw_set(USERNAME, PASSWORD)
        self.client.will_set(AVAILABILITY_TOPIC, "offline", qos=1, retain=True)
        self.connected = Event()

        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message
        self.lock_manager = LockManager(
            self.client,
            DEVICE_ID,
            DEVICE_INFO,
            AVAILABILITY_TOPIC,
            SPECIAL_BUTTONS,
            os.environ.get("LOCK_BUTTON", "up"),
            int(os.environ.get("AUTO_LOCK_SECONDS", "0"))
        )
        
        # Track state attributes internally to acknowledge states accurately back to HA
        self.current_brightness = 255 
        self.current_r = 255
        self.current_g = 255
        self.current_b = 255

    def start(self):
        self.client.connect(BROKER, PORT, 60)
        self.client.loop_start()

    def stop(self):
        self.publish_availability("offline")
        self.client.loop_stop()
        self.client.disconnect()

    def on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code != 0:
            print(f"Failed to connect to MQTT Broker: {reason_code}")
            return

        self.connected.set()
        print(f"Connected to MQTT Broker: {reason_code}")
        self.client.subscribe(LIGHT_COMMAND_TOPIC)
        self.client.subscribe(self.lock_manager.command_topic)
        self.client.subscribe(self.lock_manager.button_command_topic)
        self.client.subscribe(self.lock_manager.timer_command_topic)
        self.publish_discovery()
        self.publish_availability("online")
        self.client.publish(LIGHT_STATE_TOPIC, json.dumps({"state": "OFF"}), retain=True)
        self.lock_manager.publish_state()

    def publish_availability(self, availability: str):
        self.client.publish(AVAILABILITY_TOPIC, availability, retain=True)

    def on_disconnect(self, client, userdata, rc, properties, _):
        self.connected.clear()
        if rc != 0:
            print(f"Unexpected MQTT disconnect (rc={rc}); broker last will will publish offline.")
        else:
            print("MQTT disconnected cleanly.")

    def publish_discovery(self):
        # Added "brightness": True to tell Home Assistant to unlock the dimmer UI slider
        light_config = {
            "name": "Matrix Display",
            "unique_id": f"{DEVICE_ID}_matrix_light",
            "state_topic": LIGHT_STATE_TOPIC,
            "command_topic": LIGHT_COMMAND_TOPIC,
            "availability_topic": AVAILABILITY_TOPIC,
            "payload_available": "online",
            "payload_not_available": "offline",
            "schema": "json",
            "color_mode": True,
            "supported_color_modes": ["rgb"],
            "brightness": True, 
            "effect": True,
            "effect_list": ["static", "flash", "pulse", "clear"],
            "device": DEVICE_INFO
        }
        self.client.publish(LIGHT_CONFIG_TOPIC, json.dumps(light_config), retain=True)

        event_config = {
            "name": "Matrix Button Press",
            "unique_id": f"{DEVICE_ID}_matrix_event",
            "state_topic": EVENT_STATE_TOPIC,
            "event_types": ["single_click", "double_click", "long_press"],
            "device": DEVICE_INFO
        }
        self.client.publish(EVENT_CONFIG_TOPIC, json.dumps(event_config), retain=True)
        self.lock_manager.publish_discovery()
        print("Home Assistant Discovery Configurations Sent.")

    def on_message(self, client, userdata, msg):
        try:
            if self.lock_manager.on_message(msg):
                return

            payload = json.loads(msg.payload.decode())
            print(f"Received Command: {payload}")

            # 1. Handle incoming brightness state payload (HA handles this in a 0-255 range)
            if "brightness" in payload:
                self.current_brightness = int(payload["brightness"])

            # 2. Extract or update tracking color properties
            if "color" in payload:
                self.current_r = payload["color"].get("r", 255)
                self.current_g = payload["color"].get("g", 255)
                self.current_b = payload["color"].get("b", 255)

            mode = payload.get("effect", "static")
            state = payload.get("state", "ON")

            if state == "OFF" or mode == "clear":
                self.lp_ctrl.clear()
                self.client.publish(LIGHT_STATE_TOPIC, json.dumps({"state": "OFF"}), retain=True)
                return

            # 3. Route actions using the updated brightness scaling values
            if "text" in payload:
                text_val = str(payload["text"])
                direction_val = payload.get("direction", "left")
                self.lp_ctrl.display_text(text_val, self.current_r, self.current_g, self.current_b, self.current_brightness, direction_val)
            elif "x" in payload and "y" in payload:
                self.lp_ctrl.set_led_xy(int(payload["x"]), int(payload["y"]), self.current_r, self.current_g, self.current_b, self.current_brightness, mode)
            else:
                self.lp_ctrl.set_all_leds(self.current_r, self.current_g, self.current_b, self.current_brightness)

            # Mirror current known states to keep HA in sync
            self.client.publish(LIGHT_STATE_TOPIC, json.dumps(payload), retain=True)

        except Exception as e:
            print(f"Error handling MQTT message on {msg.topic}: {e}")

    def send_button_event(self, button_label: str, event_type: str):
        self.lock_manager.send_button_event(button_label, event_type)

    def update_connection_indicator(self):
        self.lp_ctrl.blink_all_leds_red(not self.connected.is_set())


if __name__ == "__main__":
    c = LaunchpadController()
    mqtt_handler = MQTTHandler(c)
    button_events = ButtonEventProcessor(SPECIAL_BUTTONS, mqtt_handler.send_button_event)

    try:
        mqtt_handler.start()
        print("Launchpad Matrix Engine Active (Real-Time Long-Press Trigger)...")
        
        while True:
            button_data = c.get_input()
            button_events.handle_input(button_data, mqtt_handler.lock_manager.lock_button)
            button_events.check_timers()
            mqtt_handler.lock_manager.check_auto_lock()
            mqtt_handler.update_connection_indicator()
            sleep(0.01)  # 10ms loop speed ensures tight timing accuracy
            
    except KeyboardInterrupt:
        print("\nHalting script safely...")
    except Exception as e:
        print(f"Runtime execution error: {e}")
    finally:
        mqtt_handler.stop()
        c.clear()