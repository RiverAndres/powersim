"""Post-solve tasks: derived data stored next to a run and recomputed without re-simulating."""

import json

import pandas as pd
import pytest
from test_runs import solve_known_case

from powersim.runs import SimulationRun, load_derived, update_runs
from powersim.runs import post_solve as ps
from powersim.runs.indicators import all_indicators


@pytest.fixture
def afrr_run() -> SimulationRun:
    return solve_known_case(with_afrr=True).results.to_run(label="post solve")


@pytest.fixture
def custom_task():
    """A temporary extra task, removed after the test."""
    calls = []

    def compute(run):
        calls.append(run.id)
        frame = pd.DataFrame({"x": [1.0, 2.0]}, index=pd.Index(["a", "b"], name="k"))
        return ps.Derived(
            kpis={"n_periods": run.inputs["period"]["n_periods"]}, tables={"t": frame}
        )

    task = ps.register(ps.PostSolveTask("custom", version=1, compute=compute))
    yield task, calls
    ps._TASKS.pop("custom", None)


def test_save_stores_indicators(afrr_run, tmp_path):
    path = afrr_run.save(tmp_path)

    meta = json.loads((path / "derived" / "indicators.json").read_text(encoding="utf-8"))
    assert meta["task"] == "indicators"
    assert meta["version"] == ps.INDICATORS_TASK.version

    expected = all_indicators(afrr_run.inputs, afrr_run.kpis, afrr_run.timeseries_wide())
    derived = afrr_run.derived("indicators")
    assert set(derived.kpis) == set(expected)
    for name, indicator in expected.items():
        assert derived.kpis[name]["available"] == indicator.available
        for key, value in indicator.kpis.items():
            stored = derived.kpis[name][key]
            if isinstance(value, float):
                assert stored == pytest.approx(value, nan_ok=True)
            else:
                assert stored == value
        for table, frame in indicator.tables.items():
            pd.testing.assert_frame_equal(
                derived.tables[f"{name}_{table}"], frame, check_freq=False, check_dtype=False
            )


def test_save_without_post_solve(afrr_run, tmp_path):
    path = afrr_run.save(tmp_path, post_solve=False)
    assert not (path / "derived").exists()
    assert afrr_run.derived() is None


def test_update_runs_adds_then_skips(afrr_run, tmp_path, custom_task):
    _, calls = custom_task
    afrr_run.save(tmp_path, post_solve=False)

    first = update_runs(tmp_path)
    assert {(task, status) for _, task, status in first} == {
        ("indicators", "computed"),
        ("custom", "computed"),
    }
    second = update_runs(tmp_path)
    assert {status for _, _, status in second} == {"up-to-date"}
    assert len(calls) == 1

    forced = update_runs(tmp_path, names=["custom"], force=True)
    assert forced == [(afrr_run.id, "custom", "computed")]
    assert len(calls) == 2


def test_version_bump_recomputes(afrr_run, tmp_path, custom_task):
    task, calls = custom_task
    afrr_run.save(tmp_path)
    assert len(calls) == 1

    ps.register(ps.PostSolveTask("custom", version=2, compute=task.compute))
    assert update_runs(tmp_path, names=["custom"]) == [(afrr_run.id, "custom", "computed")]
    assert load_derived(afrr_run.path, "custom").version == 2


def test_custom_task_tables_round_trip(afrr_run, tmp_path, custom_task):
    afrr_run.save(tmp_path)
    derived = load_derived(afrr_run.path, "custom")

    assert derived.kpis == {"n_periods": afrr_run.inputs["period"]["n_periods"]}
    expected = pd.DataFrame({"x": [1.0, 2.0]}, index=pd.Index(["a", "b"], name="k"))
    pd.testing.assert_frame_equal(derived.tables["t"], expected)


def test_failing_task_does_not_break_save(afrr_run, tmp_path):
    def broken(run):
        raise RuntimeError("boom")

    ps.register(ps.PostSolveTask("broken", version=1, compute=broken))
    try:
        with pytest.warns(UserWarning, match="boom"):
            path = afrr_run.save(tmp_path)
        assert (path / "manifest.json").exists()
        assert (path / "derived" / "indicators.json").exists()
        assert not (path / "derived" / "broken.json").exists()
    finally:
        ps._TASKS.pop("broken", None)


def test_clean_makes_json_safe():
    import numpy as np

    cleaned = ps._clean({"a": np.float64(1.5), "b": float("nan"), "c": [np.int64(2)], "d": "x"})
    assert cleaned == {"a": 1.5, "b": None, "c": [2], "d": "x"}


def test_invalid_task_name():
    with pytest.raises(ValueError):
        ps.register(ps.PostSolveTask("a__b", version=1, compute=lambda run: ps.Derived()))
