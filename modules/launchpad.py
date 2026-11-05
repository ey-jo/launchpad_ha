import time

from launchpad_py import LaunchpadMk2

from .color import get_closest_color

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
        factor = brightness / 255.0
        return int(r * factor), int(g * factor), int(b * factor)

    def set_led_xy(
        self, x: int, y: int, r: int, g: int, b: int, brightness: int,
        mode: str = "single"
    ):
        r, g, b = self.scale_color(r, g, b, brightness)
        colorcode = get_closest_color(r, g, b)

        if mode == "flash":
            self.lp.LedCtrlFlashXYByCode(x, y, colorcode)
        elif mode == "pulse":
            self.lp.LedCtrlPulseXYByCode(x, y, colorcode)
        else:
            self.lp.LedCtrlXYByCode(x, y, colorcode)

    def display_text(
        self, text: str, r: int, g: int, b: int, brightness: int,
        direction_str: str
    ):
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

    def blink_all_leds_red(self, enabled: bool, brightness: int = 255):
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
            self.set_all_leds(255, 0, 0, brightness)
        else:
            self.clear()

    def get_input(self) -> tuple[int, int, int] | None:
        state = self.lp.ButtonStateXY()
        if state and len(state) >= 3:
            x, y, pressure = state
            return x, y, min(pressure, 1)
        return None
