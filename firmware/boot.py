"""Boot role selector.

Reads a hardware boot-select pin and launches either the central-module
application or the differential-module application.
"""

from machine import Pin

from common.constants import (
	BOOT_HIGH_IS_CENTRAL,
	BOOT_SELECT_PIN,
	BOOT_SELECT_PULL,
	CENTRAL_ENTRY_MODULE,
	DIFF_ENTRY_MODULE,
)


def _resolve_pull_mode() -> int:
    """Return machine.Pin pull mode from string config."""
    if BOOT_SELECT_PULL == "down":
        return Pin.PULL_DOWN
    return Pin.PULL_UP


def _import_module(module_path: str):
    """Import a dotted module path and return module object."""
    module = __import__(module_path)
    for part in module_path.split(".")[1:]:
        module = getattr(module, part)
    return module


def _launch(module_path: str) -> None:
    """Import module and execute its ``main()`` function."""
    module = _import_module(module_path)
    entry = getattr(module, "main", None)
    if entry is None:
        raise RuntimeError("Missing main() in {}".format(module_path))
    entry()


def _select_role_module(pin_level_high: bool) -> str:
    """Resolve which role module to launch from pin level."""
    is_central = pin_level_high if BOOT_HIGH_IS_CENTRAL else not pin_level_high
    return CENTRAL_ENTRY_MODULE if is_central else DIFF_ENTRY_MODULE


def main() -> None:
    """Boot entry point."""
    boot_select = Pin(BOOT_SELECT_PIN, Pin.IN, _resolve_pull_mode())
    selected_module = _select_role_module(bool(boot_select.value()))
    _launch(selected_module)


main()
