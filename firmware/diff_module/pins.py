"""Diff-module hardware and link pin configuration."""

from common.constants import (
    HEARTBEAT_TIMEOUT_MS as DEFAULT_HEARTBEAT_TIMEOUT_MS,
    NODE_ID_DIFF_FRONT,
    NODE_ID_DIFF_REAR,
    UART_BAUDRATE as DEFAULT_UART_BAUDRATE,
)

# Deployment mode
# True: central-managed (UART commands + heartbeat behavior enabled)
# False: standalone (local selector only; UART/heartbeat behavior disabled)
CENTRAL_CONTROL_ENABLED = True

# Motor outputs
MOTOR_CW_PIN = 25
MOTOR_CCW_PIN = 26

# Position sensors (left to right: neutral, limited slip, locked)
POSITION_NEUTRAL_PIN = 32
POSITION_LIMITED_SLIP_PIN = 33
POSITION_LOCKED_PIN = 13

# Optional local selector buttons (left to right: neutral, limited slip, locked)
LOCAL_SELECTOR_ENABLED = True
LOCAL_SELECTOR_NEUTRAL_PIN = 14
LOCAL_SELECTOR_LIMITED_SLIP_PIN = 27
LOCAL_SELECTOR_LOCKED_PIN = 12

# Pull-up + active-low switch wiring
INPUT_PULL_UP = True
INPUT_ACTIVE_LOW = True
INPUT_DEBOUNCE_MS = 25

# Motion convention and timeout
CW_INCREASES_MODE_INDEX = True
TRAVEL_TIMEOUT_MS = 5000

# UART link for remote mode commands
# Solder jumper node-ID select (read at startup)
NODE_SELECT_PIN = 15
NODE_SELECT_PULL = "up"  # "up" or "down"
# True => high selects front ID, low selects rear ID.
NODE_SELECT_HIGH_IS_FRONT = True

NODE_ID_FRONT = NODE_ID_DIFF_FRONT
NODE_ID_REAR = NODE_ID_DIFF_REAR

UART_ID = 1
UART_BAUDRATE = DEFAULT_UART_BAUDRATE
UART_TX_PIN = 17
UART_RX_PIN = 16

# Shared-bus contention mitigation for diff-to-central replies.
BUS_CONTENTION_MITIGATION_ENABLED = True
# Delay = base + (node_low_nibble * step). For 0x11/0x12 this spaces replies.
CENTRAL_REPLY_BASE_DELAY_MS = 2
CENTRAL_REPLY_NODE_STEP_MS = 3

# Duplicate command protection (for retry/ACK ambiguity on shared bus).
SET_MODE_DEDUPE_WINDOW_MS = 1500

# Optional comms-loss reset watchdog.
# When enabled, this module will reset if central heartbeat is not seen
# for longer than HEARTBEAT_WATCHDOG_TIMEOUT_MS.
HEARTBEAT_WATCHDOG_ENABLED = True
HEARTBEAT_WATCHDOG_TIMEOUT_MS = DEFAULT_HEARTBEAT_TIMEOUT_MS
# If True, watchdog starts only after first central heartbeat is received.
HEARTBEAT_WATCHDOG_REQUIRE_FIRST_HEARTBEAT = True

# Watchdog reboot-loop protection.
BOOT_STATE_FILE = "diff_boot_state.json"
BOOT_STATE_USE_NVS = True
BOOT_STATE_NVS_NAMESPACE = "g660diff"
BOOT_STATE_WRITE_MIN_INTERVAL_MS = 1000
MAX_WATCHDOG_REBOOTS = 3
WATCHDOG_RECOVERY_HEARTBEAT_COUNT = 20

# Main loop pacing
MAIN_LOOP_DELAY_MS = 10
