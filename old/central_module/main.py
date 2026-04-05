"""Main program for the central module.

This module reads local mode selector buttons and sends mode-change commands
over UART to a differential module.
"""

import time
from machine import UART

from common.protocol import SerialProtocol
from hardware.mode_selector import DriveModeSelector
from hardware.modes import DifferentialMode

from central_module import pins


class CentralModuleMain:
    """Central controller that sends mode requests to a diff module."""

    def __init__(self) -> None:
        self._uart = UART(
            pins.UART_ID,
            baudrate=pins.UART_BAUDRATE,
            tx=pins.UART_TX_PIN,
            rx=pins.UART_RX_PIN,
        )
        self._protocol = SerialProtocol(self._uart, node_id=pins.NODE_ID)

        self._outbound_modes = []
        self._last_sent_mode = DifferentialMode.UNKNOWN

        self.selector = DriveModeSelector(
            neutral_pin=pins.SELECTOR_NEUTRAL_PIN,
            limited_slip_pin=pins.SELECTOR_LIMITED_SLIP_PIN,
            locked_pin=pins.SELECTOR_LOCKED_PIN,
            use_interrupt=True,
            on_selection_change=self._on_selection_change,
        )

    def _on_selection_change(self, mode: str) -> None:
        """Queue outbound mode command when selection changes."""
        if not DifferentialMode.is_drive_mode(mode):
            return

        if self._outbound_modes and self._outbound_modes[-1] == mode:
            return

        self._outbound_modes.append(mode)

    def _process_outbound(self) -> None:
        """Send queued mode commands to the target diff module."""
        if not self._outbound_modes:
            return

        mode = self._outbound_modes.pop(0)
        sent = self._protocol.send_set_mode(
            dst=pins.TARGET_DIFF_NODE_ID,
            mode=mode,
        )
        if sent:
            self._last_sent_mode = mode

    def run(self) -> None:
        """Run forever."""
        while True:
            self.selector.update_all()
            self._process_outbound()
            time.sleep_ms(pins.MAIN_LOOP_DELAY_MS)


def main() -> None:
    """Entry point for MicroPython execution."""
    app = CentralModuleMain()
    app.run()


if __name__ == "__main__":
    main()
