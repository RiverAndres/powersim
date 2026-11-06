"""Small battery + day-ahead cases whose optimal solution is known by hand."""

import pyomo.environ as pyo
import pytest
from conftest import TOL, make_day_ahead, values

from powersim import Battery, PerfectOptimizer, System


def solve(prices, battery: Battery, freq: str = "1h", efficiency: float = 1.0):
    system = System(capacity_buy=100, capacity_sell=100, efficiency=efficiency)
    system.add_module(battery)
    return PerfectOptimizer(system, [make_day_ahead(prices, freq)]).solve().model


@pytest.mark.parametrize(("freq", "repeat"), [("1h", 1), ("15min", 4)], ids=["hourly", "15min"])
def test_lossless_battery_does_exactly_one_cycle(freq, repeat):
    # 4 h at 10 €/MWh then 4 h at 100 €/MWh; 10 MWh battery, 2.5 MW (4 h to charge).
    prices = [10] * (4 * repeat) + [100] * (4 * repeat)
    model = solve(prices, Battery(capacity=10, rte=1.0, c_rate=0.25, name="b"), freq)

    dt = values(model.dt)
    charged = (values(model.P_charge, "b") * dt).sum()
    discharged = (values(model.P_discharge, "b") * dt).sum()

    assert charged == pytest.approx(10, abs=TOL)
    assert discharged == pytest.approx(10, abs=TOL)
    assert values(model.SOC, "b").iloc[-1] == pytest.approx(0, abs=TOL)
    assert pyo.value(model.objective) == pytest.approx((100 - 10) * 10, abs=TOL)


def test_battery_does_not_operate_when_spread_does_not_cover_losses():
    # rte = 0.81: 1 MWh bought at 90 returns 0.81 MWh sold at 100 = 81 < 90.
    model = solve([90] * 4 + [100] * 4, Battery(capacity=10, rte=0.81, c_rate=0.25, name="b"))

    assert pyo.value(model.objective) == pytest.approx(0, abs=TOL)
    assert values(model.P_discharge, "b").max() == pytest.approx(0, abs=TOL)


def test_battery_with_losses_still_cycles_when_spread_is_large():
    model = solve([10] * 4 + [100] * 4, Battery(capacity=10, rte=0.81, c_rate=0.25, name="b"))
    # Buys 10 MWh (limited by power: 2.5 MW x 4 h, SOC reaches 0.9) and sells 0.81 x 10 MWh.
    assert pyo.value(model.objective) == pytest.approx(100 * 8.1 - 10 * 10, abs=1e-4)


def test_initial_soc_is_sold():
    model = solve([100] * 4, Battery(capacity=10, rte=1.0, c_rate=0.25, soc_initial=1, name="b"))

    assert pyo.value(model.objective) == pytest.approx(100 * 10, abs=TOL)
    assert values(model.SOC, "b").iloc[-1] == pytest.approx(0, abs=TOL)


def test_power_is_limited_by_c_rate():
    model = solve([10, 100], Battery(capacity=10, rte=1.0, c_rate=0.5, name="b"))

    assert values(model.P_charge, "b").max() == pytest.approx(5, abs=TOL)
    assert pyo.value(model.objective) == pytest.approx((100 - 10) * 5, abs=TOL)


@pytest.mark.xfail(strict=True, reason="Battery.dod is not used: no lower SOC bound")
def test_dod_sets_a_lower_soc_bound():
    battery = Battery(capacity=10, rte=1.0, c_rate=1, dod=0.8, soc_initial=0.5, name="b")
    model = solve([100] * 4, battery)

    assert values(model.SOC, "b").min() >= 1 - 0.8 - TOL
