"""Small helpers shared by the modules."""
from typing import Any, Optional


def safe_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    """int(float(value)) for numbers and numeric text; ``default`` for everything else (also for bool)."""
    if value is None or value == "" or isinstance(value, bool):
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError, OverflowError):
        return default


def safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    if value is None or value == "" or isinstance(value, bool):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number == number and number not in (float("inf"), float("-inf")) else default


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def shorten(text: str, limit: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: max(0, limit - 3)] + "..."
