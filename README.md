# g660-ctrl

Firmware and support tooling for a Yamaha Grizzly 660 differential control
system.

The project is structured so one firmware tree can run in multiple roles:

- **Central module** (steering-wheel/button controller)
- **Differential module** (front or rear actuator controller)

At boot, a hardware select pin chooses which role entrypoint is launched.

---

## 1) System overview

The system controls front and rear differential actuators with three target
modes:

- `neutral`
- `limited_slip`
- `locked`

### Central module responsibilities

- Reads preset buttons (up to 6)
- Sends `set_mode` commands to front/rear diff modules
- Tracks module liveness via heartbeats
- Tracks state/fault telemetry from diff modules
- Optionally renders status on a 16x2 I2C LCD

### Differential module responsibilities

- Resolves current actuator position from 3 position sensors
- Accepts mode commands from central (and optional local selector)
- Drives motor CW/CCW until target mode is reached
- Applies timeout and invalid-sensor safety behavior
- Responds with ACK, mode status, node state, and fault status

---

## 2) Repository layout

```text
firmware/
	boot.py                     # Role-select boot entrypoint
	common/                     # Shared protocol, constants, mode definitions, inputs
	central_module/             # Central controller app + config
	diff_module/                # Differential controller app + motor/transition logic
	tools/comms_profile_validation.py
```

Key files:

- `firmware/boot.py`
- `firmware/common/constants.py`
- `firmware/common/protocol.py`
- `firmware/central_module/main.py`
- `firmware/central_module/config.py`
- `firmware/central_module/pins.py`
- `firmware/diff_module/main.py`
- `firmware/diff_module/pins.py`

---

## 3) Role and node selection

## Boot role select (central vs diff)

`firmware/boot.py` reads the boot-select GPIO and launches one module:

- `central_module.main`
- `diff_module.main`

Behavior is configured in `firmware/common/constants.py`:

- `BOOT_SELECT_PIN`
- `BOOT_SELECT_PULL`
- `BOOT_HIGH_IS_CENTRAL`

## Diff node select (front vs rear)

`diff_module.main` reads a second select pin at startup to pick node ID:

- `NODE_ID_DIFF_FRONT` (`0x11`)
- `NODE_ID_DIFF_REAR` (`0x12`)

Configured in `firmware/diff_module/pins.py`:

- `NODE_SELECT_PIN`
- `NODE_SELECT_PULL`
- `NODE_SELECT_HIGH_IS_FRONT`

This allows one diff firmware image to run as either front or rear via
hardware strapping.

---

## 4) Communications

UART is framed with a small binary protocol in
`firmware/common/protocol.py`:

Frame format:

```text
[SOF][DST][SRC][CMD][LEN][PAYLOAD...][CRC]
```

- `SOF` from `FRAME_SOF` (default `0xA5`)
- `CRC` is XOR of bytes from `DST` through payload

Important command IDs (in `firmware/common/constants.py`):

- `CMD_SET_MODE`
- `CMD_HEARTBEAT`
- `CMD_MODE_STATUS`
- `CMD_ACK`
- `CMD_STATUS_REQUEST`
- `CMD_NODE_STATE`
- `CMD_FAULT_STATUS`

Node IDs:

- Central: `0x01`
- Front diff: `0x11`
- Rear diff: `0x12`
- Broadcast: `0xFF`

---

## 5) Configuration points

## Central configuration

Edit:

- `firmware/central_module/pins.py` for GPIO and bus wiring
- `firmware/central_module/config.py` for behavior/timing

Examples:

- `BUTTON_PRESETS`
- `SET_MODE_ACK_TIMEOUT_MS`
- `SET_MODE_MAX_RETRIES`
- `HEARTBEAT_STAGGER_MS`
- `DISPLAY_ENABLED`

## Diff configuration

Edit:

- `firmware/diff_module/pins.py`

Examples:

- Motor pins (`MOTOR_CW_PIN`, `MOTOR_CCW_PIN`)
- Position sensor pins
- Optional local selector pins
- Watchdog settings
- UART pins/baudrate

---

## 6) Deployment

The project is plain MicroPython source. Typical deployment is copying the
`firmware/` contents to each controller board filesystem.

## Prerequisites

- MicroPython-compatible controller boards (ESP32-class expected)
- USB access to each board
- A file transfer tool (for example, `mpremote`, `rshell`, Thonny, etc.)
- Correct board wiring for your selected pin configuration

## A. Flash MicroPython (one-time per board)

1. Erase/flash board with a matching MicroPython firmware image.
2. Confirm REPL access over serial.

## B. Copy project files to board

Copy the `firmware/` directory contents so the board filesystem includes:

- `boot.py`
- `common/`
- `central_module/`
- `diff_module/`

`boot.py` must live at device root so it runs at startup.

## C. Configure board role by hardware

Set the boot-select strap/pin to choose:

- central role, or
- diff role

No source change is required when `BOOT_SELECT_*` wiring and constants match.

## D. Configure diff front/rear identity

On diff boards, set node-select strap/pin to choose front vs rear.

## E. Reboot and verify

1. Power cycle/reboot all modules.
2. Verify central sees both diff nodes online.
3. Press preset buttons and verify actuator movement + telemetry.
4. If enabled, verify LCD status transitions.

---

## 7) Operational notes

- Central only sends mode commands to online nodes (with startup grace window).
- `set_mode` includes retry/ACK tracking with sequence support.
- Diff modules dedupe repeated `set_mode` commands in a short window.
- Sensor invalid combinations and travel timeout stop motor and report faults.
- Optional heartbeat watchdog can reboot diff nodes on comms loss.
- Reboot loop protection can force degraded mode until stable recovery heartbeats.

---

## 8) Optional timing sanity check tool

`firmware/tools/comms_profile_validation.py` provides a lightweight check for
heartbeat stagger and reply-slot separation using current config defaults.

---

## 9) Development workflow

1. Update configuration files for your harness/wiring.
2. Deploy to bench hardware.
3. Validate sensor transitions in all 3 modes.
4. Validate heartbeat/fault behavior with central connected and disconnected.
5. Freeze known-good pin and timing values before field testing.
