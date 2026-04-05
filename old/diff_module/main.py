"""Main control loop for an individual differential module.

This program runs on a diff controller board and does the following:
- reads local mode-selection buttons
- reads 3 internal motor position sensors (N, L, K)
- drives motor CW/CCW until requested mode is reached
- queues requests so moves complete one at a time
"""

import time
from machine import UART

from common.constants import CMD_SET_MODE
from common.protocol import SerialProtocol, byte_to_mode
from hardware.mode_selector import DriveModeSelector
from hardware.modes import DifferentialMode
from hardware.motor_controller import MotorController
from hardware.position_sensor import DifferentialPositionSensors

from diff_module import pins


class ModeRequestQueue:
    """FIFO queue for requested diff modes."""

    def __init__(self, max_size: int = 16) -> None:
        self._max_size = max_size
        self._items = []

    def enqueue(self, mode: str) -> bool:
        """Add a mode request.

        Returns ``True`` when queued, ``False`` when ignored.
        """
        if not DifferentialMode.is_drive_mode(mode):
            return False

        if self._items and self._items[-1] == mode:
            return False

        if len(self._items) >= self._max_size:
            self._items.pop(0)

        self._items.append(mode)
        return True

    def dequeue(self):
        """Pop and return the next mode request, or ``None`` if empty."""
        if not self._items:
            return None
        return self._items.pop(0)

    def peek(self):
        """Return next request without removing it."""
        if not self._items:
            return None
        return self._items[0]

    def __len__(self) -> int:
        return len(self._items)


class DifferentialActuatorController:
    """Run queued mode requests against motor and sensor feedback."""

    def __init__(
        self,
        motor: MotorController,
        sensors: DifferentialPositionSensors,
        cw_increases_mode_index: bool = True,
        travel_timeout_ms: int = 5000,
        on_mode_applied=None,
        on_fault=None,
    ) -> None:
        self._motor = motor
        self._sensors = sensors
        self._queue = ModeRequestQueue()
        self._cw_increases_mode_index = cw_increases_mode_index
        self._travel_timeout_ms = travel_timeout_ms
        self._on_mode_applied = on_mode_applied
        self._on_fault = on_fault

        self._active_target = None
        self._active_direction = 0
        self._motion_start_ms = 0
        self._required_exit_sensor = None
        self._last_known_mode = DifferentialMode.UNKNOWN

    def _notify_mode_applied(self, mode: str) -> None:
        """Notify external callback that a mode request completed."""
        if self._on_mode_applied:
            self._on_mode_applied(mode)

    def queue_mode(self, mode: str) -> bool:
        """Queue a mode request."""
        if mode == self._active_target:
            return False
        return self._queue.enqueue(mode)

    def _emit_fault(self, code: str) -> None:
        """Emit fault callback and stop motor."""
        self._motor.stop()
        self._active_target = None
        self._active_direction = 0
        self._required_exit_sensor = None
        if self._on_fault:
            self._on_fault(code)

    def _estimate_position_index(self, active_modes: frozenset):
        """Estimate mechanical position index from active sensors.

        Returns 0, 1, 2, or half-step overlap values (0.5, 1.5).
        """
        if len(active_modes) == 1:
            mode = next(iter(active_modes))
            return DifferentialMode.position_index(mode)

        if len(active_modes) == 2:
            if (
                DifferentialMode.NEUTRAL in active_modes
                and DifferentialMode.LIMITED_SLIP in active_modes
            ):
                return 0.5
            if (
                DifferentialMode.LIMITED_SLIP in active_modes
                and DifferentialMode.LOCKED in active_modes
            ):
                return 1.5

        if DifferentialMode.is_drive_mode(self._last_known_mode):
            return DifferentialMode.position_index(self._last_known_mode)

        return None

    def _resolve_direction(self, target_mode: str, active_modes: frozenset):
        """Resolve requested travel direction toward the target mode."""
        target_index = DifferentialMode.position_index(target_mode)
        position_index = self._estimate_position_index(active_modes)
        if target_index is None or position_index is None:
            return None

        if target_index > position_index:
            return 1
        if target_index < position_index:
            return -1

        # Equal index can occur in overlap when target is present with a neighbor.
        if target_mode in active_modes and len(active_modes) == 2:
            if (
                target_mode == DifferentialMode.LIMITED_SLIP
                and DifferentialMode.NEUTRAL in active_modes
            ):
                return 1
            if (
                target_mode == DifferentialMode.LIMITED_SLIP
                and DifferentialMode.LOCKED in active_modes
            ):
                return -1

        return 0

    def _drive_for_direction(self, direction: int) -> None:
        """Drive motor based on logical direction (-1 or +1)."""
        if direction == 0:
            self._motor.stop()
            return

        cw_for_positive = self._cw_increases_mode_index
        drive_cw = direction > 0 if cw_for_positive else direction < 0

        if drive_cw:
            self._motor.cw()
        else:
            self._motor.ccw()

    def _start_request(self, target_mode: str) -> None:
        """Start moving toward a queued target mode."""
        active = self._sensors.get_active_switches()

        if target_mode in active and len(active) == 1:
            self._notify_mode_applied(target_mode)
            return

        direction = self._resolve_direction(target_mode, active)
        if direction is None:
            self._emit_fault("position_unknown")
            return

        if direction == 0:
            # Already aligned enough to stop at target.
            self._motor.stop()
            self._notify_mode_applied(target_mode)
            return

        self._active_target = target_mode
        self._active_direction = direction
        self._motion_start_ms = time.ticks_ms()

        current_mode = self._sensors.get_mode()
        if DifferentialMode.is_drive_mode(current_mode) and current_mode != target_mode:
            self._required_exit_sensor = current_mode
        else:
            self._required_exit_sensor = None

        self._drive_for_direction(direction)

    def _is_target_reached(self, active_modes: frozenset) -> bool:
        """Check whether target completion condition is satisfied."""
        if self._active_target not in active_modes:
            return False

        # Do not stop while in overlap zones. Target must be the only active
        # sensor so a Neutral->Locked move passes both N/L and L/K overlaps.
        if len(active_modes) != 1:
            return False

        # Required behavior: keep moving until we leave starting position.
        if self._required_exit_sensor is not None:
            if self._required_exit_sensor in active_modes:
                return False

        return True

    def _update_last_known_mode(self) -> None:
        """Cache last stable single-sensor mode."""
        current_mode = self._sensors.get_mode()
        if DifferentialMode.is_drive_mode(current_mode):
            self._last_known_mode = current_mode

    def step(self) -> None:
        """Advance control state by one loop iteration."""
        self._sensors.update_all()
        self._update_last_known_mode()

        if self._active_target is None:
            next_mode = self._queue.dequeue()
            if next_mode is not None:
                self._start_request(next_mode)
            return

        now = time.ticks_ms()
        elapsed = time.ticks_diff(now, self._motion_start_ms)
        if elapsed > self._travel_timeout_ms:
            self._emit_fault("travel_timeout")
            return

        active = self._sensors.get_active_switches()
        if self._is_target_reached(active):
            reached_mode = self._active_target
            self._motor.stop()
            self._active_target = None
            self._active_direction = 0
            self._required_exit_sensor = None
            self._notify_mode_applied(reached_mode)


