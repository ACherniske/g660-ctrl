"""Shared firmware constants."""

# Boot role select
BOOT_SELECT_PIN = 4
BOOT_SELECT_PULL = "up"  # "up" or "down"

# Entry module paths (module containing a ``main()`` callable)
CENTRAL_ENTRY_MODULE = "central_module.main"
DIFF_ENTRY_MODULE = "diff_module.main"

# Node IDs on the control network
NODE_ID_CENTRAL = 0x01
NODE_ID_DIFF_FRONT = 0x11
NODE_ID_DIFF_REAR = 0x12
NODE_ID_BROADCAST = 0xFF

# UART link defaults (suitable for short board-to-board links)
UART_BAUDRATE = 115200
UART_BITS = 8
UART_PARITY = None
UART_STOP = 1

# Protocol framing
FRAME_SOF = 0xA5
MAX_PAYLOAD_SIZE = 16

# Command IDs
CMD_SET_MODE = 0x01
CMD_HEARTBEAT = 0x02

# Poll loop behavior
SERIAL_POLL_DELAY_MS = 5