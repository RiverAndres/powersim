"""Known bugs outside aFRR. Each test is xfail(strict=True): remove the marker when fixing it."""

import pytest
from conftest import make_day_ahead
from pyomo.core.expr.visitor import identify_variables
from pyomo.repn import generate_standard_repn

from powersim import MFRR, Battery, PerfectOptimizer, Photovoltaic, System


def build_model(battery: Battery, periods: int = 8):
    system = System(capacity_buy=10, capacity_sell=10, efficiency=1.0)
    system.add_module(battery)
    return PerfectOptimizer(system, [make_day_ahead([50] * periods)])._model_setup()


@pytest.mark.xfail(strict=True, reason="Photovoltaic.__init__ rejects a name given with parameters")
def test_photovoltaic_accepts_name_and_parameters():
    pv = Photovoltaic(peak_power=1, latitude=40, longitude=-3, name="pv")
    assert pv.name == "pv"


@pytest.mark.xfail(strict=True, reason="rsoc[:1] makes rsoc_min == rsoc_max")
def test_rsoc_max_uses_upper_bound():
    battery = Battery(capacity=10, rte=1, c_rate=0.5, rsoc=(0.2, 0.6, "monthly"), name="b")
    model = build_model(battery)

    constraint = next(iter(model.rsoc_max_b.values()))
    repn = generate_standard_repn(constraint.body)
    rest_coefs = [
        abs(coef / model.dt[var.index()[1]])
        for var, coef in zip(repn.linear_vars, repn.linear_coefs, strict=True)
        if var.parent_component() is model.rest
    ]
    assert rest_coefs
    assert rest_coefs == pytest.approx([0.6] * len(rest_coefs))


@pytest.mark.xfail(
    strict=True,
    reason="min_resting_period: model.T.atleast() does not exist in Pyomo (model build fails) "
    "and the rule returns inside the loop (only 1 period)",
)
def test_min_resting_period_spans_several_periods():
    battery = Battery(capacity=10, rte=1, c_rate=0.5, resting_period=3, name="b")
    model = build_model(battery)

    first = model.T.first()
    variables = identify_variables(model.min_resting_period_b[first].body)
    rest_vars = [v for v in variables if v.parent_component() is model.rest]
    assert len(rest_vars) == 3


@pytest.mark.xfail(
    strict=True,
    reason="PerfectOptimizer forwards **kwargs to Optimizer.__init__, which does not accept them",
)
def test_unknown_optimizer_argument_gives_clear_error():
    system = System(capacity_buy=10, capacity_sell=10, efficiency=1.0)
    with pytest.raises(TypeError, match="PerfectOptimizer"):
        PerfectOptimizer(system, [make_day_ahead([50] * 4)], unknown_option=1)


@pytest.mark.xfail(strict=True, reason="Milp_MFRR is incomplete (no Market_output expression)")
def test_mfrr_can_be_optimized():
    market = MFRR()
    market.datasets = make_day_ahead([50] * 4).datasets
    system = System(capacity_buy=10, capacity_sell=10, efficiency=1.0)
    system.add_module(Battery(capacity=10, rte=1, c_rate=0.5, name="b"))
    PerfectOptimizer(system, [market]).solve()
