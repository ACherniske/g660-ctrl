"""Operator mode selector input for local or central modules."""

from machine import Pin

from hardware.modes import DifferentialMode
from hardware.switch_input import SwitchManager


class DriveModeSelector(SwitchManager):
    """Read three mode-selection buttons: neutral, limited-slip, locked."""

    BUTTON_NEUTRAL = DifferentialMode.NEUTRAL
    BUTTON_LIMITED_SLIP = DifferentialMode.LIMITED_SLIP
    BUTTON_LOCKED = DifferentialMode.LOCKED

    def __init__(
        self,
        neutral_pin: int,
        limited_slip_pin: int,
        locked_pin: int,
        pull: int = Pin.PULL_UP,
        debounce_ms: int = 20,
        active_low: bool = True,
        use_interrupt: bool = True,
        on_selection_change=None,
    ) -> None:
        """Create selector input set.

        Args:
            on_selection_change: Optional callback ``fn(mode: str)`` called
                when resolved button mode changes.
        """
        super().__init__()
        self._on_selection_change = on_selection_change
        self._last_selection = DifferentialMode.UNKNOWN

        self.add_switch(
            name=self.BUTTON_NEUTRAL,
            pin=neutral_pin,
            pull=pull,
            debounce_ms=debounce_ms,
            active_low=active_low,
            use_interrupt=use_interrupt,
            on_change=self._handle_change,
        )
        self.add_switch(
            name=self.BUTTON_LIMITED_SLIP,
            pin=limited_slip_pin,
            pull=pull,
            debounce_ms=debounce_ms,
            active_low=active_low,
            use_interrupt=use_interrupt,
            on_change=self._handle_change,
        )
        self.add_switch(
            name=self.BUTTON_LOCKED,
            pin=locked_pin,
            pull=pull,
            debounce_ms=debounce_ms,
            active_low=active_low,
            use_interrupt=use_interrupt,
            on_change=self._handle_change,
        )

    def _handle_change(self, _name: str, _is_pressed: bool) -> None:
        """Emit selection callback when resolved mode changes."""
        selection = self.get_selected_mode()
        if selection == self._last_selection:
            return
        self._last_selection = selection
        if self._on_selection_change:
            self._on_selection_change(selection)

    def get_selected_mode(self) -> str:
        """Resolve selected mode from active buttons."""
        active = self.get_active_switches()

        if len(active) == 0:
            return DifferentialMode.UNKNOWN
        if len(active) > 1:
            return DifferentialMode.INVALID

        selected = next(iter(active))
        if DifferentialMode.is_drive_mode(selected):
            return selected
        return DifferentialMode.INVALID
