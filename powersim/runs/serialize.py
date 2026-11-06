"""Conversion of domain objects (system, modules, markets) into JSON-friendly dicts."""

import math
from numbers import Number

# Attributes holding time series or large data: stored in the Parquet files, not in inputs.json.
_EXCLUDED_ATTRIBUTES = {"datasets", "production", "batteries", "generators"}


def _to_json_value(value):
    """JSON-friendly version of a scalar/sequence attribute, or None if it is not one."""
    if value is None or isinstance(value, bool | str):
        return value
    if isinstance(value, Number):
        number = float(value) if not isinstance(value, int) else value
        return None if isinstance(number, float) and math.isnan(number) else number
    if isinstance(value, list | tuple):
        items = [_to_json_value(item) for item in value]
        return (
            items
            if all(i is not None or v is None for i, v in zip(items, value, strict=True))
            else None
        )
    return None


def object_params(obj) -> dict:
    """Scalar parameters of a domain object, plus its class name.

    Private attributes (``_max_up``) are stored without the leading underscore.
    Attributes that are not scalars or sequences of scalars (DataFrames, objects) are skipped.
    """
    params = {"class": type(obj).__name__}
    for key, value in vars(obj).items():
        if key in _EXCLUDED_ATTRIBUTES:
            continue
        json_value = _to_json_value(value)
        if json_value is not None or value is None:
            params[key.lstrip("_")] = json_value
    return params


def system_inputs(system) -> dict:
    return {
        "system": object_params(system),
        "batteries": [object_params(battery) for battery in system.batteries],
        "generators": [object_params(generator) for generator in system.generators],
    }


def market_inputs(market) -> dict:
    """Market type (domain name), the class used by the optimizer, and its parameters."""
    params = object_params(market)
    market_class = params.pop("class")
    params.pop("parent_name", None)
    params.pop("name", None)
    return {"type": market.parent_name, "class": market_class, "params": params}
