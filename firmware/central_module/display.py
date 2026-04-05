"""2x16 LCD (HD44780) over PCF8574 I2C backpack.

This module provides:
- ``I2cBackpackLcd1602``: low-level LCD driver.
- ``CentralStatusDisplay``: central-module status formatter/writer.
"""

import time


class I2cBackpackLcd1602:
    """Minimal HD44780 16x2 driver for a common PCF8574 backpack.

    Pin mapping used (typical "0x27" backpacks):
    - P0: RS
    - P1: RW
    - P2: EN
    - P3: Backlight
    - P4..P7: D4..D7
    """

    # Commands
    _CMD_CLEAR = 0x01
    _CMD_HOME = 0x02
    _CMD_ENTRY_MODE = 0x04
    _CMD_DISPLAY_CTRL = 0x08
    _CMD_FUNCTION_SET = 0x20
    _CMD_SET_DDRAM = 0x80

    # Flags
    _ENTRY_LEFT = 0x02
    _DISPLAY_ON = 0x04
    _DISPLAY_OFF = 0x00
    _CURSOR_OFF = 0x00
    _BLINK_OFF = 0x00
    _MODE_4BIT = 0x00
    _MODE_2LINE = 0x08
    _MODE_5X8DOTS = 0x00

    # Backpack control bits
    _RS = 0x01
    _RW = 0x02
    _EN = 0x04
    _BL = 0x08

    def __init__(
        self,
        i2c,
        address: int = 0x27,
        cols: int = 16,
        rows: int = 2,
        backlight: bool = True,
    ) -> None:
        self._i2c = i2c
        self._address = address
        self._cols = cols
        self._rows = rows
        self._backlight = self._BL if backlight else 0x00
        self._row_offsets = [0x00, 0x40, 0x14, 0x54]

        self._init_lcd()

    def _write_byte(self, value: int) -> None:
        self._i2c.writeto(self._address, bytes([value]))

    def _pulse_enable(self, data: int) -> None:
        self._write_byte(data | self._EN)
        time.sleep_us(1)
        self._write_byte(data & ~self._EN)
        time.sleep_us(50)

    def _write4bits(self, nibble_with_ctrl: int) -> None:
        self._write_byte(nibble_with_ctrl)
        self._pulse_enable(nibble_with_ctrl)

    def _send(self, value: int, mode: int) -> None:
        high = (value & 0xF0) | mode | self._backlight
        low = ((value << 4) & 0xF0) | mode | self._backlight
        self._write4bits(high)
        self._write4bits(low)

    def _command(self, value: int) -> None:
        self._send(value, 0)

    def _data(self, value: int) -> None:
        self._send(value, self._RS)

    def _init_lcd(self) -> None:
        time.sleep_ms(50)

        # Force 8-bit mode sequence before switching to 4-bit mode.
        self._write4bits(0x30 | self._backlight)
        time.sleep_ms(5)
        self._write4bits(0x30 | self._backlight)
        time.sleep_us(150)
        self._write4bits(0x30 | self._backlight)
        self._write4bits(0x20 | self._backlight)

        self._command(
            self._CMD_FUNCTION_SET
            | self._MODE_4BIT
            | self._MODE_2LINE
            | self._MODE_5X8DOTS
        )
        self._command(self._CMD_DISPLAY_CTRL | self._DISPLAY_ON | self._CURSOR_OFF | self._BLINK_OFF)
        self.clear()
        self._command(self._CMD_ENTRY_MODE | self._ENTRY_LEFT)
        self.home()

    def clear(self) -> None:
        """Clear display and reset cursor."""
        self._command(self._CMD_CLEAR)
        time.sleep_ms(2)

    def home(self) -> None:
        """Move cursor to home position."""
        self._command(self._CMD_HOME)
        time.sleep_ms(2)

    def set_display(self, on: bool) -> None:
        """Enable or disable display output."""
        display_flag = self._DISPLAY_ON if on else self._DISPLAY_OFF
        self._command(self._CMD_DISPLAY_CTRL | display_flag | self._CURSOR_OFF | self._BLINK_OFF)

    def set_cursor(self, col: int, row: int) -> None:
        """Set cursor to ``(col, row)``."""
        row = 0 if row < 0 else row
        if row >= self._rows:
            row = self._rows - 1

        col = 0 if col < 0 else col
        if col >= self._cols:
            col = self._cols - 1

        self._command(self._CMD_SET_DDRAM | (col + self._row_offsets[row]))

    def write(self, text: str) -> None:
        """Write text at current cursor position."""
        for char in text:
            self._data(ord(char))

    def write_line(self, row: int, text: str) -> None:
        """Write one full padded/truncated line."""
        self.set_cursor(0, row)
        padded = (text or "")[: self._cols].ljust(self._cols)
        self.write(padded)

    def write_lines(self, line1: str, line2: str) -> None:
        """Write both lines for 2x16 display."""
        self.write_line(0, line1)
        self.write_line(1, line2)