class DiffModuleMain:
    """Main application for an individual differential controller board."""

    def __init__(self) -> None:
        self.motor = MotorController(
            cw_pin=pins.MOTOR_CW_PIN,
            ccw_pin=pins.MOTOR_CCW_PIN,
        )

        self.position_sensors = DifferentialPositionSensors(
            neutral_pin=pins.POSITION_NEUTRAL_PIN,
            limited_slip_pin=pins.POSITION_LIMITED_SLIP_PIN,
            locked_pin=pins.POSITION_LOCKED_PIN,
            use_interrupt=False,
        )

        self.controller = DifferentialActuatorController(
            motor=self.motor,
            sensors=self.position_sensors,
            cw_increases_mode_index=pins.CW_INCREASES_MODE_INDEX,
            travel_timeout_ms=pins.TRAVEL_TIMEOUT_MS,
            on_mode_applied=self._on_mode_applied,
            on_fault=self._on_fault,
        )

        self.selector = DriveModeSelector(
            neutral_pin=pins.SELECTOR_NEUTRAL_PIN,
            limited_slip_pin=pins.SELECTOR_LIMITED_SLIP_PIN,
            locked_pin=pins.SELECTOR_LOCKED_PIN,
            use_interrupt=True,
            on_selection_change=self._on_selector_change,
        )

        self._uart = UART(
            pins.UART_ID,
            baudrate=pins.UART_BAUDRATE,
            tx=pins.UART_TX_PIN,
            rx=pins.UART_RX_PIN,
        )
        self._protocol = SerialProtocol(self._uart, node_id=pins.NODE_ID)

    def _on_selector_change(self, selected_mode: str) -> None:
        """Queue selector mode requests."""
        if DifferentialMode.is_drive_mode(selected_mode):
            self.controller.queue_mode(selected_mode)

    def _on_mode_applied(self, mode: str) -> None:
        """Handle successful mode application.

        Replace with status LED, CAN publish, or UART logging as needed.
        """
        _ = mode

    def _process_remote_commands(self) -> None:
        """Handle inbound mode commands from the central module."""
        messages = self._protocol.poll()
        for message in messages:
            if message["cmd"] != CMD_SET_MODE:
                continue

            payload = message["payload"]
            if len(payload) != 1:
                continue

            requested_mode = byte_to_mode(payload[0])
            if requested_mode is None:
                continue

            self.controller.queue_mode(requested_mode)

    def _on_fault(self, fault_code: str) -> None:
        """Handle movement fault conditions.

        Replace with fault LED, watchdog strategy, or telemetry publish.
        """
        _ = fault_code

    def run(self) -> None:
        """Run forever."""
        while True:
            self.selector.update_all()
            self._process_remote_commands()
            self.controller.step()
            time.sleep_ms(pins.MAIN_LOOP_DELAY_MS)


def main() -> None:
    """Entry point for MicroPython execution."""
    app = DiffModuleMain()
    app.run()


if __name__ == "__main__":
    main()
