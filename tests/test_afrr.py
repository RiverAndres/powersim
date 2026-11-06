"""aFRR market: band limits shared with energy markets, activation and revenues."""

import pyomo.environ as pyo
import pytest
from conftest import TOL, make_afrr, make_day_ahead, time_index, values

from powersim import Battery, PerfectOptimizer, System

CAPACITY_SELL = 10.0
CAPACITY_BUY = 10.0


def make_system(soc_initial: float = 1.0) -> System:
    system = System(capacity_buy=CAPACITY_BUY, capacity_sell=CAPACITY_SELL, efficiency=1.0)
    # 40 MWh, 10 MW: can sell at full grid capacity during the 4 hours.
    system.add_module(Battery(capacity=40, rte=1.0, c_rate=0.25, soc_initial=soc_initial, name="b"))
    return system


def test_band_up_and_day_ahead_share_export_capacity():
    """Selling 10 MW in day-ahead leaves no room for upward band (capacity_sell = 10 MW).

    Day-ahead pays 100 €/MWh and band only 50 €/MW, so the optimum is to sell everything in
    day-ahead and offer no band. Without the operational limit, the band is offered on top.
    """
    day_ahead = make_day_ahead([100] * 4)
    afrr = make_afrr(time_index(4), p_up=50)
    model = PerfectOptimizer(make_system(), [day_ahead, afrr]).solve().model

    pre_allocated = values(model.Total_power_pre_allocated)
    band_up = values(model.Band_up_Milp_AFRR)

    assert (band_up + pre_allocated).max() <= CAPACITY_SELL + TOL
    assert pyo.value(model.objective) == pytest.approx(100 * 40, abs=1e-4)


def test_band_down_and_day_ahead_share_import_capacity():
    """Buying 10 MW in day-ahead (negative price) leaves no room for downward band."""
    day_ahead = make_day_ahead([-100] * 4)
    afrr = make_afrr(time_index(4), p_down=50)
    model = PerfectOptimizer(make_system(soc_initial=0), [day_ahead, afrr]).solve().model

    pre_allocated = values(model.Total_power_pre_allocated)
    band_down = values(model.Band_down_Milp_AFRR)

    assert (band_down - pre_allocated).max() <= CAPACITY_BUY + TOL


def test_operational_band_limits_are_in_the_model():
    afrr = make_afrr(time_index(4))
    optimizer = PerfectOptimizer(make_system(), [make_day_ahead([0] * 4), afrr])
    model = optimizer._model_setup()

    assert hasattr(model, "band_up_operational_limit_Milp_AFRR")
    assert hasattr(model, "band_down_operational_limit_Milp_AFRR")


def test_band_revenue_is_not_multiplied_by_dt():
    """Band price is €/MW for availability in the interval: no dt factor (quarter-hourly data)."""
    index = time_index(4, "15min")
    afrr = make_afrr(index, p_up=50)
    system = make_system()
    model = PerfectOptimizer(system, [make_day_ahead([0] * 4, "15min"), afrr]).solve().model

    band_up = values(model.Band_up_Milp_AFRR)
    assert band_up.min() == pytest.approx(CAPACITY_SELL, abs=TOL)
    assert pyo.value(model.Revenues_Milp_AFRR) == pytest.approx(50 * CAPACITY_SELL * 4, abs=1e-4)


def _deterministic_down_activation():
    """bin_max with e_act_down / band_down = 0.25 -> probability 1 of downward activation."""
    return make_afrr(
        time_index(4),
        p_down=50,
        band_up=100,
        band_down=100,
        e_act_up=0,
        e_act_down=25,
        act="bin_max",
    )


def test_activation_requirement_parameters_are_loaded():
    optimizer = PerfectOptimizer(
        make_system(), [make_day_ahead([0] * 4), _deterministic_down_activation()]
    )
    model = optimizer._model_setup()

    assert values(model.e_act_down_Milp_AFRR).tolist() == [1, 1, 1, 1]
    assert values(model.e_act_up_Milp_AFRR).tolist() == [0, 0, 0, 0]


@pytest.mark.xfail(strict=True, reason="act_down_requirement uses Band_up instead of Band_down")
def test_down_activation_follows_band_down():
    system = make_system(soc_initial=0)
    model = (
        PerfectOptimizer(system, [make_day_ahead([0] * 4), _deterministic_down_activation()])
        .solve()
        .model
    )

    band_down = values(model.Band_down_Milp_AFRR)
    assert band_down.max() > TOL
    assert values(model.P_down_Milp_AFRR).tolist() == pytest.approx(band_down.tolist(), abs=TOL)


@pytest.mark.xfail(
    strict=True,
    reason="'rand' activation is unfinished: bitwise & on floats, undefined df_temp_up/prob_up",
)
def test_rand_activation_runs():
    afrr = make_afrr(time_index(4), act="rand")
    up, down = afrr._energy_activation_requirements()
    assert len(up) == len(down) == 4
