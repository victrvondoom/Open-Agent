"""Exact decimal money helpers. Floats never touch monetary values."""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CENT = Decimal("0.01")


def D(value) -> Decimal:
    """Parse a monetary/percentage value exactly. Rejects floats to avoid binary rounding."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool) or isinstance(value, float):
        raise TypeError(f"refusing non-exact numeric value {value!r}; use str or int")
    if isinstance(value, int):
        return Decimal(value)
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"invalid decimal {value!r}") from exc


def cents(value: Decimal) -> Decimal:
    return D(value).quantize(CENT, rounding=ROUND_HALF_UP)


def fmt(value) -> str:
    """Canonical string form for JSON (always two decimals)."""
    if value is None:
        return None
    return str(cents(value))
