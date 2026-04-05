"""Simple framed UART protocol for mode commands.

Protocol frame format:
    [SOF][DST][SRC][CMD][LEN][PAYLOAD...][CRC]

CRC is XOR of all bytes from DST through payload.
"""

from common.modes import DifferentialMode

from common.constants import (
    CMD_ACK,
    CMD_FAULT_STATUS,
    CMD_SET_MODE,
    CMD_HEARTBEAT,
    CMD_MODE_STATUS,
    CMD_NODE_STATE,
    CMD_STATUS_REQUEST,
    FRAME_SOF,
    MAX_PAYLOAD_SIZE,
    NODE_ID_BROADCAST,
)

_MODE_TO_BYTE = {
    DifferentialMode.NEUTRAL: b"N",  # 0x4E
    DifferentialMode.LIMITED_SLIP: b"L",  # 0x4C
    DifferentialMode.LOCKED: b"K",  # 0x4B
    DifferentialMode.UNKNOWN: b"U",  # 0x55
    DifferentialMode.INVALID: b"I",  # 0x49
}

_BYTE_TO_MODE = {
    b"N": DifferentialMode.NEUTRAL,
    b"L": DifferentialMode.LIMITED_SLIP,
    b"K": DifferentialMode.LOCKED,
    b"U": DifferentialMode.UNKNOWN,
    b"I": DifferentialMode.INVALID,
}

FAULT_NONE = "fault_cleared"
FAULT_TRAVEL_TIMEOUT = "travel_timeout"
FAULT_SENSOR_INVALID_COMBO = "sensor_invalid_combo"
FAULT_HEARTBEAT_TIMEOUT = "heartbeat_timeout"
FAULT_DEGRADED_MODE = "degraded_mode"

_FAULT_TO_BYTE = {
    FAULT_NONE: 0x00,
    FAULT_TRAVEL_TIMEOUT: 0x01,
    FAULT_SENSOR_INVALID_COMBO: 0x02,
    FAULT_HEARTBEAT_TIMEOUT: 0x03,
    FAULT_DEGRADED_MODE: 0x04,
}

_BYTE_TO_FAULT = {value: key for key, value in _FAULT_TO_BYTE.items()}

NODE_STATE_FLAG_DEGRADED = 0x01


def mode_to_byte(mode: str):
    """Return one-byte ASCII mode code: ``N``, ``L``, or ``K``."""
    return _MODE_TO_BYTE.get(mode)


def byte_to_mode(value):
    """Return mode string from one-byte ASCII payload."""
    if isinstance(value, int):
        value = bytes((value,))
    return _BYTE_TO_MODE.get(value)


def fault_to_byte(fault_code: str):
    """Return one-byte fault code payload."""
    code = _FAULT_TO_BYTE.get(fault_code)
    if code is None:
        return None
    return bytes((code,))


def byte_to_fault(value):
    """Return fault-code string from one-byte fault payload."""
    if isinstance(value, bytes):
        if len(value) != 1:
            return None
        value = value[0]
    return _BYTE_TO_FAULT.get(value)


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

    def send_set_mode(self, dst: int, mode: str, seq: int = None) -> bool:
        """Send a mode command frame. Returns True if sent.

        Payload is:
        - ``[mode]`` when ``seq`` is None
        - ``[mode, seq]`` when ``seq`` is provided
        """
        mode_byte = mode_to_byte(mode)
        if mode_byte is None:
            return False

        if seq is None:
            payload = mode_byte
        else:
            payload = mode_byte + bytes((seq & 0xFF,))

        self.send_frame(dst=dst, cmd=CMD_SET_MODE, payload=payload)
        return True

    def send_mode_status(self, dst: int, mode: str) -> bool:
        """Send current mode status as one-byte ASCII payload."""
        mode_byte = mode_to_byte(mode)
        if mode_byte is None:
            return False

        self.send_frame(dst=dst, cmd=CMD_MODE_STATUS, payload=mode_byte)
        return True

    def send_heartbeat(self, dst: int = NODE_ID_BROADCAST) -> None:
        """Send a heartbeat frame to the specified destination (default broadcast)."""
        self.send_frame(dst=dst, cmd=CMD_HEARTBEAT)

    def send_ack(self, dst: int, acked_cmd: int, seq: int = None) -> None:
        """Send command acknowledgment payload.

        Payload is:
        - ``[acked_cmd]`` when ``seq`` is None
        - ``[acked_cmd, seq]`` when ``seq`` is provided
        """
        payload = bytes((acked_cmd & 0xFF,))
        if seq is not None:
            payload += bytes((seq & 0xFF,))

        self.send_frame(dst=dst, cmd=CMD_ACK, payload=payload)

    def send_status_request(self, dst: int) -> None:
        """Request one node-state report from destination node."""
        self.send_frame(dst=dst, cmd=CMD_STATUS_REQUEST)

    def send_node_state(self, dst: int, mode: str, degraded: bool) -> bool:
        """Send node-state payload ``[mode_byte, flags]``."""
        mode_byte = mode_to_byte(mode)
        if mode_byte is None:
            return False

        flags = NODE_STATE_FLAG_DEGRADED if degraded else 0
        payload = mode_byte + bytes((flags & 0xFF,))
        self.send_frame(dst=dst, cmd=CMD_NODE_STATE, payload=payload)
        return True

    def send_fault_status(self, dst: int, fault_code: str) -> bool:
        """Send one-byte fault status payload."""
        code_byte = fault_to_byte(fault_code)
        if code_byte is None:
            return False

        self.send_frame(dst=dst, cmd=CMD_FAULT_STATUS, payload=code_byte)
        return True

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
