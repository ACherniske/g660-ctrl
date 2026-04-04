"""Differential mode definitions used across hardware modules."""


class DifferentialMode:
    """Differential mode constants and helpers for MicroPython."""

    NEUTRAL = "neutral"
    LIMITED_SLIP = "limited_slip"
    LOCKED = "locked"

    UNKNOWN = "unknown"
    INVALID = "invalid"

    _DRIVE_MODES = (NEUTRAL, LIMITED_SLIP, LOCKED)
    _POSITION_INDEX = {
        NEUTRAL: 0,
        LIMITED_SLIP: 1,
        LOCKED: 2,
    }

    @classmethod
    def drive_modes(cls):
        """Return the three valid commanded drive modes."""
        return cls._DRIVE_MODES

    @classmethod
    def is_drive_mode(cls, mode) -> bool:
        """Return ``True`` when mode is one of N/L/K."""
        return mode in cls.drive_modes()

    @classmethod
    def position_index(cls, mode):
        """Return ordinal position index for N/L/K, or ``None``."""
        return cls._POSITION_INDEX.get(mode)
