import os
from time import sleep

from dotenv import load_dotenv

from modules.button_events import ButtonEventProcessor
from modules.launchpad import LaunchpadController, SPECIAL_BUTTONS
from modules.mqtt_handler import MQTTHandler


def main():
    load_dotenv()
    controller = LaunchpadController()
    mqtt_handler = MQTTHandler(
        controller,
        os.environ.get("BROKER"),
        os.environ.get("PORT", "1883"),
        os.environ.get("USERNAME"),
        os.environ.get("PASSWORD"),
        os.environ.get("DEVICE_ID", "launchpad"),
        os.environ.get("DEVICE_NAME", "Launchpad Matrix Controller"),
        SPECIAL_BUTTONS
    )
    button_events = ButtonEventProcessor(
        SPECIAL_BUTTONS, mqtt_handler.send_button_event
    )

    try:
        mqtt_handler.start()
        print("Launchpad Matrix Engine Active (Real-Time Long-Press Trigger)...")

        while True:
            button_data = controller.get_input()
            button_events.handle_input(button_data, mqtt_handler.lock_manager.lock_button)
            button_events.check_timers()
            mqtt_handler.lock_manager.check_auto_lock()
            mqtt_handler.update_connection_indicator()
            sleep(0.01)

    except KeyboardInterrupt:
        print("\nHalting script safely...")
    except Exception as e:
        print(f"Runtime execution error: {e}")
        raise
    finally:
        mqtt_handler.stop()
        controller.clear()


if __name__ == "__main__":
    main()
