"""Central module entry point.

Reads steering-wheel preset buttons, sends target modes to front/rear diff
modules, monitors module heartbeat, and tracks each diff's current mode.
"""

import time
from machine import Pin, UART

from central_module import config, pins
from common.constants import (
    CMD_HEARTBEAT,
    CMD_MODE_STATUS,
    HEARTBEAT_INTERVAL_MS,
    HEARTBEAT_TIMEOUT_MS,
    NODE_ID_DIFF_FRONT,
    NODE_ID_DIFF_REAR,
)
from common.modes import DifferentialMode
from common.protocol import SerialProtocol, byte_to_mode
from common.switch_input import SwitchCollection


class CentralModuleApp:
    """Runtime application for central (steering-wheel) controller."""

    def __init__(self) -> None:
        pull_mode = Pin.PULL_UP if pins.INPUT_PULL_UP else Pin.PULL_DOWN

        self._buttons = SwitchCollection()
        self._registered_button_ids = []
        self._register_buttons(pull_mode)

        self._uart = UART(
            pins.UART_ID,
            baudrate=pins.UART_BAUDRATE,
            tx=pins.UART_TX_PIN,
            rx=pins.UART_RX_PIN,
        )
        self._protocol = SerialProtocol(self._uart, node_id=pins.NODE_ID)

        self._diff_modes = {
            NODE_ID_DIFF_FRONT: DifferentialMode.UNKNOWN,
            NODE_ID_DIFF_REAR: DifferentialMode.UNKNOWN,
        }
        self._diff_last_seen_ms = {
            NODE_ID_DIFF_FRONT: 0,
            NODE_ID_DIFF_REAR: 0,
        }
        self._diff_online = {
            NODE_ID_DIFF_FRONT: False,
            NODE_ID_DIFF_REAR: False,
        }

        self._last_heartbeat_ms = 0

    def _register_buttons(self, pull_mode: int) -> None:
        """Register configured button pins (1..6)."""
        for button_id in range(1, 7):
            pin_attr = "BUTTON_{}_PIN".format(button_id)
            pin_value = getattr(pins, pin_attr, None)
            if pin_value is None:
                continue

            button_name = str(button_id)
            self._buttons.add_switch(
                name=button_name,
                pin=pin_value,
                pull=pull_mode,
                debounce_ms=pins.INPUT_DEBOUNCE_MS,
                active_low=pins.INPUT_ACTIVE_LOW,
            )
            self._registered_button_ids.append(button_id)

    def _apply_preset(self, button_id: int) -> None:
        """Send front/rear set-mode commands for one selected preset."""
        preset = config.BUTTON_PRESETS.get(button_id)
        if preset is None:
            return

        front_mode, rear_mode = preset
        if DifferentialMode.is_drive_mode(front_mode):
            self._protocol.send_set_mode(NODE_ID_DIFF_FRONT, front_mode)
        if DifferentialMode.is_drive_mode(rear_mode):
            self._protocol.send_set_mode(NODE_ID_DIFF_REAR, rear_mode)

    def _poll_buttons(self) -> None:
        """Detect newly pressed preset buttons."""
        self._buttons.update_all()

        for button_id in self._registered_button_ids:
            button_name = str(button_id)
            switch = self._buttons.get_switch(button_name)
            if switch is None:
                continue
            if switch.was_pressed():
                self._apply_preset(button_id)

    def _process_incoming(self) -> None:
        """Consume incoming UART messages and update diff state tracking."""
        now = time.ticks_ms()

        for message in self._protocol.poll():
            src = message["src"]
            if src not in self._diff_last_seen_ms:
                continue

            self._diff_last_seen_ms[src] = now
            self._diff_online[src] = True

            cmd = message["cmd"]
            if cmd == CMD_MODE_STATUS:
                payload = message["payload"]
                if len(payload) != 1:
                    continue

                mode = byte_to_mode(payload[0])
                if mode is None:
                    continue

                self._diff_modes[src] = mode
                continue

            if cmd == CMD_HEARTBEAT:
                continue

    def _send_heartbeats(self) -> None:
        """Send periodic heartbeat to front and rear diff nodes."""
        now = time.ticks_ms()
        elapsed = time.ticks_diff(now, self._last_heartbeat_ms)
        if elapsed < HEARTBEAT_INTERVAL_MS:
            return

        self._last_heartbeat_ms = now
        self._protocol.send_heartbeat(dst=NODE_ID_DIFF_FRONT)
        self._protocol.send_heartbeat(dst=NODE_ID_DIFF_REAR)

    def _update_online_flags(self) -> None:
        """Mark diff online/offline based on heartbeat timeout."""
        now = time.ticks_ms()
        for node_id, last_seen in self._diff_last_seen_ms.items():
            if last_seen == 0:
                self._diff_online[node_id] = False
                continue

            elapsed = time.ticks_diff(now, last_seen)
            self._diff_online[node_id] = elapsed <= HEARTBEAT_TIMEOUT_MS

    def step(self) -> None:
        """Run one control-loop cycle."""
        self._poll_buttons()
        self._send_heartbeats()
        self._process_incoming()
        self._update_online_flags()

    def run(self) -> None:
        """Run forever."""
        while True:
            self.step()
            time.sleep_ms(pins.MAIN_LOOP_DELAY_MS)


def main() -> None:
    """MicroPython entry point for central module."""
    app = CentralModuleApp()
    app.run()


if __name__ == "__main__":
    main()
