"""Small helpers on a run's wide time series and inputs, shared by indicators and the dashboard.

Pure pandas, no plotting. The period length is always taken from the time index (runs may mix
15-minute and hourly periods).
"""

import pandas as pd


def period_hours(index: pd.DatetimeIndex) -> pd.Series:
    """Length of each period in hours (the last one repeats the previous)."""
    if len(index) < 2:
        return pd.Series(1.0, index=index)
    hours = pd.Series(index, index=index).diff().shift(-1).dt.total_seconds() / 3600
    return hours.fillna(hours.iloc[-2])


def energy(data: pd.DataFrame, variable: str) -> float:
    """Absolute energy (MWh) of a power variable over the run (power × period length)."""
    if variable not in data:
        return 0.0
    return abs(float((data[variable] * period_hours(data.index)).sum()))


def plant_ratings(inputs: dict) -> dict:
    """Rated PV peak power (MW), battery power (MW) and capacity (MWh); None when unknown.

    Several batteries or generators are summed.
    """
    batteries = inputs.get("batteries", [])
    return {
        "pv_peak": sum_known(g.get("peak_power") for g in inputs.get("generators", [])),
        "battery_power": sum_known(battery_power(b) for b in batteries),
        "battery_capacity": sum_known(b.get("capacity") for b in batteries),
    }


def battery_ratings(inputs: dict) -> dict:
    """Battery figures used by the indicators (None when there is no battery).

    ``power`` (MW) and ``capacity`` (MWh) are summed over batteries; ``rte``, ``soc_min``
    (1 − DoD) and ``soc_max`` are capacity-weighted; ``max_cycles_day`` is the strictest limit.
    """
    batteries = [b for b in inputs.get("batteries", []) if b.get("capacity")]
    ratings = plant_ratings(inputs)
    capacity = ratings["battery_capacity"]

    def weighted(key, default):
        values = [(b.get(key), b["capacity"]) for b in batteries]
        values = [(v if v is not None else default, c) for v, c in values]
        return sum(v * c for v, c in values) / capacity if capacity and values else None

    limits = [b["max_cycles_day"] for b in batteries if b.get("max_cycles_day")]
    return {
        "power": ratings["battery_power"],
        "capacity": capacity,
        "rte": weighted("rte", None) if all(b.get("rte") for b in batteries) else None,
        "soc_min": 1 - weighted("dod", 1.0) if batteries else None,
        "soc_max": weighted("soc_max", 1.0),
        "max_cycles_day": min(limits) if limits else None,
    }


def battery_power(battery: dict):
    """Rated power of one battery: ``max_power_output``, else capacity × c-rate."""
    if battery.get("max_power_output") is not None:
        return battery["max_power_output"]
    if battery.get("capacity") is not None and battery.get("c_rate") is not None:
        return battery["capacity"] * battery["c_rate"]
    return None


def sum_known(values):
    """Sum of the values that are not None (None if all are)."""
    known = [v for v in values if v is not None]
    return sum(known) if known else None
