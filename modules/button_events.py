import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class ActivePress:
    started_at: float
    triggered: bool = False


class ButtonEventProcessor:
    def __init__(self, special_buttons: dict[tuple[int, int], str],
                 send_event: Callable[[str, str], None],
                 long_press_threshold: float = 0.55,
                 double_click_gap: float = 0.35):
        self.special_buttons = special_buttons
        self.send_event = send_event
        self.long_press_threshold = long_press_threshold
        self.double_click_gap = double_click_gap
        self.active_presses: dict[str, ActivePress] = {}
        self.pending_click: tuple[str, float] | None = None

    def handle_input(self, button_data: tuple[int, int, int] | None, lock_button: str):
        if button_data is None:
            return

        x, y, pressed = button_data
        button_label = self.special_buttons.get((x, y), f"grid_{x}_{y}")
        if pressed > 0:
            if button_label not in self.active_presses:
                self.active_presses[button_label] = ActivePress(time.monotonic())
                print(f"Debug: {button_label} pressed down.")
            return

        if pressed != 0 or button_label not in self.active_presses:
            return

        press_info = self.active_presses.pop(button_label)
        if press_info.triggered:
            print(f"Debug: {button_label} released after long_press cleanup.")
            return

        current_time = time.monotonic()
        if (self.pending_click is not None
                and button_label == self.pending_click[0]
                and current_time - self.pending_click[1] <= self.double_click_gap):
            print(f"Fired Event: {button_label} -> double_click")
            self.send_event(button_label, "double_click")
            self.pending_click = None
            return

        if self.pending_click is not None:
            pending_button = self.pending_click[0]
            self._send_single_click(pending_button)
            self.pending_click = None

        if button_label == lock_button:
            self._send_single_click(button_label)
        else:
            self.pending_click = (button_label, current_time)

    def check_timers(self):
        current_time = time.monotonic()
        for button_label, press_info in list(self.active_presses.items()):
            if (not press_info.triggered
                    and current_time - press_info.started_at >= self.long_press_threshold):
                print(f"Fired Event (Instant Threshold): {button_label} -> long_press")
                self.send_event(button_label, "long_press")
                press_info.triggered = True

        if (self.pending_click is not None
                and current_time - self.pending_click[1] > self.double_click_gap):
            pending_button = self.pending_click[0]
            self._send_single_click(pending_button)
            self.pending_click = None

    def _send_single_click(self, button_label: str):
        print(f"Fired Event: {button_label} -> single_click")
        self.send_event(button_label, "single_click")
