"""Number formatting shared by components and figures (no Dash imports)."""

# Larger units for compact values: (unit, [(factor, unit), ...]) from the largest.
_UNIT_SCALES = {
    "€": [(1e9, "G€"), (1e6, "M€"), (1e3, "k€")],
    "MWh": [(1e6, "TWh"), (1e3, "GWh")],
    "MW": [(1e3, "GW")],
}
_PLAIN_SCALES = [(1e9, "G"), (1e6, "M"), (1e3, "k")]


def format_compact(value, unit: str = "", decimals: int = 1, digits: int = 3) -> tuple[str, str]:
    """Value and unit as short text for large numbers, e.g. (37241389, '€') -> ('37.2', 'M€').

    Values below 10,000 keep ``decimals`` and their unit. Larger ones are scaled to the unit in
    ``_UNIT_SCALES`` (or a k/M/G suffix for other units) and shown with ``digits`` significant
    digits. ``None`` gives '-'.
    """
    if value is None:
        return "-", unit
    if abs(value) < 1e4:
        return f"{value:,.{decimals}f}", unit
    for factor, scaled_unit in _UNIT_SCALES.get(unit, []):
        if abs(value) >= factor:
            return _significant(value / factor, digits), scaled_unit
    for factor, suffix in _PLAIN_SCALES:
        if abs(value) >= factor:
            return _significant(value / factor, digits) + suffix, unit
    return f"{value:,.{decimals}f}", unit


def _significant(value: float, digits: int) -> str:
    integer_digits = len(str(int(abs(value)))) if abs(value) >= 1 else 1
    return f"{value:,.{max(0, digits - integer_digits)}f}"


def compact_text(value, unit: str = "", decimals: int = 0, digits: int = 3) -> str:
    """``format_compact`` as a single string, e.g. '18.4 M€'."""
    text, unit = format_compact(value, unit, decimals, digits)
    return f"{text} {unit}".strip()
