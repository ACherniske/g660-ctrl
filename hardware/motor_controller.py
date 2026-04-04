"""
Differential motor control module.

This module provides a small controller for a differential
motor actuator driven by two GPIO outputs. The actuator rotates clockwise
(CW) or counterclockwise (CCW) to move a rack-and-pinion mechanism into
different drive modes.
"""

from machine import Pin


class MotorController:
    """Control a bidirectional motor with two GPIO output pins.

    Args:
        cw_pin: GPIO pin number used for clockwise (CW) drive.
        ccw_pin: GPIO pin number used for counterclockwise (CCW) drive.
    """

    STATE_STOPPED = "stopped"
    STATE_CW = "cw"
    STATE_CCW = "ccw"

    def __init__(self, cw_pin: int, ccw_pin: int) -> None:
        """Initialize the motor controller and set a safe default state."""
        self._cw_pin = Pin(cw_pin, Pin.OUT)
        self._ccw_pin = Pin(ccw_pin, Pin.OUT)
        self._state = self.STATE_STOPPED
        self.stop()

    @property
    def state(self) -> str:
        """Return the current motor state.

        Returns:
            One of: ``"stopped"``, ``"cw"``, or ``"ccw"``.
        """
        return self._state

    def _set_outputs(self, cw_value: int, ccw_value: int) -> None:
        """Set raw GPIO output values for CW and CCW channels."""
        self._cw_pin.value(cw_value)
        self._ccw_pin.value(ccw_value)

    def cw(self) -> None:
        """Drive the motor clockwise (CW)."""
        self._set_outputs(1, 0)
        self._state = self.STATE_CW

    def ccw(self) -> None:
        """Drive the motor counterclockwise (CCW)."""
        self._set_outputs(0, 1)
        self._state = self.STATE_CCW

    def stop(self) -> None:
        """Stop motor output on both control lines."""
        self._set_outputs(0, 0)
        self._state = self.STATE_STOPPED
