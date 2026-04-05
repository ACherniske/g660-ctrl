"""Simple framed UART protocol for mode commands.

Protocol frame format:
    [SOF][DST][SRC][CMD][LEN][PAYLOAD...][CRC]

CRC is XOR of all bytes from DST through payload.
"""

from hardware.modes import DifferentialMode

from common.constants import (
    CMD_SET_MODE,
    CMD_HEARTBEAT,
    FRAME_SOF,
    MAX_PAYLOAD_SIZE,
    NODE_ID_BROADCAST,
)

_MODE_TO_BYTE = {
    DifferentialMode.NEUTRAL: b"N",  # 0x4E
    DifferentialMode.LIMITED_SLIP: b"L",  # 0x4C
    DifferentialMode.LOCKED: b"K",  # 0x4B
}

_BYTE_TO_MODE = {
    b"N": DifferentialMode.NEUTRAL,
    b"L": DifferentialMode.LIMITED_SLIP,
    b"K": DifferentialMode.LOCKED,
}


def mode_to_byte(mode: str):
    """Return one-byte ASCII mode code: ``N``, ``L``, or ``K``."""
    return _MODE_TO_BYTE.get(mode)


def byte_to_mode(value):
    """Return mode string from one-byte ASCII payload."""
    if isinstance(value, int):
        value = bytes((value,))
    return _BYTE_TO_MODE.get(value)


def _crc_xor(data: bytes) -> int:
    """Compute XOR checksum for frame body."""
    checksum = 0
    for item in data:
        checksum ^= item
    return checksum & 0xFF


def build_frame(dst: int, src: int, cmd: int, payload: bytes = b"") -> bytes:
    """Build and return one protocol frame."""
    if len(payload) > MAX_PAYLOAD_SIZE:
        raise ValueError("payload too large")

    body = bytes((dst & 0xFF, src & 0xFF, cmd & 0xFF, len(payload) & 0xFF)) + payload
    return bytes((FRAME_SOF,)) + body + bytes((_crc_xor(body),))


def parse_frame(frame: bytes):
    """Parse one complete frame and return a dictionary or ``None``."""
    if len(frame) < 6:
        return None
    if frame[0] != FRAME_SOF:
        return None

    payload_len = frame[4]
    expected_len = 6 + payload_len
    if len(frame) != expected_len:
        return None

    body = frame[1:-1]
    if frame[-1] != _crc_xor(body):
        return None

    payload_start = 5
    payload_end = payload_start + payload_len
    return {
        "dst": frame[1],
        "src": frame[2],
        "cmd": frame[3],
        "payload": frame[payload_start:payload_end],
    }


class SerialProtocol:
    """UART framing helper for command transport.

    Args:
        uart: UART object for transport.
        node_id: This node's ID for addressing.
    """

    def __init__(self, uart, node_id: int) -> None:
        self._uart = uart
        self._node_id = node_id
        self._buffer = bytearray()

    def send_frame(self, dst: int, cmd: int, payload: bytes = b"") -> None:
        """Send one generic frame."""
        frame = build_frame(
            dst=dst,
            src=self._node_id,
            cmd=cmd,
            payload=payload,
        )
        self._uart.write(frame)

    def send_set_mode(self, dst: int, mode: str) -> bool:
        """Send a mode command frame. Returns True if sent."""
        mode_byte = mode_to_byte(mode)
        if mode_byte is None:
            return False

        self.send_frame(dst=dst, cmd=CMD_SET_MODE, payload=mode_byte)
        return True

    def send_heartbeat(self, dst: int = NODE_ID_BROADCAST) -> None:
        """Send a heartbeat frame to the specified destination (default broadcast)."""
        self.send_frame(dst=dst, cmd=CMD_HEARTBEAT)

    def poll(self):
        """Read UART and return list of parsed messages for this node."""
        incoming = self._uart.read()
        if incoming:
            self._buffer.extend(incoming)

        messages = []
        while True:
            if len(self._buffer) < 6:
                break

            try:
                sof_index = self._buffer.index(FRAME_SOF)
            except ValueError:
                self._buffer.clear()
                break

            if sof_index > 0:
                del self._buffer[:sof_index]

            if len(self._buffer) < 6:
                break

            payload_len = self._buffer[4]
            frame_len = 6 + payload_len
            if len(self._buffer) < frame_len:
                break

            frame = bytes(self._buffer[:frame_len])
            del self._buffer[:frame_len]

            parsed = parse_frame(frame)
            if parsed is None:
                continue

            if parsed["dst"] not in (self._node_id, NODE_ID_BROADCAST):
                continue

            messages.append(parsed)

        return messages
