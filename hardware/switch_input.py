"""Switch input primitives.

This module is intentionally minimal: it handles debounced, named switch
inputs and optional interrupt-driven callbacks.
"""

from machine import Pin
import time

try:
    import micropython
except ImportError:
    micropython = None


class Switch:
    """Represent a debounced, named digital switch input.

    Args:
        name: Human-readable switch identifier.
        pin: GPIO pin number.
        pull: Pull configuration (for example ``Pin.PULL_UP``).
        debounce_ms: Debounce duration in milliseconds.
        active_low: ``True`` when pressed state is logic low.
        use_interrupt: Enable pin interrupt handling when ``True``.
        on_change: Optional callback called on any stable edge.
        on_press: Optional callback called on press edge.
        on_release: Optional callback called on release edge.
    """

    EVENT_CHANGE = 0
    EVENT_PRESS = 1
    EVENT_RELEASE = 2

    def __init__(
        self,
        name: str,
        pin: int,
        pull: int = Pin.PULL_UP,
        debounce_ms: int = 50,
        active_low: bool = True,
        use_interrupt: bool = True,
        on_change=None,
        on_press=None,
        on_release=None,
    ) -> None:
        self._name = name
        self._pin = Pin(pin, Pin.IN, pull)
        self._debounce_ms = debounce_ms
        self._active_low = active_low
        self._on_change = on_change
        self._on_press = on_press
        self._on_release = on_release

        self._last_raw_state = self._read_raw()
        self._pressed = self._last_raw_state
        self._last_change_time = time.ticks_ms()
        self._press_detected = False
        self._release_detected = False

        if use_interrupt:
            trigger_mask = Pin.IRQ_RISING | Pin.IRQ_FALLING
            self._pin.irq(trigger=trigger_mask, handler=self._irq_handler)

    @property
    def name(self) -> str:
        """Return the configured switch name."""
        return self._name

    def _read_raw(self) -> bool:
        """Read raw pin input and return logical pressed state."""
        raw_value = self._pin.value()
        return not raw_value if self._active_low else bool(raw_value)

    def update(self) -> None:
        """Update switch state with debounce logic.

        Call this in the main loop when polling mode is used.
        """
        self._process_state_change()

    def _irq_handler(self, _pin) -> None:
        """Handle pin interrupt and process state transition quickly."""
        self._process_state_change()

    def _process_state_change(self) -> None:
        """Process debounced state transitions and edge events."""
        now = time.ticks_ms()
        raw_state = self._read_raw()

        if raw_state == self._last_raw_state:
            return

        stable_for_ms = time.ticks_diff(now, self._last_change_time)
        if stable_for_ms < self._debounce_ms:
            return

        self._last_change_time = now
        self._last_raw_state = raw_state
        self._pressed = raw_state

        self._trigger_event(self.EVENT_CHANGE)
        if raw_state:
            self._press_detected = True
            self._trigger_event(self.EVENT_PRESS)
        else:
            self._release_detected = True
            self._trigger_event(self.EVENT_RELEASE)

    def _trigger_event(self, event_type: int) -> None:
        """Run event callbacks; schedule when runtime support is available."""
        if micropython is not None:
            try:
                micropython.schedule(self._dispatch_event, event_type)
                return
            except RuntimeError:
                # Scheduler queue can be full; fallback to direct dispatch.
                pass
        self._dispatch_event(event_type)

    def _dispatch_event(self, event_type: int) -> None:
        """Dispatch callbacks with ``(name, is_pressed)`` arguments."""
        callback = None
        if event_type == self.EVENT_CHANGE:
            callback = self._on_change
        elif event_type == self.EVENT_PRESS:
            callback = self._on_press
        elif event_type == self.EVENT_RELEASE:
            callback = self._on_release

        if callback is not None:
            callback(self._name, self._pressed)

    @property
    def is_pressed(self) -> bool:
        """Return ``True`` when the switch is currently pressed."""
        return self._pressed

    def was_pressed(self) -> bool:
        """Return ``True`` once when a press edge is detected."""
        if not self._press_detected:
            return False
        self._press_detected = False
        return True

    def was_released(self) -> bool:
        """Return ``True`` once when a release edge is detected."""
        if not self._release_detected:
            return False
        self._release_detected = False
        return True


class SwitchManager:
    """Manage multiple named switches."""

    def __init__(self) -> None:
        self._switches = {}

    def add_switch(
        self,
        name: str,
        pin: int,
        pull: int = Pin.PULL_UP,
        debounce_ms: int = 50,
        active_low: bool = True,
        use_interrupt: bool = True,
        on_change=None,
        on_press=None,
        on_release=None,
    ) -> None:
        """Register a named switch in the manager."""
        self._switches[name] = Switch(
            name=name,
            pin=pin,
            pull=pull,
            debounce_ms=debounce_ms,
            active_low=active_low,
            use_interrupt=use_interrupt,
            on_change=on_change,
            on_press=on_press,
            on_release=on_release,
        )

    def update_all(self) -> None:
        """Update all registered switches."""
        for switch in self._switches.values():
            switch.update()

    def get_switch(self, name: str):
        """Return a switch object by name, or ``None`` if not found."""
        return self._switches.get(name)

    def has_switch(self, name: str) -> bool:
        """Return ``True`` when a switch name is registered."""
        return name in self._switches

    def remove_switch(self, name: str) -> bool:
        """Remove a switch by name.

        Returns:
            ``True`` if the switch existed and was removed.
        """
        if name not in self._switches:
            return False
        del self._switches[name]
        return True

    def is_pressed(self, name: str) -> bool:
        """Return current pressed state for a named switch."""
        switch = self._switches.get(name)
        return switch.is_pressed if switch else False

    def was_pressed(self, name: str) -> bool:
        """Return ``True`` once when a named switch is pressed."""
        switch = self._switches.get(name)
        return switch.was_pressed() if switch else False

    def was_released(self, name: str) -> bool:
        """Return ``True`` once when a named switch is released."""
        switch = self._switches.get(name)
        return switch.was_released() if switch else False

    def get_all_states(self) -> dict:
        """Return a mapping of switch name to current pressed state."""
        return {
            name: switch.is_pressed
            for name, switch in self._switches.items()
        }

    def get_active_switches(self) -> frozenset:
        """Return a ``frozenset`` of currently pressed switch names."""
        return frozenset(
            name
            for name, switch in self._switches.items()
            if switch.is_pressed
        )
