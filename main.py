import os
import json
import time
from time import sleep
import paho.mqtt.client as mqtt
from dotenv import load_dotenv
from launchpad_py import LaunchpadMk2
from color import get_closest_color

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
        
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        
        # Track state attributes internally to acknowledge states accurately back to HA
        self.current_brightness = 255 
        self.current_r = 255
        self.current_g = 255
        self.current_b = 255

    def start(self):
        self.client.connect(BROKER, PORT, 60)
        self.client.loop_start()

    def stop(self):
        self.client.loop_stop()
        self.client.disconnect()

    def on_connect(self, client, userdata, flags, reason_code, properties):
        print(f"Connected to MQTT Broker: {reason_code}")
        self.client.subscribe(LIGHT_COMMAND_TOPIC)
        self.publish_discovery()

    def publish_discovery(self):
        # Added "brightness": True to tell Home Assistant to unlock the dimmer UI slider
        light_config = {
            "name": "Matrix Display",
            "unique_id": f"{DEVICE_ID}_matrix_light",
            "state_topic": LIGHT_STATE_TOPIC,
            "command_topic": LIGHT_COMMAND_TOPIC,
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
        print("Home Assistant Discovery Configurations Sent.")

    def on_message(self, client, userdata, msg):
        try:
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
            print(f"Error parsing incoming JSON control schema: {e}")

    def send_button_event(self, button_label: str, event_type: str):
        payload = {
            "event_type": event_type,
            "button": button_label
        }
        self.client.publish(EVENT_STATE_TOPIC, json.dumps(payload))


if __name__ == "__main__":
    c = LaunchpadController()
    mqtt_handler = MQTTHandler(c)
    
    # Timing Threshold Constraints
    LONG_PRESS_THRESHOLD = 0.55  # 550ms
    DOUBLE_CLICK_GAP = 0.35      # 350ms

    # active_presses will now store: { button_label: {"start_time": float, "triggered": bool} }
    active_presses = {}          
    last_released_button = None
    last_release_time = 0

    try:
        mqtt_handler.start()
        print("Launchpad Matrix Engine Active (Real-Time Long-Press Trigger)...")
        
        while True:
            button_data = c.get_input()
            
            if button_data:
                x, y, pressed = button_data
                
                # Resolve the button label mapping
                if (x, y) in SPECIAL_BUTTONS:
                    button_label = SPECIAL_BUTTONS[(x, y)]
                else:
                    button_label = f"grid_{x}_{y}"

                # --- CASE 1: BUTTON PRESSED DOWN ---
                if pressed > 0:
                    if button_label not in active_presses:
                        active_presses[button_label] = {
                            "start_time": time.time(),
                            "triggered": False
                        }
                        print(f"Debug: {button_label} pressed down.")

                # --- CASE 2: BUTTON RELEASED ---
                elif pressed == 0:
                    if button_label in active_presses:
                        press_info = active_presses.pop(button_label)
                        
                        # If it already fired a long_press while being held, 
                        # we just clean it up silently on release.
                        if press_info["triggered"]:
                            print(f"Debug: {button_label} released after long_press cleanup.")
                            continue
                        
                        # Otherwise, it was a short press, calculate single vs double click
                        current_time = time.time()
                        
                        # Check for Double Click
                        if (button_label == last_released_button) and ((current_time - last_release_time) <= DOUBLE_CLICK_GAP):
                            print(f"Fired Event: {button_label} -> double_click")
                            mqtt_handler.send_button_event(button_label, "double_click")
                            last_released_button = None
                            last_release_time = 0
                        else:
                            # It's a Single Click
                            print(f"Fired Event: {button_label} -> single_click")
                            mqtt_handler.send_button_event(button_label, "single_click")
                            last_released_button = button_label
                            last_release_time = current_time

            # --- CASE 3: REAL-TIME LONG PRESS CHECK ---
            # Loop through all currently held buttons to see if any just crossed the threshold
            current_time = time.time()
            for b_label, press_info in list(active_presses.items()):
                if not press_info["triggered"]:
                    duration = current_time - press_info["start_time"]
                    if duration >= LONG_PRESS_THRESHOLD:
                        print(f"Fired Event (Instant Threshold): {b_label} -> long_press")
                        mqtt_handler.send_button_event(b_label, "long_press")
                        press_info["triggered"] = True  # Prevent it from firing repeatedly while held

            sleep(0.01)  # 10ms loop speed ensures tight timing accuracy
            
    except KeyboardInterrupt:
        print("\nHalting script safely...")
    except Exception as e:
        print(f"Runtime execution error: {e}")
    finally:
        mqtt_handler.stop()
        c.clear()