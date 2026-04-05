"""Central-module pin and UART configuration."""

from common.constants import NODE_ID_CENTRAL, UART_BAUDRATE as DEFAULT_UART_BAUDRATE

# Steering-wheel mode buttons (up to 6 presets)
BUTTON_1_PIN = 14
BUTTON_2_PIN = 27
BUTTON_3_PIN = 12
BUTTON_4_PIN = 26
BUTTON_5_PIN = None  # Placeholder
BUTTON_6_PIN = None  # Placeholder

# Pull-up + active-low switch wiring
INPUT_PULL_UP = True
INPUT_ACTIVE_LOW = True
INPUT_DEBOUNCE_MS = 25

# UART link (shared bus or point-to-point wiring)
NODE_ID = NODE_ID_CENTRAL
UART_ID = 1
UART_BAUDRATE = DEFAULT_UART_BAUDRATE
UART_TX_PIN = 17
UART_RX_PIN = 16

# Main loop pacing
MAIN_LOOP_DELAY_MS = 10
