"""SimulationRun: standardized export, save/load round trip, KPIs and catalog."""

import pandas as pd
import pytest
from conftest import TOL, make_afrr, make_day_ahead, time_index

from powersim import Battery, PerfectOptimizer, SimulationRun, System, list_runs

RUN_FILES = {
    "manifest.json",
    "inputs.json",
    "solver.json",
    "kpis.json",
    "timeseries.parquet",
    "market_data.parquet",
}


def solve_known_case(with_afrr: bool = False) -> PerfectOptimizer:
    """RTE = 1 battery, 4 h at 10 EUR/MWh then 4 h at 100 EUR/MWh: exactly one cycle, 900 EUR."""
    system = System(capacity_buy=10, capacity_sell=10, efficiency=1.0)
    system.add_module(Battery(capacity=10, rte=1.0, c_rate=0.25, name="b"))
    markets = [make_day_ahead([10] * 4 + [100] * 4)]
    if with_afrr:
        markets.append(make_afrr(time_index(8), p_up=5))
    return PerfectOptimizer(system, markets).solve()


@pytest.fixture(scope="module")
def known_run() -> SimulationRun:
    return solve_known_case().results.to_run(label="Known case", tags=["test"])


@pytest.fixture(scope="module")
def afrr_run() -> SimulationRun:
    return solve_known_case(with_afrr=True).results.to_run(label="With aFRR")


def assert_same_run(a: SimulationRun, b: SimulationRun):
    assert a.manifest == b.manifest
    assert a.inputs == b.inputs
    assert a.solver == b.solver
    assert a.kpis == b.kpis
    pd.testing.assert_frame_equal(a.timeseries, b.timeseries)
    pd.testing.assert_frame_equal(a.market_data, b.market_data)


@pytest.mark.parametrize("run_fixture", ["known_run", "afrr_run"])
def test_save_and_load_round_trip(run_fixture, request, tmp_path):
    run = request.getfixturevalue(run_fixture)
    path = run.save(tmp_path)

    assert {p.name for p in path.iterdir()} == RUN_FILES | {"derived"}
    assert_same_run(SimulationRun.load(path), run)


def test_kpis_of_known_case(known_run):
    kpis = known_run.kpis

    assert kpis["revenue_total"] == pytest.approx(900, abs=TOL)
    assert kpis["revenue_by_market"] == {"DayAhead": pytest.approx(900, abs=TOL)}
    assert kpis["energy_charged_MWh"] == pytest.approx(10, abs=TOL)
    assert kpis["energy_discharged_MWh"] == pytest.approx(10, abs=TOL)
    assert kpis["equivalent_cycles"] == pytest.approx(1, abs=TOL)
    assert kpis["excess_energy_MWh"] == pytest.approx(0, abs=TOL)


def test_revenue_by_market_adds_up_to_objective(afrr_run):
    kpis = afrr_run.kpis
    assert set(kpis["revenue_by_market"]) == {"DayAhead", "AFRR"}
    assert sum(kpis["revenue_by_market"].values()) == pytest.approx(kpis["revenue_total"], abs=1e-3)


def test_inputs_and_solver_are_recorded(afrr_run):
    inputs = afrr_run.inputs
    assert inputs["system"]["capacity_sell"] == 10
    assert inputs["batteries"][0]["name"] == "b"
    assert [m["type"] for m in inputs["markets"]] == ["DayAhead", "AFRR"]
    assert inputs["period"]["n_periods"] == 8
    assert inputs["period"]["dt_hours"] == [1.0]
    assert inputs["optimizer_params"] == {"solver_name": "highs", "precision": 1}

    assert afrr_run.solver["termination_condition"] == "optimal"
    assert afrr_run.solver["objective"] == pytest.approx(afrr_run.kpis["revenue_total"])


def test_realized_activations_are_stored(afrr_run):
    afrr_datasets = set(afrr_run.market_data.query("market == 'AFRR'")["dataset"])
    assert {"e_act_up_realized", "e_act_down_realized"} <= afrr_datasets


def test_timeseries_wide_keeps_column_order(known_run):
    wide = known_run.timeseries_wide()
    assert list(wide.columns[:3]) == ["P_system_import", "P_system_export", "P_generation"]
    assert len(wide) == 8


def test_save_never_overwrites(tmp_path):
    optimizer = solve_known_case()
    first = optimizer.results.to_run(label="same").save(tmp_path)
    second = optimizer.results.to_run(label="same").save(tmp_path)

    assert first != second
    assert len(list(tmp_path.iterdir())) == 2


def test_list_runs(known_run, afrr_run, tmp_path):
    known_run.save(tmp_path)
    afrr_run.save(tmp_path)
    (tmp_path / "not_a_run").mkdir()

    catalog = list_runs(tmp_path)

    assert len(catalog) == 2
    assert catalog["created_at"].is_monotonic_decreasing
    assert set(catalog["label"]) == {"Known case", "With aFRR"}
    afrr_row = catalog.set_index("label").loc["With aFRR"]
    assert afrr_row["markets"] == ["DayAhead", "AFRR"]
    assert "revenue_AFRR" in catalog.columns


def test_list_runs_of_empty_folder(tmp_path):
    assert list_runs(tmp_path).empty
