"""Shared protocol and constants for module-to-module communication."""

from common.constants import (
    CMD_HEARTBEAT,
    CMD_SET_MODE,
    NODE_ID_CENTRAL,
    NODE_ID_DIFF_FRONT,
    NODE_ID_DIFF_REAR,
)
from common.protocol import SerialProtocol, byte_to_mode, mode_to_byte

__all__ = [
    "CMD_HEARTBEAT",
    "CMD_SET_MODE",
    "NODE_ID_CENTRAL",
    "NODE_ID_DIFF_FRONT",
    "NODE_ID_DIFF_REAR",
    "SerialProtocol",
    "mode_to_byte",
    "byte_to_mode",
]
