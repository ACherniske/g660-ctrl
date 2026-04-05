"""Generic command-driven mode transition manager for the differential module.

This selector tracks current mode, queues requested mode transitions, and
completes transitions based on position-sensor mode updates.
"""

from common.modes import DifferentialMode


class ModeSelector:
    """Manage mode requests and transitions for N/L/K drive modes.

    Args:
        queue_size: Maximum queued requests.
        on_mode_request: Optional callback ``fn(target_mode: str)``.
        on_mode_applied: Optional callback ``fn(applied_mode: str)``.
    """

    def __init__(
        self,
        queue_size: int = 8,
        on_mode_request=None,
        on_mode_applied=None,
    ) -> None:
        self._queue_size = queue_size
        self._on_mode_request = on_mode_request
        self._on_mode_applied = on_mode_applied

        self._current_mode = DifferentialMode.UNKNOWN
        self._active_target = None
        self._request_queue = []

    @property
    def current_mode(self) -> str:
        """Return last mode reported by position sensors."""
        return self._current_mode

    @property
    def active_target(self):
        """Return currently active target mode, or ``None``."""
        return self._active_target

    def request_mode(self, mode: str) -> bool:
        """Queue a new mode request.

        Returns:
            ``True`` when queued, ``False`` when ignored.
        """
        if not DifferentialMode.is_drive_mode(mode):
            return False

        if mode == self._active_target:
            return False

        if self._request_queue and self._request_queue[-1] == mode:
            return False

        if len(self._request_queue) >= self._queue_size:
            self._request_queue.pop(0)

        self._request_queue.append(mode)
        if self._on_mode_request is not None:
            self._on_mode_request(mode)
        return True

    def activate_next(self):
        """Activate and return the next queued target mode.

        Returns ``None`` when queue is empty.
        """
        if self._active_target is not None:
            return self._active_target
        if not self._request_queue:
            return None

        self._active_target = self._request_queue.pop(0)
        return self._active_target

    def update_position_mode(self, sensor_mode: str):
        """Update mode from position sensors and complete targets when reached.

        Position sensors define stop conditions. When ``sensor_mode`` reaches
        the active target, the transition is considered complete.

        Returns:
            Applied mode when a transition completes, else ``None``.
        """
        if sensor_mode != self._current_mode:
            self._current_mode = sensor_mode

        if self._active_target is None:
            return None
        if sensor_mode != self._active_target:
            return None

        applied_mode = self._active_target
        self._active_target = None
        if self._on_mode_applied is not None:
            self._on_mode_applied(applied_mode)
        return applied_mode

    def clear(self) -> None:
        """Clear pending and active mode requests."""
        self._request_queue = []
        self._active_target = None
