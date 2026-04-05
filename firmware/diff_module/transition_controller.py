"""Diff module transition controller.

This module combines `ModeSelector` request/queue state with `MotorController`
actuation. Position sensors remain the source of truth for transition
completion.
"""

import time

from common.modes import DifferentialMode


class TransitionController:
    """Drive motor transitions toward selector targets.

    Args:
        mode_selector: `ModeSelector` instance.
        motor: `MotorController` instance.
        cw_increases_mode_index: `True` when CW means N -> L -> K.
        travel_timeout_ms: Max travel time for one transition.
        on_fault: Optional callback `fn(code: str)`.
    """

    def __init__(
        self,
        mode_selector,
        motor,
        cw_increases_mode_index: bool = True,
        travel_timeout_ms: int = 5000,
        on_fault=None,
    ) -> None:
        self._selector = mode_selector
        self._motor = motor
        self._cw_increases_mode_index = cw_increases_mode_index
        self._travel_timeout_ms = travel_timeout_ms
        self._on_fault = on_fault

        self._motion_start_ms = 0
        self._last_stable_mode = DifferentialMode.UNKNOWN

    def request_mode(self, mode: str) -> bool:
        """Queue a mode request through the selector."""
        return self._selector.request_mode(mode)

    def clear(self) -> None:
        """Stop motor and clear selector queue/active target."""
        self._motor.stop()
        self._motion_start_ms = 0
        self._selector.clear()

    def step(self, sensor_mode: str, active_sensors: frozenset = None):
        """Advance one transition-control cycle.

        Args:
            sensor_mode: Mode resolved from position sensors.
            active_sensors: Optional active sensor-name set. Used to identify
                overlap zones (N/L and L/K) precisely.

        Returns:
            Applied mode when a transition completes, else `None`.
        """
        if DifferentialMode.is_drive_mode(sensor_mode):
            self._last_stable_mode = sensor_mode

        applied = self._selector.update_position_mode(sensor_mode)
        if applied is not None:
            self._motor.stop()
            self._motion_start_ms = 0

        active_target = self._selector.active_target
        if active_target is None:
            active_target = self._selector.activate_next()
            if active_target is not None:
                self._motion_start_ms = 0

        if active_target is None:
            self._motor.stop()
            return applied

        direction = self._resolve_direction(active_target, sensor_mode, active_sensors)
        if direction is None:
            self._emit_fault("position_unknown")
            return None

        if direction == 0:
            return self._selector.update_position_mode(active_target)

        if self._motion_start_ms == 0:
            self._motion_start_ms = time.ticks_ms()
        elif self._travel_timeout_expired():
            self._emit_fault("travel_timeout")
            return None

        self._drive_direction(direction)
        return applied

    def _resolve_direction(
        self,
        target_mode: str,
        sensor_mode: str,
        active_sensors: frozenset,
    ):
        """Return -1, 0, +1 toward target; `None` if unknown position."""
        target_index = DifferentialMode.position_index(target_mode)
        if target_index is None:
            return None

        current_index = self._estimate_position_index(sensor_mode, active_sensors)
        if current_index is None:
            return None

        if target_index > current_index:
            return 1
        if target_index < current_index:
            return -1
        return 0

    def _estimate_position_index(self, sensor_mode: str, active_sensors: frozenset):
        """Estimate position index including overlap zones.

        Returns:
            0, 1, 2 for stable N/L/K positions,
            0.5 for N/L overlap,
            1.5 for L/K overlap,
            or `None` if unknown.
        """
        if active_sensors is not None:
            if (
                DifferentialMode.NEUTRAL in active_sensors
                and DifferentialMode.LIMITED_SLIP in active_sensors
                and len(active_sensors) == 2
            ):
                return 0.5
            if (
                DifferentialMode.LIMITED_SLIP in active_sensors
                and DifferentialMode.LOCKED in active_sensors
                and len(active_sensors) == 2
            ):
                return 1.5

        current_index = DifferentialMode.position_index(sensor_mode)
        if current_index is not None:
            return current_index

        return DifferentialMode.position_index(self._last_stable_mode)

    def _drive_direction(self, direction: int) -> None:
        """Drive motor according to logical direction."""
        drive_cw = direction > 0 if self._cw_increases_mode_index else direction < 0
        if drive_cw:
            self._motor.cw()
        else:
            self._motor.ccw()

    def _travel_timeout_expired(self) -> bool:
        """Return `True` when current transition exceeded timeout."""
        elapsed_ms = time.ticks_diff(time.ticks_ms(), self._motion_start_ms)
        return elapsed_ms > self._travel_timeout_ms

    def _emit_fault(self, code: str) -> None:
        """Stop motion and publish fault callback."""
        self._motor.stop()
        self._motion_start_ms = 0
        self._selector.clear()
        if self._on_fault is not None:
            self._on_fault(code)
