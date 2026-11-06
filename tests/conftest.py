"""Synthetic market data and small helpers shared by the tests.

No test may call ESIOS: markets are built by filling ``datasets`` directly with DataFrames
indexed by timestamp with a ``value`` column, exactly like ``get_info`` would.
"""

import copy
from collections.abc import Sequence

import numpy as np
import pandas as pd
import pyomo.environ as pyo
import pytest

from powersim import AFRR, DayAhead

START = "2025-01-01"
TOL = 1e-6


def time_index(periods: int, freq: str = "1h") -> pd.DatetimeIndex:
    return pd.date_range(START, periods=periods, freq=freq, tz="UTC")


def series(index: pd.DatetimeIndex, values: float | Sequence[float]) -> pd.DataFrame:
    if np.isscalar(values):
        values = [values] * len(index)
    return pd.DataFrame({"value": list(values)}, index=index)


def make_day_ahead(prices: Sequence[float], freq: str = "1h") -> DayAhead:
    index = time_index(len(prices), freq)
    market = DayAhead()
    market.datasets = {
        "p_pmd": series(index, prices),
        "e_pmd": series(index, 1e6),
    }
    return market


def make_afrr(
    index: pd.DatetimeIndex,
    *,
    p_up: float = 0.0,
    p_down: float = 0.0,
    p_act_up: float = 0.0,
    p_act_down: float = 0.0,
    band_up: float = 1e6,
    band_down: float = 1e6,
    e_act_up: float = 0.0,
    e_act_down: float = 0.0,
    **kwargs,
) -> AFRR:
    market = AFRR(**kwargs)
    market.datasets = {
        "p_afrr_up": series(index, p_up),
        "p_afrr_down": series(index, p_down),
        "p_afrr_act_up": series(index, p_act_up),
        "p_afrr_act_down": series(index, p_act_down),
        "band_afrr_up": series(index, band_up),
        "band_afrr_down": series(index, band_down),
        "e_afrr_act_up": series(index, e_act_up),
        "e_afrr_act_down": series(index, e_act_down),
    }
    return market


def values(component, *prefix) -> pd.Series:
    """Values of an indexed Pyomo component over ``model.T`` (optionally with a leading index)."""
    model = component.model()
    return pd.Series({t: pyo.value(component[(*prefix, t)]) for t in model.T})


def snapshot(obj):
    """Deep copy of an object's state, to check later that it was not modified."""
    return copy.deepcopy(obj.__dict__)


def assert_same_state(before, after, path="obj"):
    """Recursive equality that understands DataFrames and nested domain objects."""
    if isinstance(before, pd.DataFrame | pd.Series):
        pd.testing.assert_frame_equal(pd.DataFrame(before), pd.DataFrame(after), obj=path)
    elif isinstance(before, dict):
        assert before.keys() == after.keys(), path
        for key in before:
            assert_same_state(before[key], after[key], f"{path}.{key}")
    elif isinstance(before, list | tuple):
        assert len(before) == len(after), path
        for i, (b, a) in enumerate(zip(before, after, strict=True)):
            assert_same_state(b, a, f"{path}[{i}]")
    elif hasattr(before, "__dict__"):
        assert type(before) is type(after), path
        assert_same_state(before.__dict__, after.__dict__, path)
    else:
        assert before == after, path


@pytest.fixture
def two_price_day_ahead() -> DayAhead:
    """8 hours: 4 cheap (10 €/MWh) followed by 4 expensive (100 €/MWh)."""
    return make_day_ahead([10] * 4 + [100] * 4)
