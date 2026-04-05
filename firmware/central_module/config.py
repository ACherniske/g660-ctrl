"""Central-module mode preset configuration.

Each preset maps one button number to ``(front_mode, rear_mode)``.
Buttons 5 and 6 are reserved placeholders for future presets.
"""

from common.modes import DifferentialMode

# Optional 2x16 I2C LCD status display
DISPLAY_ENABLED = False
DISPLAY_REFRESH_MS = 250

BUTTON_PRESETS = {
    1: (DifferentialMode.NEUTRAL, DifferentialMode.NEUTRAL),
    2: (DifferentialMode.LIMITED_SLIP, DifferentialMode.LIMITED_SLIP),
    3: (DifferentialMode.LOCKED, DifferentialMode.LOCKED),
    4: (DifferentialMode.LIMITED_SLIP, DifferentialMode.NEUTRAL),
    # 5: (...),
    # 6: (...),
}
