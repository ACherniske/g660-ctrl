"""Diff module entry point.

This app receives mode commands (local buttons and/or UART), drives motor
transitions, and uses position sensors as the stop/completion authority.
"""

import time
import machine
from machine import Pin, UART

from common.constants import CMD_HEARTBEAT, CMD_SET_MODE, NODE_ID_CENTRAL
from common.modes import DifferentialMode
from common.protocol import SerialProtocol, byte_to_mode
from common.switch_input import DiffModeButtons, DiffPositionSensors
from diff_module import pins
from diff_module.mode_selector import ModeSelector as RequestModeSelector
from diff_module.motor_controller import MotorController
from diff_module.transition_controller import TransitionController
from hardware.mode_selector import ModeSelector as InputModeResolver


class DiffModuleApp:
    """Runtime application for a single differential controller module."""

    @staticmethod
    def _validate_configuration() -> None:
        """Fail fast on invalid deployment/config combinations."""
        if not pins.CENTRAL_CONTROL_ENABLED and not pins.LOCAL_SELECTOR_ENABLED:
            raise ValueError(
                "Invalid diff config: enable CENTRAL_CONTROL_ENABLED or LOCAL_SELECTOR_ENABLED."
            )

    @staticmethod
    def _resolve_pull_mode(pull_setting: str) -> int:
        """Map pull setting string to machine Pin pull mode."""
        if pull_setting == "down":
            return Pin.PULL_DOWN
        return Pin.PULL_UP

    def _resolve_node_id(self) -> int:
        """Resolve front/rear node ID from solder-jumper select pin."""
        select_pin = Pin(
            pins.NODE_SELECT_PIN,
            Pin.IN,
            self._resolve_pull_mode(pins.NODE_SELECT_PULL),
        )
        level_high = bool(select_pin.value())
        is_front = level_high if pins.NODE_SELECT_HIGH_IS_FRONT else not level_high
        return pins.NODE_ID_FRONT if is_front else pins.NODE_ID_REAR

    def __init__(self) -> None:
        self._validate_configuration()

        pull_mode = Pin.PULL_UP if pins.INPUT_PULL_UP else Pin.PULL_DOWN
        self._node_id = self._resolve_node_id()

        self._motor = MotorController(
            cw_pin=pins.MOTOR_CW_PIN,
            ccw_pin=pins.MOTOR_CCW_PIN,
        )

        self._request_selector = RequestModeSelector(
            on_mode_request=self._on_mode_request,
            on_mode_applied=self._on_mode_applied,
        )

        self._transition = TransitionController(
            mode_selector=self._request_selector,
            motor=self._motor,
            cw_increases_mode_index=pins.CW_INCREASES_MODE_INDEX,
            travel_timeout_ms=pins.TRAVEL_TIMEOUT_MS,
            on_fault=self._on_fault,
        )

        self._position_inputs = DiffPositionSensors(
            input_a_pin=pins.POSITION_NEUTRAL_PIN,
            input_b_pin=pins.POSITION_LIMITED_SLIP_PIN,
            input_c_pin=pins.POSITION_LOCKED_PIN,
            pull=pull_mode,
            debounce_ms=pins.INPUT_DEBOUNCE_MS,
            active_low=pins.INPUT_ACTIVE_LOW,
        )
        self._position_mode = InputModeResolver(input_bank=self._position_inputs)

        self._local_selector = None
        self._local_selector_mode = None
        if pins.LOCAL_SELECTOR_ENABLED:
            self._local_selector = DiffModeButtons(
                input_a_pin=pins.LOCAL_SELECTOR_NEUTRAL_PIN,
                input_b_pin=pins.LOCAL_SELECTOR_LIMITED_SLIP_PIN,
                input_c_pin=pins.LOCAL_SELECTOR_LOCKED_PIN,
                pull=pull_mode,
                debounce_ms=pins.INPUT_DEBOUNCE_MS,
                active_low=pins.INPUT_ACTIVE_LOW,
            )
            self._local_selector_mode = InputModeResolver(input_bank=self._local_selector)

        self._uart = None
        self._protocol = None
        if pins.CENTRAL_CONTROL_ENABLED:
            self._uart = UART(
                pins.UART_ID,
                baudrate=pins.UART_BAUDRATE,
                tx=pins.UART_TX_PIN,
                rx=pins.UART_RX_PIN,
            )
            self._protocol = SerialProtocol(self._uart, node_id=self._node_id)

        self._last_reported_sensor_mode = DifferentialMode.UNKNOWN
        self._last_central_heartbeat_ms = 0
        self._heartbeat_watchdog_armed = not pins.HEARTBEAT_WATCHDOG_REQUIRE_FIRST_HEARTBEAT

    def _on_mode_request(self, _mode: str) -> None:
        """Optional hook for telemetry or status indicators."""

    def _on_mode_applied(self, _mode: str) -> None:
        """Report applied mode to central module."""
        if self._protocol is None:
            return

        if DifferentialMode.is_drive_mode(_mode):
            self._protocol.send_mode_status(NODE_ID_CENTRAL, _mode)

    def _on_fault(self, _fault_code: str) -> None:
        """Optional hook for telemetry or status indicators."""

    def _handle_remote_commands(self) -> None:
        """Handle UART commands and queue mode requests."""
        if self._protocol is None:
            return

        for message in self._protocol.poll():
            source_id = message["src"]
            cmd = message["cmd"]

            if cmd == CMD_SET_MODE:
                payload = message["payload"]
                if len(payload) != 1:
                    continue

                requested_mode = byte_to_mode(payload[0])
                if requested_mode is None:
                    continue

                self._transition.request_mode(requested_mode)
                self._protocol.send_ack(dst=source_id, acked_cmd=CMD_SET_MODE)
                continue

            if cmd == CMD_HEARTBEAT:
                if source_id == NODE_ID_CENTRAL:
                    self._last_central_heartbeat_ms = time.ticks_ms()
                    self._heartbeat_watchdog_armed = True

                self._protocol.send_heartbeat(dst=source_id)
                if DifferentialMode.is_drive_mode(self._last_reported_sensor_mode):
                    self._protocol.send_mode_status(
                        dst=source_id,
                        mode=self._last_reported_sensor_mode,
                    )

    def _check_heartbeat_watchdog(self) -> None:
        """Reset module when central heartbeat is missing for too long."""
        if not pins.CENTRAL_CONTROL_ENABLED:
            return

        if not pins.HEARTBEAT_WATCHDOG_ENABLED:
            return

        if not self._heartbeat_watchdog_armed:
            return

        if self._last_central_heartbeat_ms == 0:
            return

        now = time.ticks_ms()
        elapsed = time.ticks_diff(now, self._last_central_heartbeat_ms)
        if elapsed <= pins.HEARTBEAT_WATCHDOG_TIMEOUT_MS:
            return

        # Fail safe: stop outputs before reset.
        self._motor.stop()
        machine.reset()

    def _handle_local_selector(self) -> None:
        """Queue mode requests from local selector buttons."""
        if self._local_selector_mode is None:
            return

        selected_mode = self._local_selector_mode.update()
        if not self._local_selector_mode.pop_mode_changed():
            return

        if DifferentialMode.is_drive_mode(selected_mode):
            self._transition.request_mode(selected_mode)

    def step(self) -> None:
        """Run one control-loop cycle."""
        self._handle_remote_commands()
        self._handle_local_selector()

        sensor_mode = self._position_mode.update()
        if (
            sensor_mode != self._last_reported_sensor_mode
            and DifferentialMode.is_drive_mode(sensor_mode)
        ):
            self._last_reported_sensor_mode = sensor_mode
            if self._protocol is not None:
                self._protocol.send_mode_status(NODE_ID_CENTRAL, sensor_mode)

        active_sensors = self._position_inputs.get_active_switches()
        self._transition.step(sensor_mode, active_sensors=active_sensors)
        self._check_heartbeat_watchdog()

    def run(self) -> None:
        """Run forever."""
        while True:
            self.step()
            time.sleep_ms(pins.MAIN_LOOP_DELAY_MS)


def main() -> None:
    """MicroPython entry point for diff module."""
    app = DiffModuleApp()
    app.run()


if __name__ == "__main__":
    main()
