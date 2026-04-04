"""
Position sensor handling for the differential motor.

The Grizzly 660 differential motor has three internal position sensors.
Each sensor acts like a switch to a reference pin when the actuator reaches
its corresponding mechanical position.
"""

from machine import Pin

from hardware.modes import DifferentialMode
from hardware.switch_input import SwitchManager


class DifferentialPositionSensors(SwitchManager):
    """Read and resolve differential mode from three position sensors.

    Sensors:
        - neutral
        - limited_slip
        - locked

    Exactly one sensor should be active in normal operation.
    """

    SENSOR_NEUTRAL = DifferentialMode.NEUTRAL
    SENSOR_LIMITED_SLIP = DifferentialMode.LIMITED_SLIP
    SENSOR_LOCKED = DifferentialMode.LOCKED

    def __init__(
        self,
        neutral_pin: int,
        limited_slip_pin: int,
        locked_pin: int,
        pull: int = Pin.PULL_UP,
        debounce_ms: int = 10,
        active_low: bool = True,
        use_interrupt: bool = False,
        on_mode_change=None,
    ) -> None:
        """Create the sensor bank.

        Args:
            neutral_pin: GPIO pin for neutral sensor.
            limited_slip_pin: GPIO pin for limited-slip sensor.
            locked_pin: GPIO pin for locked sensor.
            pull: Pull resistor config for all sensor inputs.
            debounce_ms: Input debounce in milliseconds.
            active_low: ``True`` when active sensor pulls line low.
            use_interrupt: Enable immediate edge handling.
            on_mode_change: Optional callback ``fn(mode: str)`` called when
                resolved mode changes.
        """
        super().__init__()
        self._on_mode_change = on_mode_change
        self._last_mode = DifferentialMode.UNKNOWN

        self.add_switch(
            name=self.SENSOR_NEUTRAL,
            pin=neutral_pin,
            pull=pull,
            debounce_ms=debounce_ms,
            active_low=active_low,
            use_interrupt=use_interrupt,
            on_change=self._handle_sensor_change,
        )
        self.add_switch(
            name=self.SENSOR_LIMITED_SLIP,
            pin=limited_slip_pin,
            pull=pull,
            debounce_ms=debounce_ms,
            active_low=active_low,
            use_interrupt=use_interrupt,
            on_change=self._handle_sensor_change,
        )
        self.add_switch(
            name=self.SENSOR_LOCKED,
            pin=locked_pin,
            pull=pull,
            debounce_ms=debounce_ms,
            active_low=active_low,
            use_interrupt=use_interrupt,
            on_change=self._handle_sensor_change,
        )

    def _handle_sensor_change(self, _name: str, _is_pressed: bool) -> None:
        """Handle any sensor transition and emit mode-change callback."""
        mode = self.get_mode()
        if mode == self._last_mode:
            return

        self._last_mode = mode
        if self._on_mode_change:
            self._on_mode_change(mode)

    def get_mode(self) -> str:
        """Return resolved current differential mode.

        Returns:
            ``neutral``, ``limited_slip``, or ``locked`` when exactly one
            sensor is active.
            ``unknown`` when no sensor is active.
            ``invalid`` when more than one sensor is active.
        """
        active = self.get_active_switches()

        if len(active) == 0:
            return DifferentialMode.UNKNOWN
        if len(active) > 1:
            return DifferentialMode.INVALID

        active_sensor = next(iter(active))
        if DifferentialMode.is_drive_mode(active_sensor):
            return active_sensor
        return DifferentialMode.INVALID

    def is_valid(self) -> bool:
        """Return ``True`` when exactly one position sensor is active."""
        return DifferentialMode.is_drive_mode(self.get_mode())

    @property
    def mode(self) -> str:
        """Return the currently resolved mode."""
        return self.get_mode()
