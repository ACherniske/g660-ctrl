"""Central module entry point.

Reads steering-wheel preset buttons, sends target modes to front/rear diff
modules, monitors module heartbeat, and tracks each diff's current mode.
"""

import time
from machine import I2C, Pin, UART

from central_module import config, pins
from central_module.display import CentralStatusDisplay, I2cBackpackLcd1602
from common.constants import (
    CMD_ACK,
    CMD_HEARTBEAT,
    CMD_SET_MODE,
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
        self._last_display_refresh_ms = 0
        self._command_blocked_until_ms = 0
        self._command_blocked_nodes = ""
        self._startup_ms = time.ticks_ms()
        self._pending_set_mode = {
            NODE_ID_DIFF_FRONT: None,
            NODE_ID_DIFF_REAR: None,
        }
        self._display = self._build_display()

    def _in_startup_grace(self) -> bool:
        """Return True while central is inside startup grace window."""
        elapsed = time.ticks_diff(time.ticks_ms(), self._startup_ms)
        return elapsed < config.STARTUP_GRACE_MS

    def _send_set_mode_with_tracking(self, node_id: int, mode: str) -> None:
        """Send set-mode and start ACK wait/retry tracking."""
        if not self._protocol.send_set_mode(node_id, mode):
            return

        self._pending_set_mode[node_id] = {
            "mode": mode,
            "attempts": 1,
            "last_sent_ms": time.ticks_ms(),
        }

    def _build_display(self):
        """Create optional LCD display wrapper if enabled in config."""
        if not config.DISPLAY_ENABLED:
            return None

        try:
            i2c = I2C(
                pins.DISPLAY_I2C_ID,
                scl=Pin(pins.DISPLAY_I2C_SCL_PIN),
                sda=Pin(pins.DISPLAY_I2C_SDA_PIN),
                freq=pins.DISPLAY_I2C_FREQ,
            )
            lcd = I2cBackpackLcd1602(
                i2c=i2c,
                address=pins.DISPLAY_I2C_ADDRESS,
                cols=pins.DISPLAY_COLS,
                rows=pins.DISPLAY_ROWS,
            )
            lcd.write_lines("g660 central", "starting...")
            return CentralStatusDisplay(lcd)
        except Exception:
            # Keep runtime alive even if display wiring/driver is unavailable.
            return None

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
        blocked_nodes = []
        startup_grace = self._in_startup_grace()

        if DifferentialMode.is_drive_mode(front_mode):
            if self._diff_online[NODE_ID_DIFF_FRONT] or startup_grace:
                self._send_set_mode_with_tracking(NODE_ID_DIFF_FRONT, front_mode)
            else:
                blocked_nodes.append("F")

        if DifferentialMode.is_drive_mode(rear_mode):
            if self._diff_online[NODE_ID_DIFF_REAR] or startup_grace:
                self._send_set_mode_with_tracking(NODE_ID_DIFF_REAR, rear_mode)
            else:
                blocked_nodes.append("R")

        if blocked_nodes:
            self._mark_command_blocked("+".join(blocked_nodes))

    def _mark_command_blocked(self, blocked_nodes: str) -> None:
        """Start temporary display indication for blocked preset commands."""
        self._command_blocked_nodes = blocked_nodes
        now = time.ticks_ms()
        self._command_blocked_until_ms = time.ticks_add(
            now,
            config.COMMAND_BLOCKED_INDICATOR_MS,
        )

    def _active_blocked_nodes(self):
        """Return active blocked-node indicator, if still within timeout."""
        if not self._command_blocked_nodes:
            return None

        now = time.ticks_ms()
        if time.ticks_diff(self._command_blocked_until_ms, now) <= 0:
            self._command_blocked_nodes = ""
            return None

        return self._command_blocked_nodes

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
            if cmd == CMD_ACK:
                payload = message["payload"]
                if len(payload) != 1:
                    continue

                if payload[0] == CMD_SET_MODE:
                    self._pending_set_mode[src] = None
                continue

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

    def _retry_pending_set_mode(self) -> None:
        """Retry set-mode commands that have not been acknowledged yet."""
        now = time.ticks_ms()

        for node_id in (NODE_ID_DIFF_FRONT, NODE_ID_DIFF_REAR):
            pending = self._pending_set_mode[node_id]
            if pending is None:
                continue

            if not self._diff_online[node_id] and not self._in_startup_grace():
                self._pending_set_mode[node_id] = None
                self._mark_command_blocked("F" if node_id == NODE_ID_DIFF_FRONT else "R")
                continue

            elapsed = time.ticks_diff(now, pending["last_sent_ms"])
            if elapsed < config.SET_MODE_ACK_TIMEOUT_MS:
                continue

            if pending["attempts"] >= config.SET_MODE_MAX_RETRIES:
                self._pending_set_mode[node_id] = None
                self._mark_command_blocked("F" if node_id == NODE_ID_DIFF_FRONT else "R")
                continue

            if not self._protocol.send_set_mode(node_id, pending["mode"]):
                self._pending_set_mode[node_id] = None
                continue

            pending["attempts"] += 1
            pending["last_sent_ms"] = now

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

    def _update_display(self) -> None:
        """Refresh optional LCD status display at configured interval."""
        if self._display is None:
            return

        now = time.ticks_ms()
        elapsed = time.ticks_diff(now, self._last_display_refresh_ms)
        if elapsed < config.DISPLAY_REFRESH_MS:
            return

        self._last_display_refresh_ms = now
        self._display.update(
            front_mode=self._diff_modes[NODE_ID_DIFF_FRONT],
            rear_mode=self._diff_modes[NODE_ID_DIFF_REAR],
            front_online=self._diff_online[NODE_ID_DIFF_FRONT],
            rear_online=self._diff_online[NODE_ID_DIFF_REAR],
            blocked_nodes=self._active_blocked_nodes(),
        )

    def step(self) -> None:
        """Run one control-loop cycle."""
        self._poll_buttons()
        self._send_heartbeats()
        self._process_incoming()
        self._update_online_flags()
        self._retry_pending_set_mode()
        self._update_display()

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
