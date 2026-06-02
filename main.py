from paho.mqtt.client import Client, CallbackAPIVersion as API	# mqtt
from launchpad_py import LaunchpadMk2	# launchpad
from time import sleep
import json
import os	# environment
from dotenv import load_dotenv

from color import get_closest_color		# custom color calculation


# load environment variables
load_dotenv()
BROKER = os.environ.get("BROKER")
PORT = int(os.environ.get("PORT", 1883))

USERNAME = os.environ.get("USERNAME")
PASSWORD = os.environ.get("PASSWORD")

TOPIC = os.environ.get("TOPIC")
DEVICE_ID = os.environ.get("DEVICE_ID")
DEVICE_NAME = os.environ.get("DEVICE_NAME")


# MQTT Discovery Topics
LIGHT_CONFIG_TOPIC = f"homeassistant/light/{DEVICE_ID}/rgb_light/config"
BUTTON_CONFIG_TOPIC = f"homeassistant/binary_sensor/{DEVICE_ID}/button_state/config"

# State and Command Topics
LIGHT_STATE_TOPIC = f"device/{DEVICE_ID}/light/state"
LIGHT_COMMAND_TOPIC = f"device/{DEVICE_ID}/light/set"
BUTTON_STATE_TOPIC = f"device/{DEVICE_ID}/button/state"

# Shared Device Definition (links entities together in HA UI)
DEVICE_INFO = {
    "identifiers": [DEVICE_ID],
    "name": DEVICE_NAME,
    "model": "Launchpad Mk2",
    "manufacturer": "Novation"
}



# main loop async waiting for button pres then publishing
# on_message to control led

# led messages with qos 2, to shutdown the connection and read them when button is pressed and color correctly

# also the inputs are switches, because they can have both states


class controller:
	def __init__(self):
		self.lp = LaunchpadMk2()
		self.lp.Open()
		self.lp.ButtonFlush()


	def setLED(self, mode: str, red: int , green: int, blue: int, cords: list[int, int] = []):
		colorcode = get_closest_color(red, green, blue)

		match mode:
			case "all":
				self.lp.LedAllOn(colorcode)
			case "single":
				self.lp.LedCtrlXYByCode()
			case "pulse":
				self.lp.LedCtrlPulseXYByCode()
			case "flash":
				self.lp.LedCtrlFlashXYByCode()
			case "char":
				self.lp.LedCtrlChar()
			case "str":
				self.lp.LedCtrlString()
			case "clear":
				self.lp.Reset()
			case _:
				pass
	
	def getInput(self) -> tuple[int, int, int]:
		"""hold the main thread until an input is triggered, then return the input (x, y, pressed)
		Grid:	0|0				7|0
				0|8					8|8
		"""

		DELAY = 0.1
		state = self.lp.ButtonStateXY()
		while not state:
			sleep(DELAY)
			state = self.lp.ButtonStateXY()
		
		x, y, pressure = state
		return x, y, min(pressure, 1)


	def matrixify():
		pass



class mqtt:
	def _setup():
		client = Client(API.VERSION2)

		client.on_connect = mqtt.on_connect
		client.on_message = mqtt.on_message

		client.username_pw_set(USERNAME, PASSWORD)
		client.connect(BROKER, PORT, 60)


	def on_connect(client, userdata, flags, reason_code, properties):
		print(f"Connected with {reason_code}")
		client.subscribe(TOPIC)

	def on_message(client, userdata, msg):
		print(f"{msg.topic}\t{msg.payload}")


if __name__ == "__main__":
	try:
		#client.loop_start()
		c = controller()
		while True:
			#wait for button press
			print(c.getInput())
		#client.loop_stop()
		
	except BaseException as e:
		print(e)
		# send error message mqtt for everything
	