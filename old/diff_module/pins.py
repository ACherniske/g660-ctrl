"""Diff-module pin definitions.

Update these values for the specific board wiring.
"""

from common.constants import NODE_ID_DIFF_FRONT, UART_BAUDRATE as DEFAULT_UART_BAUDRATE

# Motor outputs
MOTOR_CW_PIN = 25
MOTOR_CCW_PIN = 26

# Position sensors (left to right: neutral, limited slip, locked)
POSITION_NEUTRAL_PIN = 32
POSITION_LIMITED_SLIP_PIN = 33
POSITION_LOCKED_PIN = 13

# Local mode selector buttons (left to right: neutral, limited slip, locked)
SELECTOR_NEUTRAL_PIN = 14
SELECTOR_LIMITED_SLIP_PIN = 27
SELECTOR_LOCKED_PIN = 12

# Direction convention:
# True  -> CW moves from left to right (N -> L -> K)
# False -> CW moves from right to left (K -> L -> N)
CW_INCREASES_MODE_INDEX = True

# Control timings
MAIN_LOOP_DELAY_MS = 10
TRAVEL_TIMEOUT_MS = 3000

# UART link to central module
NODE_ID = NODE_ID_DIFF_FRONT
UART_ID = 1
UART_BAUDRATE = DEFAULT_UART_BAUDRATE
UART_TX_PIN = 17
UART_RX_PIN = 16
