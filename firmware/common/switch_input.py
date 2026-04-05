"""Switch input abstractions for firmware.

This module provides:
- debounced named digital inputs
- grouped switch collections
- named three-input banks used by:
  - differential module buttons
  - wheel/central module buttons
  - differential position sensors
"""

from machine import Pin
import time


class SwitchInput:
    """One debounced digital switch input.

    Args:
        name: Logical switch name.
        pin: GPIO number.
        pull: Pull mode (for example ``Pin.PULL_UP``).
        debounce_ms: Debounce interval in milliseconds.
        active_low: ``True`` when active state is logic low.
        on_change: Optional callback ``fn(name, is_active)``.
    """

    def __init__(
        self,
        name: str,
        pin: int,
        pull: int = Pin.PULL_UP,
        debounce_ms: int = 25,
        active_low: bool = True,
        on_change=None,
    ) -> None:
        self._name = name
        self._pin = Pin(pin, Pin.IN, pull)
        self._debounce_ms = debounce_ms
        self._active_low = active_low
        self._on_change = on_change

        self._state = self._read_raw_state()
        self._last_raw_state = self._state
        self._last_transition_ms = time.ticks_ms()

        self._pressed_event = False
        self._released_event = False

    @property
    def name(self) -> str:
        """Return the configured switch name."""
        return self._name

    @property
    def is_active(self) -> bool:
        """Return current logical active state."""
        return self._state

    def was_pressed(self) -> bool:
        """Return ``True`` once for a rising active edge."""
        if not self._pressed_event:
            return False
        self._pressed_event = False
        return True

    def was_released(self) -> bool:
        """Return ``True`` once for a falling active edge."""
        if not self._released_event:
            return False
        self._released_event = False
        return True

    def update(self) -> None:
        """Update input state in polling mode."""
        self._process_state_transition()

    def _read_raw_state(self) -> bool:
        """Read pin value and convert to logical state."""
        value = self._pin.value()
        return not value if self._active_low else bool(value)

    def _process_state_transition(self) -> None:
        """Run debounce and emit events on stable changes."""
        now = time.ticks_ms()
        raw_state = self._read_raw_state()

        if raw_state == self._last_raw_state:
            return

        elapsed_ms = time.ticks_diff(now, self._last_transition_ms)
        if elapsed_ms < self._debounce_ms:
            return

        self._last_transition_ms = now
        self._last_raw_state = raw_state
        self._state = raw_state

        if raw_state:
            self._pressed_event = True
        else:
            self._released_event = True

        self._emit_change()

    def _emit_change(self) -> None:
        """Dispatch ``on_change`` callback."""
        if self._on_change is None:
            return
        self._on_change(self._name, self._state)


class SwitchCollection:
    """Container for named switch inputs."""

    def __init__(self) -> None:
        self._switches = {}

    def add_switch(
        self,
        name: str,
        pin: int,
        pull: int = Pin.PULL_UP,
        debounce_ms: int = 25,
        active_low: bool = True,
        on_change=None,
    ) -> None:
        """Register one switch."""
        self._switches[name] = SwitchInput(
            name=name,
            pin=pin,
            pull=pull,
            debounce_ms=debounce_ms,
            active_low=active_low,
            on_change=on_change,
        )

    def update_all(self) -> None:
        """Update all switches."""
        for switch in self._switches.values():
            switch.update()

    def get_switch(self, name: str):
        """Return switch by name, or ``None``."""
        return self._switches.get(name)

    def is_active(self, name: str) -> bool:
        """Return active state for named switch."""
        switch = self._switches.get(name)
        return switch.is_active if switch else False

    def get_active_switches(self) -> frozenset:
        """Return currently active switch names."""
        return frozenset(
            name
            for name, switch in self._switches.items()
            if switch.is_active
        )


class ThreeInputBank(SwitchCollection):
    """Three named switch inputs with no mode-processing logic.

    This class is intentionally I/O-only. It exposes raw switch states so mode
    selection and interpretation can be handled in the mode selector module.
    """

    INPUT_A = "a"
    INPUT_B = "b"
    INPUT_C = "c"

    def __init__(
        self,
        input_a_pin: int,
        input_b_pin: int,
        input_c_pin: int,
        pull: int = Pin.PULL_UP,
        debounce_ms: int = 25,
        active_low: bool = True,
        on_change=None,
    ) -> None:
        super().__init__()

        self.add_switch(
            name=self.INPUT_A,
            pin=input_a_pin,
            pull=pull,
            debounce_ms=debounce_ms,
            active_low=active_low,
            on_change=on_change,
        )
        self.add_switch(
            name=self.INPUT_B,
            pin=input_b_pin,
            pull=pull,
            debounce_ms=debounce_ms,
            active_low=active_low,
            on_change=on_change,
        )
        self.add_switch(
            name=self.INPUT_C,
            pin=input_c_pin,
            pull=pull,
            debounce_ms=debounce_ms,
            active_low=active_low,
            on_change=on_change,
        )

    def states(self) -> dict:
        """Return active-state mapping for inputs A/B/C."""
        return {
            self.INPUT_A: self.is_active(self.INPUT_A),
            self.INPUT_B: self.is_active(self.INPUT_B),
            self.INPUT_C: self.is_active(self.INPUT_C),
        }


class DiffModeButtons(ThreeInputBank):
    """Raw three-input bank for local differential buttons.

    Input labels map to positions left-to-right:
    A=neutral, B=limited_slip, C=locked.
    """

    INPUT_A = "neutral"
    INPUT_B = "limited_slip"
    INPUT_C = "locked"


class WheelModeButtons(ThreeInputBank):
    """Raw three-input bank for wheel mode buttons.

    Input labels map to positions left-to-right:
    A=neutral, B=limited_slip, C=locked.
    """

    INPUT_A = "neutral"
    INPUT_B = "limited_slip"
    INPUT_C = "locked"


class DiffPositionSensors(ThreeInputBank):
    """Raw three-input bank for differential position sensors.

    Input labels map to positions left-to-right:
    A=neutral, B=limited_slip, C=locked.
    """

    INPUT_A = "neutral"
    INPUT_B = "limited_slip"
    INPUT_C = "locked"
