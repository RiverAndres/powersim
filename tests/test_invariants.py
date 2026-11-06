"""Properties that must hold for any solution, on a non-trivial synthetic case."""

import math

import numpy as np
import pandas as pd
import pyomo.environ as pyo
import pytest
from conftest import TOL, make_day_ahead, values

from powersim import Battery, PerfectOptimizer, System

CAPACITY = 20.0
SOC_MAX = 0.9
RTE = 0.85
CAPACITY_BUY = 6.0
CAPACITY_SELL = 8.0
EFFICIENCY = 0.95


@pytest.fixture(scope="module", params=[("1h", 48), ("15min", 96)], ids=["hourly", "15min"])
def solved(request):
    freq, periods = request.param
    rng = np.random.default_rng(42)
    prices = rng.normal(60, 40, periods).round(2)  # includes some negative prices

    system = System(capacity_buy=CAPACITY_BUY, capacity_sell=CAPACITY_SELL, efficiency=EFFICIENCY)
    # 10 MW battery behind a smaller grid connection, so the grid limits bind.
    system.add_module(
        Battery(capacity=CAPACITY, rte=RTE, c_rate=0.5, soc_max=SOC_MAX, soc_initial=0.3, name="b")
    )
    optimizer = PerfectOptimizer(system, [make_day_ahead(prices, freq)]).solve()
    return optimizer, freq


def test_dt_matches_data_frequency(solved):
    optimizer, freq = solved
    expected = pd.Timedelta(freq) / pd.Timedelta("1h")
    assert set(values(optimizer.model.dt)) == {expected}


def test_soc_within_limits(solved):
    soc = values(solved[0].model.SOC, "b")
    assert soc.min() >= -TOL
    assert soc.max() <= SOC_MAX + TOL


def test_grid_limits(solved):
    model = solved[0].model
    assert values(model.P_import).max() <= CAPACITY_BUY + TOL
    assert values(model.P_export).max() <= CAPACITY_SELL + TOL


def test_soc_balance_uses_power_times_dt(solved):
    model = solved[0].model
    soc = values(model.SOC, "b")
    soc_prev = soc.shift(1).fillna(0.3)
    energy_in = (
        math.sqrt(RTE) * values(model.P_charge, "b")
        - values(model.P_discharge, "b") / math.sqrt(RTE)
    ) * values(model.dt)

    np.testing.assert_allclose(soc - soc_prev, energy_in / CAPACITY, atol=TOL)


def test_market_output_matches_system_output(solved):
    model = solved[0].model
    market_output = values(model.Market_output_Milp_DayAhead)
    system_output = values(model.P_export) * EFFICIENCY - values(model.P_import)

    np.testing.assert_allclose(market_output, system_output, atol=TOL)


def test_revenues_are_power_times_price_times_dt(solved):
    model = solved[0].model
    net = values(model.P_sell_Milp_DayAhead) - values(model.P_buy_Milp_DayAhead)
    expected = (net * values(model.p_Milp_DayAhead) * values(model.dt)).sum()

    assert pyo.value(model.objective) == pytest.approx(expected, abs=1e-4)


def test_battery_results_energy(solved):
    optimizer, _ = solved
    df = optimizer.results.operation_storage_list[0]

    np.testing.assert_allclose(df["E_discharge"], df["P_discharge"] * df["dt"], atol=TOL)
    np.testing.assert_allclose(df["E_charge"], df["P_charge"] * df["dt"], atol=TOL)
