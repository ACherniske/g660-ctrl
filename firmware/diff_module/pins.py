"""Diff-module hardware and link pin configuration."""

from common.constants import (
	NODE_ID_DIFF_FRONT,
	NODE_ID_DIFF_REAR,
	UART_BAUDRATE as DEFAULT_UART_BAUDRATE,
)

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

# Main loop pacing
MAIN_LOOP_DELAY_MS = 10
