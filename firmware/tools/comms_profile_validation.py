"""Lightweight comms-profile validator for shared UART bus timing.

This does not replace hardware testing, but helps sanity-check configured timing
slots for potential reply collisions.
"""


def validate_profile(
    heartbeat_interval_ms: int,
    heartbeat_stagger_ms: int,
    front_reply_delay_ms: int,
    rear_reply_delay_ms: int,
    min_reply_separation_ms: int = 2,
) -> dict:
    """Return timing checks and basic collision risk indicators."""
    issues = []

    if heartbeat_stagger_ms <= 0:
        issues.append("heartbeat_stagger_ms should be > 0")
    if heartbeat_stagger_ms >= heartbeat_interval_ms:
        issues.append("heartbeat_stagger_ms must be < heartbeat_interval_ms")

    separation = abs(rear_reply_delay_ms - front_reply_delay_ms)
    if separation < min_reply_separation_ms:
        issues.append(
            "front/rear reply delay separation too small: {}ms < {}ms".format(
                separation,
                min_reply_separation_ms,
            )
        )

    return {
        "ok": len(issues) == 0,
        "issues": issues,
        "metrics": {
            "heartbeat_interval_ms": heartbeat_interval_ms,
            "heartbeat_stagger_ms": heartbeat_stagger_ms,
            "reply_delay_separation_ms": separation,
            "min_reply_separation_ms": min_reply_separation_ms,
        },
    }


def validate_workspace_defaults() -> dict:
    """Validate default profile values from current central/diff configs."""
    from common.constants import HEARTBEAT_INTERVAL_MS
    from central_module import config as central_config
    from diff_module import pins as diff_pins

    front_delay = diff_pins.CENTRAL_REPLY_BASE_DELAY_MS + ((0x11 & 0x0F) * diff_pins.CENTRAL_REPLY_NODE_STEP_MS)
    rear_delay = diff_pins.CENTRAL_REPLY_BASE_DELAY_MS + ((0x12 & 0x0F) * diff_pins.CENTRAL_REPLY_NODE_STEP_MS)

    return validate_profile(
        heartbeat_interval_ms=HEARTBEAT_INTERVAL_MS,
        heartbeat_stagger_ms=central_config.HEARTBEAT_STAGGER_MS,
        front_reply_delay_ms=front_delay,
        rear_reply_delay_ms=rear_delay,
        min_reply_separation_ms=2,
    )


if __name__ == "__main__":
    result = validate_workspace_defaults()
    print(result)
