"""Shared code and constants for firmware modules."""

from common.constants import (
    # Boot role select
	BOOT_SELECT_PIN,
	BOOT_SELECT_PULL,
	CENTRAL_ENTRY_MODULE,
	DIFF_ENTRY_MODULE,

    # Node IDs on the control network
    NODE_ID_CENTRAL,
    NODE_ID_DIFF_FRONT,
    NODE_ID_DIFF_REAR,

    # UART link defaults
    UART_BAUDRATE,
    UART_BITS,
    UART_PARITY,
    UART_STOP,

    # Protocol framing
    FRAME_SOF,
    MAX_PAYLOAD_SIZE,

    # Command IDs
    CMD_SET_MODE,
    CMD_HEARTBEAT,

    # Poll loop behavior
    SERIAL_POLL_DELAY_MS,
)
