"""Persistent boot-state tracking for diff module.

Stores minimal reboot metadata to support watchdog loop protection.
"""

import ujson as json
import time


_REASON_TO_CODE = {
    "none": 0,
    "heartbeat_timeout": 1,
}

_CODE_TO_REASON = {value: key for key, value in _REASON_TO_CODE.items()}


class BootStateStore:
    """Small file-backed store for watchdog reboot diagnostics."""

    def __init__(
        self,
        path: str = "diff_boot_state.json",
        use_nvs: bool = True,
        nvs_namespace: str = "g660diff",
        write_min_interval_ms: int = 1000,
    ) -> None:
        self._path = path
        self._use_nvs = use_nvs
        self._nvs_namespace = nvs_namespace
        self._write_min_interval_ms = write_min_interval_ms
        self._last_write_ms = 0
        self._cached_state = None

        self._nvs = None
        if self._use_nvs:
            try:
                import esp32

                self._nvs = esp32.NVS(self._nvs_namespace)
            except Exception:
                self._nvs = None

    def load(self) -> dict:
        """Load state dictionary, returning defaults on failure."""
        default_state = {
            "last_reset_reason": "none",
            "watchdog_reset_count": 0,
        }

        if self._cached_state is not None:
            return {
                "last_reset_reason": self._cached_state["last_reset_reason"],
                "watchdog_reset_count": self._cached_state["watchdog_reset_count"],
            }

        state = self._load_from_nvs()
        if state is not None:
            self._cached_state = state
            return {
                "last_reset_reason": state["last_reset_reason"],
                "watchdog_reset_count": state["watchdog_reset_count"],
            }

        try:
            with open(self._path, "r") as handle:
                data = json.loads(handle.read())

            reason = data.get("last_reset_reason", "none")
            count = int(data.get("watchdog_reset_count", 0))
            if count < 0:
                count = 0

            state = {
                "last_reset_reason": reason,
                "watchdog_reset_count": count,
            }
            self._cached_state = state
            return state
        except Exception:
            self._cached_state = default_state
            return default_state

    def mark_watchdog_timeout_reset(self) -> None:
        """Increment watchdog reset count and persist reason."""
        state = self.load()
        state["last_reset_reason"] = "heartbeat_timeout"
        state["watchdog_reset_count"] = int(state["watchdog_reset_count"]) + 1
        self._save(state, force=True)

    def clear_watchdog_reset_state(self) -> None:
        """Clear watchdog reset diagnostics after stable recovery."""
        self._save(
            {
                "last_reset_reason": "none",
                "watchdog_reset_count": 0,
            },
            force=True,
        )

    def _save(self, state: dict, force: bool = False) -> None:
        """Persist state dictionary; best effort on embedded storage."""
        now = time.ticks_ms()
        if not force and self._cached_state == state:
            return

        if not force and self._last_write_ms != 0:
            elapsed = time.ticks_diff(now, self._last_write_ms)
            if elapsed < self._write_min_interval_ms:
                self._cached_state = state
                return

        wrote = self._save_to_nvs(state)
        if not wrote:
            self._save_to_file(state)

        self._cached_state = state
        self._last_write_ms = now

    def _load_from_nvs(self):
        """Load state from NVS, or ``None`` if unavailable."""
        if self._nvs is None:
            return None

        try:
            reason_code = self._nvs.get_i32("reason")
            count = self._nvs.get_i32("wd_count")
            if count < 0:
                count = 0

            return {
                "last_reset_reason": _CODE_TO_REASON.get(reason_code, "none"),
                "watchdog_reset_count": count,
            }
        except Exception:
            return None

    def _save_to_nvs(self, state: dict) -> bool:
        """Save state to NVS when available."""
        if self._nvs is None:
            return False

        reason_code = _REASON_TO_CODE.get(state.get("last_reset_reason"), 0)
        count = int(state.get("watchdog_reset_count", 0))

        try:
            self._nvs.set_i32("reason", reason_code)
            self._nvs.set_i32("wd_count", count)
            self._nvs.commit()
            return True
        except Exception:
            return False

    def _save_to_file(self, state: dict) -> None:
        """Persist to JSON file fallback storage."""
        try:
            with open(self._path, "w") as handle:
                handle.write(json.dumps(state))
        except Exception:
            # Intentionally non-fatal.
            return