"""The optimizer works on converted copies: the user's system and markets are never modified."""

import pandas as pd
import pytest
from conftest import assert_same_state, make_afrr, snapshot, time_index

from powersim import AFRR, Battery, DayAhead, PerfectOptimizer, Photovoltaic, System
from powersim.markets.markets import Market
from powersim.optimizers.milp_optimizer.milp_markets import Milp_AFRR, Milp_DayAhead
from powersim.optimizers.milp_optimizer.milp_modules import (
    Milp_Battery,
    Milp_Photovoltaic,
    Milp_System,
)


def make_system(with_battery: bool = True, with_pv: bool = False) -> System:
    system = System(capacity_buy=5, capacity_sell=5, efficiency=0.95)
    if with_battery:
        system.add_module(Battery(capacity=10, rte=0.9, c_rate=0.5, name="bat"))
    if with_pv:
        pv = Photovoltaic(name="pv")
        pv.production = pd.DataFrame({"power": [0, 2, 4, 6, 6, 4, 2, 0]}, index=time_index(8))
        system.add_module(pv)
    return system


def test_system_and_modules_are_converted(two_price_day_ahead):
    optimizer = PerfectOptimizer(make_system(with_pv=True), [two_price_day_ahead])

    assert isinstance(optimizer.system, Milp_System)
    assert isinstance(optimizer.system.batteries[0], Milp_Battery)
    assert isinstance(optimizer.system.generators[0], Milp_Photovoltaic)


def test_markets_are_converted(two_price_day_ahead):
    afrr = make_afrr(time_index(8))
    optimizer = PerfectOptimizer(make_system(), [two_price_day_ahead, afrr])

    assert isinstance(optimizer.markets[0], Milp_DayAhead)
    assert isinstance(optimizer.markets[1], Milp_AFRR)
    # Converted markets are still instances of the domain class and keep their domain name.
    assert isinstance(optimizer.markets[1], AFRR)
    assert optimizer.markets[1].parent_name == "AFRR"


def test_unsupported_market_raises_type_error(two_price_day_ahead):
    class UnknownMarket(Market):
        def get_info(self, esios_token, start_date, end_date):
            return self

    unknown = UnknownMarket(datasets=dict(two_price_day_ahead.datasets))

    with pytest.raises(TypeError, match="UnknownMarket"):
        PerfectOptimizer(make_system(), [unknown])


@pytest.mark.parametrize(
    ("with_battery", "with_pv"),
    [(True, False), (False, True), (True, True)],
    ids=["battery", "pv_only", "battery_and_pv"],
)
def test_originals_are_not_modified_by_solve(two_price_day_ahead, with_battery, with_pv):
    system = make_system(with_battery=with_battery, with_pv=with_pv)
    afrr = make_afrr(time_index(8), p_up=5)
    markets = [two_price_day_ahead, afrr]

    system_before = snapshot(system)
    markets_before = [snapshot(m) for m in markets]

    PerfectOptimizer(system, markets).solve()

    assert type(system) is System
    assert all(type(m) in (DayAhead, AFRR) for m in markets)
    assert_same_state(system_before, snapshot(system), "system")
    for i, (before, market) in enumerate(zip(markets_before, markets, strict=True)):
        assert_same_state(before, snapshot(market), f"markets[{i}]")
