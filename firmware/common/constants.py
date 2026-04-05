"""Shared firmware constants."""

# Boot role select
BOOT_SELECT_PIN = 4
BOOT_SELECT_PULL = "up"  # "up" or "down"

# Entry module paths (module containing a ``main()`` callable)
CENTRAL_ENTRY_MODULE = "central_module.main"
DIFF_ENTRY_MODULE = "diff_module.main"
