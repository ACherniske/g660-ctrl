"""Central-module pin and link configuration."""

from common.constants import (
    NODE_ID_CENTRAL,
    NODE_ID_DIFF_FRONT,
    UART_BAUDRATE as DEFAULT_UART_BAUDRATE,
)

# Local selector buttons (left to right: neutral, limited slip, locked)
SELECTOR_NEUTRAL_PIN = 14
SELECTOR_LIMITED_SLIP_PIN = 27
SELECTOR_LOCKED_PIN = 12

# UART link to differential module
NODE_ID = NODE_ID_CENTRAL
TARGET_DIFF_NODE_ID = NODE_ID_DIFF_FRONT
UART_ID = 1
UART_BAUDRATE = DEFAULT_UART_BAUDRATE
UART_TX_PIN = 17
UART_RX_PIN = 16

# Control loop delay
MAIN_LOOP_DELAY_MS = 10