class CentralStatusDisplay:
    """High-level formatter for central-module front/rear status."""

    def __init__(self, lcd: I2cBackpackLcd1602) -> None:
        self._lcd = lcd
        self._last_lines = (None, None)

    @staticmethod
    def _mode_token(mode: str) -> str:
        if mode == "neutral":
            return "N"
        if mode == "limited_slip":
            return "L"
        if mode == "locked":
            return "K"
        return "?"

    @staticmethod
    def _online_token(online: bool) -> str:
        return "ON" if online else "OF"

    @staticmethod
    def _fault_token(fault_code: str) -> str:
        if fault_code == "travel_timeout":
            return "TRV"
        if fault_code == "sensor_invalid_combo":
            return "SNS"
        if fault_code == "heartbeat_timeout":
            return "HBT"
        if fault_code == "degraded_mode":
            return "DGD"
        return "---"

    @staticmethod
    def _degraded_lines(front_degraded: bool, rear_degraded: bool):
        """Return full-screen degraded warning text when needed."""
        if not front_degraded and not rear_degraded:
            return None

        if front_degraded and rear_degraded:
            return ("!!! DEGRADED !!!", "F+R LOCKOUT   ")

        if front_degraded:
            return ("!!! DEGRADED !!!", "FRONT LOCKOUT ")

        return ("!!! DEGRADED !!!", "REAR LOCKOUT  ")

    def _fault_lines(self, front_fault: str, rear_fault: str):
        """Return compact fault lines when either diff reports a fault."""
        if not front_fault and not rear_fault:
            return None

        line1 = "F FLT:{}".format(self._fault_token(front_fault) if front_fault else "---")
        line2 = "R FLT:{}".format(self._fault_token(rear_fault) if rear_fault else "---")
        return (line1, line2)

    @staticmethod
    def _offline_lines(front_online: bool, rear_online: bool, blocked_nodes: str = None):
        """Return full-screen offline warning text when needed."""
        if front_online and rear_online:
            return None

        if blocked_nodes:
            if blocked_nodes == "F+R":
                return ("!!! OFFLINE !!!", "CMD BLOCKED F+R")
            if blocked_nodes == "F":
                return ("!!! OFFLINE !!!", "CMD BLOCKED F  ")
            if blocked_nodes == "R":
                return ("!!! OFFLINE !!!", "CMD BLOCKED R  ")

        if not front_online and not rear_online:
            return ("!!! OFFLINE !!!", "FRONT+REAR DIFF")

        if not front_online:
            return ("!!! OFFLINE !!!", "FRONT DIFF MOD")

        return ("!!! OFFLINE !!!", "REAR DIFF MOD ")

    def update(
        self,
        front_mode: str,
        rear_mode: str,
        front_online: bool,
        rear_online: bool,
        blocked_nodes: str = None,
        front_degraded: bool = False,
        rear_degraded: bool = False,
        front_fault: str = None,
        rear_fault: str = None,
    ) -> None:
        """Render front/rear mode + online flags to the LCD."""
        offline_lines = self._offline_lines(
            front_online,
            rear_online,
            blocked_nodes=blocked_nodes,
        )
        if offline_lines is not None:
            lines = offline_lines
            if lines == self._last_lines:
                return

            self._lcd.write_lines(lines[0], lines[1])
            self._last_lines = lines
            return

        degraded_lines = self._degraded_lines(front_degraded, rear_degraded)
        if degraded_lines is not None:
            lines = degraded_lines
            if lines == self._last_lines:
                return

            self._lcd.write_lines(lines[0], lines[1])
            self._last_lines = lines
            return

        fault_lines = self._fault_lines(front_fault, rear_fault)
        if fault_lines is not None:
            lines = fault_lines
            if lines == self._last_lines:
                return

            self._lcd.write_lines(lines[0], lines[1])
            self._last_lines = lines
            return

        line1 = "F:{} {}".format(self._mode_token(front_mode), self._online_token(front_online))
        line2 = "R:{} {}".format(self._mode_token(rear_mode), self._online_token(rear_online))

        lines = (line1, line2)
        if lines == self._last_lines:
            return

        self._lcd.write_lines(line1, line2)
        self._last_lines = lines