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

# Optional 2x16 I2C LCD backpack
DISPLAY_I2C_ID = 0
DISPLAY_I2C_SCL_PIN = 22
DISPLAY_I2C_SDA_PIN = 21
DISPLAY_I2C_FREQ = 100_000
DISPLAY_I2C_ADDRESS = 0x27
DISPLAY_COLS = 16
DISPLAY_ROWS = 2

# Main loop pacing
MAIN_LOOP_DELAY_MS = 10
