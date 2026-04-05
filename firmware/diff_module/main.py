"""Diff module entry point.

This app receives mode commands (local buttons and/or UART), drives motor
transitions, and uses position sensors as the stop/completion authority.
"""

import time
import machine
from machine import Pin, UART

from common.constants import CMD_HEARTBEAT, CMD_SET_MODE, CMD_STATUS_REQUEST, NODE_ID_CENTRAL
from common.modes import DifferentialMode
from common.protocol import SerialProtocol, byte_to_mode
from common.switch_input import DiffModeButtons, DiffPositionSensors
from diff_module.boot_state import BootStateStore
from diff_module import pins
from diff_module.mode_selector import ModeSelector as RequestModeSelector
from diff_module.motor_controller import MotorController
from diff_module.transition_controller import TransitionController
from hardware.mode_selector import ModeSelector as InputModeResolver


_FAULT_NONE = "fault_cleared"


class DiffModuleApp:
    """Runtime application for a single differential controller module."""

    @staticmethod
    def _validate_configuration() -> None:
        """Fail fast on invalid deployment/config combinations."""
        if not pins.CENTRAL_CONTROL_ENABLED and not pins.LOCAL_SELECTOR_ENABLED:
            raise ValueError(
                "Invalid diff config: enable CENTRAL_CONTROL_ENABLED or LOCAL_SELECTOR_ENABLED."
            )

        if pins.TRAVEL_TIMEOUT_MS <= 0:
            raise ValueError("TRAVEL_TIMEOUT_MS must be > 0")

        if pins.HEARTBEAT_WATCHDOG_TIMEOUT_MS <= 0:
            raise ValueError("HEARTBEAT_WATCHDOG_TIMEOUT_MS must be > 0")

        if pins.CENTRAL_REPLY_BASE_DELAY_MS < 0:
            raise ValueError("CENTRAL_REPLY_BASE_DELAY_MS must be >= 0")

        if pins.CENTRAL_REPLY_NODE_STEP_MS < 0:
            raise ValueError("CENTRAL_REPLY_NODE_STEP_MS must be >= 0")

        if pins.SET_MODE_DEDUPE_WINDOW_MS < 0:
            raise ValueError("SET_MODE_DEDUPE_WINDOW_MS must be >= 0")

        if pins.MAX_WATCHDOG_REBOOTS < 1:
            raise ValueError("MAX_WATCHDOG_REBOOTS must be >= 1")

        if pins.WATCHDOG_RECOVERY_HEARTBEAT_COUNT < 1:
            raise ValueError("WATCHDOG_RECOVERY_HEARTBEAT_COUNT must be >= 1")

        used_pins = [
            pins.MOTOR_CW_PIN,
            pins.MOTOR_CCW_PIN,
            pins.POSITION_NEUTRAL_PIN,
            pins.POSITION_LIMITED_SLIP_PIN,
            pins.POSITION_LOCKED_PIN,
            pins.NODE_SELECT_PIN,
        ]

        if pins.CENTRAL_CONTROL_ENABLED:
            used_pins.extend([pins.UART_TX_PIN, pins.UART_RX_PIN])

        if pins.LOCAL_SELECTOR_ENABLED:
            used_pins.extend(
                [
                    pins.LOCAL_SELECTOR_NEUTRAL_PIN,
                    pins.LOCAL_SELECTOR_LIMITED_SLIP_PIN,
                    pins.LOCAL_SELECTOR_LOCKED_PIN,
                ]
            )

        if len(used_pins) != len(set(used_pins)):
            raise ValueError("Duplicate GPIO assignments detected in diff_module.pins")

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

        self._boot_state = BootStateStore(
            path=pins.BOOT_STATE_FILE,
            use_nvs=pins.BOOT_STATE_USE_NVS,
            nvs_namespace=pins.BOOT_STATE_NVS_NAMESPACE,
            write_min_interval_ms=pins.BOOT_STATE_WRITE_MIN_INTERVAL_MS,
        )
        self._boot_info = self._boot_state.load()
        self._watchdog_reset_count = self._boot_info["watchdog_reset_count"]
        self._degraded_mode = (
            pins.CENTRAL_CONTROL_ENABLED
            and pins.HEARTBEAT_WATCHDOG_ENABLED
            and self._watchdog_reset_count >= pins.MAX_WATCHDOG_REBOOTS
        )
        self._recovery_heartbeat_count = 0
        self._recent_set_mode_by_source = {}
        self._active_fault = None

        self._last_reported_sensor_mode = DifferentialMode.UNKNOWN
        self._last_central_heartbeat_ms = 0
        self._heartbeat_watchdog_armed = not pins.HEARTBEAT_WATCHDOG_REQUIRE_FIRST_HEARTBEAT

        if self._degraded_mode:
            self._transition.clear()
            self._motor.stop()

    def _on_mode_request(self, _mode: str) -> None:
        """Optional hook for telemetry or status indicators."""

    def _on_mode_applied(self, _mode: str) -> None:
        """Report applied mode to central module."""
        if self._protocol is None:
            return

        if DifferentialMode.is_drive_mode(_mode):
            self._send_mode_status_to_central(_mode)

    def _on_fault(self, _fault_code: str) -> None:
        """Optional hook for telemetry or status indicators."""
        if _fault_code == self._active_fault:
            return

        self._active_fault = _fault_code
        self._send_fault_to_central(_fault_code)

    def _central_reply_delay_ms(self) -> int:
        """Return deterministic per-node delay for central-bound replies."""
        if not pins.BUS_CONTENTION_MITIGATION_ENABLED:
            return 0

        node_offset = self._node_id & 0x0F
        return pins.CENTRAL_REPLY_BASE_DELAY_MS + (node_offset * pins.CENTRAL_REPLY_NODE_STEP_MS)

    def _delay_before_reply_to_central(self, source_id: int) -> None:
        """Delay short deterministic amount before replying to central."""
        if source_id != NODE_ID_CENTRAL:
            return

        delay_ms = self._central_reply_delay_ms()
        if delay_ms > 0:
            time.sleep_ms(delay_ms)

    def _send_mode_status_to_central(self, mode: str) -> None:
        """Send mode status to central with contention mitigation delay."""
        if self._protocol is None:
            return

        self._delay_before_reply_to_central(NODE_ID_CENTRAL)
        self._protocol.send_mode_status(NODE_ID_CENTRAL, mode)

    def _send_fault_to_central(self, fault_code: str) -> None:
        """Send one-byte fault telemetry event to central."""
        if self._protocol is None:
            return

        self._delay_before_reply_to_central(NODE_ID_CENTRAL)
        self._protocol.send_fault_status(NODE_ID_CENTRAL, fault_code)

    def _send_node_state_to(self, dst: int) -> None:
        """Send explicit node-state snapshot to destination."""
        if self._protocol is None:
            return

        self._delay_before_reply_to_central(dst)
        self._protocol.send_node_state(
            dst=dst,
            mode=self._last_reported_sensor_mode,
            degraded=self._degraded_mode,
        )

    def _is_duplicate_set_mode(self, source_id: int, seq: int) -> bool:
        """Return True when set-mode sequence is duplicate in dedupe window."""
        if seq is None:
            return False

        record = self._recent_set_mode_by_source.get(source_id)
        if record is None:
            self._recent_set_mode_by_source[source_id] = {
                "seq": seq,
                "ms": time.ticks_ms(),
            }
            return False

        elapsed = time.ticks_diff(time.ticks_ms(), record["ms"])
        is_duplicate = record["seq"] == seq and elapsed <= pins.SET_MODE_DEDUPE_WINDOW_MS
        if not is_duplicate:
            record["seq"] = seq
            record["ms"] = time.ticks_ms()

        return is_duplicate

    @staticmethod
    def _is_sensor_combo_valid(active_sensors: frozenset) -> bool:
        """Return True for allowed sensor combinations.

        Allowed:
        - no active sensor
        - one active sensor
        - overlap pairs N/L or L/K
        """
        if len(active_sensors) <= 1:
            return True

        if len(active_sensors) != 2:
            return False

        if (
            DifferentialMode.NEUTRAL in active_sensors
            and DifferentialMode.LIMITED_SLIP in active_sensors
        ):
            return True

        if (
            DifferentialMode.LIMITED_SLIP in active_sensors
            and DifferentialMode.LOCKED in active_sensors
        ):
            return True

        return False

    def _handle_remote_commands(self) -> None:
        """Handle UART commands and queue mode requests."""
        if self._protocol is None:
            return

        for message in self._protocol.poll():
            source_id = message["src"]
            cmd = message["cmd"]

            if cmd == CMD_SET_MODE:
                if self._degraded_mode:
                    continue

                payload = message["payload"]
                if len(payload) not in (1, 2):
                    continue

                requested_mode = byte_to_mode(payload[0])
                if requested_mode is None:
                    continue

                set_mode_seq = payload[1] if len(payload) == 2 else None

                if self._is_duplicate_set_mode(source_id, set_mode_seq):
                    self._delay_before_reply_to_central(source_id)
                    self._protocol.send_ack(
                        dst=source_id,
                        acked_cmd=CMD_SET_MODE,
                        seq=set_mode_seq,
                    )
                    continue

                self._transition.request_mode(requested_mode)
                self._delay_before_reply_to_central(source_id)
                self._protocol.send_ack(
                    dst=source_id,
                    acked_cmd=CMD_SET_MODE,
                    seq=set_mode_seq,
                )
                continue

            if cmd == CMD_STATUS_REQUEST:
                self._send_node_state_to(source_id)
                if self._active_fault is not None:
                    self._send_fault_to_central(self._active_fault)
                continue

            if cmd == CMD_HEARTBEAT:
                if source_id == NODE_ID_CENTRAL:
                    self._last_central_heartbeat_ms = time.ticks_ms()
                    self._heartbeat_watchdog_armed = True
                    self._handle_recovery_heartbeat()

                self._delay_before_reply_to_central(source_id)
                self._protocol.send_heartbeat(dst=source_id)
                if DifferentialMode.is_drive_mode(self._last_reported_sensor_mode):
                    self._protocol.send_mode_status(
                        dst=source_id,
                        mode=self._last_reported_sensor_mode,
                    )
                self._send_node_state_to(source_id)

    def _handle_recovery_heartbeat(self) -> None:
        """Count stable heartbeats to exit degraded mode safely."""
        if not self._degraded_mode:
            return

        self._recovery_heartbeat_count += 1
        if self._recovery_heartbeat_count < pins.WATCHDOG_RECOVERY_HEARTBEAT_COUNT:
            return

        self._degraded_mode = False
        self._recovery_heartbeat_count = 0
        self._watchdog_reset_count = 0
        self._boot_state.clear_watchdog_reset_state()
        self._send_fault_to_central(_FAULT_NONE)
        self._active_fault = None
        self._send_node_state_to(NODE_ID_CENTRAL)

    def _check_heartbeat_watchdog(self) -> None:
        """Reset module when central heartbeat is missing for too long."""
        if not pins.CENTRAL_CONTROL_ENABLED:
            return

        if self._degraded_mode:
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
        self._send_fault_to_central("heartbeat_timeout")
        self._boot_state.mark_watchdog_timeout_reset()
        machine.reset()

    def _handle_local_selector(self) -> None:
        """Queue mode requests from local selector buttons."""
        if self._degraded_mode:
            return

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
        active_sensors = self._position_inputs.get_active_switches()

        if not self._is_sensor_combo_valid(active_sensors):
            self._on_fault("sensor_invalid_combo")
            self._transition.clear()
            self._check_heartbeat_watchdog()
            return
        if self._active_fault == "sensor_invalid_combo":
            self._send_fault_to_central(_FAULT_NONE)
            self._active_fault = None

        if self._degraded_mode:
            if self._active_fault != "degraded_mode":
                self._on_fault("degraded_mode")
            self._transition.clear()
            self._motor.stop()
            self._check_heartbeat_watchdog()
            return

        if (
            sensor_mode != self._last_reported_sensor_mode
            and DifferentialMode.is_drive_mode(sensor_mode)
        ):
            self._last_reported_sensor_mode = sensor_mode
            if self._protocol is not None:
                self._send_mode_status_to_central(sensor_mode)

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
