"""Simple framed UART protocol for mode commands.

Protocol frame format:
    [SOF][DST][SRC][CMD][LEN][PAYLOAD...][CRC]

CRC is XOR of all bytes from DST through payload.
"""

from hardware.modes import DifferentialMode

from common.constants import (
    CMD_SET_MODE,
    FRAME_SOF,
    MAX_PAYLOAD_SIZE,
)


_MODE_TO_BYTE = {
    DifferentialMode.NEUTRAL: 0,
    DifferentialMode.LIMITED_SLIP: 1,
    DifferentialMode.LOCKED: 2,
}

_BYTE_TO_MODE = {
    0: DifferentialMode.NEUTRAL,
    1: DifferentialMode.LIMITED_SLIP,
    2: DifferentialMode.LOCKED,
}


def mode_to_byte(mode: str):
    """Return encoded mode byte, or ``None`` when invalid."""
    return _MODE_TO_BYTE.get(mode)


def byte_to_mode(value: int):
    """Return decoded mode string, or ``None`` when invalid."""
    return _BYTE_TO_MODE.get(value)


def _crc_xor(data: bytes) -> int:
    """Compute XOR checksum for payload bytes."""
    checksum = 0
    for value in data:
        checksum ^= value
    return checksum & 0xFF


def build_frame(dst: int, src: int, cmd: int, payload: bytes = b"") -> bytes:
    """Build a protocol frame."""
    if len(payload) > MAX_PAYLOAD_SIZE:
        raise ValueError("payload too large")

    body = bytes((dst & 0xFF, src & 0xFF, cmd & 0xFF, len(payload) & 0xFF)) + payload
    crc = _crc_xor(body)
    return bytes((FRAME_SOF,)) + body + bytes((crc,))


def parse_frame(frame: bytes):
    """Parse a complete frame.

    Returns:
        Dictionary with keys ``dst``, ``src``, ``cmd``, ``payload`` when valid.
        ``None`` when invalid.
    """
    if len(frame) < 6:
        return None
    if frame[0] != FRAME_SOF:
        return None

    dst = frame[1]
    src = frame[2]
    cmd = frame[3]
    payload_len = frame[4]

    expected_len = 6 + payload_len
    if len(frame) != expected_len:
        return None

    payload = frame[5:5 + payload_len]
    received_crc = frame[-1]
    body = frame[1:-1]
    computed_crc = _crc_xor(body)
    if received_crc != computed_crc:
        return None

    return {
        "dst": dst,
        "src": src,
        "cmd": cmd,
        "payload": payload,
    }


class SerialProtocol:
    """UART transport wrapper for framed command exchange."""

    def __init__(self, uart, node_id: int) -> None:
        self._uart = uart
        self._node_id = node_id
        self._buffer = bytearray()

    def send_frame(self, dst: int, cmd: int, payload: bytes = b"") -> None:
        """Send a generic protocol frame."""
        frame = build_frame(dst=dst, src=self._node_id, cmd=cmd, payload=payload)
        self._uart.write(frame)

    def send_set_mode(self, dst: int, mode: str) -> bool:
        """Send a set-mode command.

        Returns ``True`` when the mode encoded and was sent.
        """
        mode_byte = mode_to_byte(mode)
        if mode_byte is None:
            return False

        self.send_frame(dst=dst, cmd=CMD_SET_MODE, payload=bytes((mode_byte,)))
        return True

    def poll(self):
        """Read UART and return list of parsed messages."""
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

            if parsed["dst"] not in (self._node_id, 0xFF):
                continue

            messages.append(parsed)

        return messages
