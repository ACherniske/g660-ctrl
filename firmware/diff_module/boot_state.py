"""Persistent boot-state tracking for diff module.

Stores minimal reboot metadata to support watchdog loop protection.
"""

import ujson as json


class BootStateStore:
    """Small file-backed store for watchdog reboot diagnostics."""

    def __init__(self, path: str = "diff_boot_state.json") -> None:
        self._path = path

    def load(self) -> dict:
        """Load state dictionary, returning defaults on failure."""
        default_state = {
            "last_reset_reason": "none",
            "watchdog_reset_count": 0,
        }

        try:
            with open(self._path, "r") as handle:
                data = json.loads(handle.read())

            reason = data.get("last_reset_reason", "none")
            count = int(data.get("watchdog_reset_count", 0))
            if count < 0:
                count = 0

            return {
                "last_reset_reason": reason,
                "watchdog_reset_count": count,
            }
        except Exception:
            return default_state

    def mark_watchdog_timeout_reset(self) -> None:
        """Increment watchdog reset count and persist reason."""
        state = self.load()
        state["last_reset_reason"] = "heartbeat_timeout"
        state["watchdog_reset_count"] = int(state["watchdog_reset_count"]) + 1
        self._save(state)

    def clear_watchdog_reset_state(self) -> None:
        """Clear watchdog reset diagnostics after stable recovery."""
        self._save(
            {
                "last_reset_reason": "none",
                "watchdog_reset_count": 0,
            }
        )

    def _save(self, state: dict) -> None:
        """Persist state dictionary; best effort on embedded storage."""
        try:
            with open(self._path, "w") as handle:
                handle.write(json.dumps(state))
        except Exception:
            # Intentionally non-fatal.
            return