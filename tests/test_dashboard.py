"""Dashboard figures and app construction (no server is started)."""

import pytest
from test_runs import solve_known_case

pytest.importorskip("dash")

from powersim.dashboard.app import _kpis_panel, _run_option_label, create_app  # noqa: E402
from powersim.dashboard.figures import (  # noqa: E402
    assets_figure,
    excess_figure,
    markets_figure,
)
from powersim.runs import list_runs  # noqa: E402


@pytest.fixture(scope="module")
def afrr_run():
    return solve_known_case(with_afrr=True).results.to_run(label="With aFRR")


def trace_names(fig) -> set[str]:
    return {trace.name for trace in fig.data}


def test_assets_figure(afrr_run):
    fig = assets_figure(afrr_run)

    assert trace_names(fig) == {
        "P_generation",
        "P_storage_charge",
        "P_storage_discharge",
        "P_system_export",
        "P_system_import",
    }
    # Three rows sharing the y axis, as in plot_operation.
    assert {fig.layout.yaxis2.matches, fig.layout.yaxis3.matches} == {"y"}


def test_markets_figure_includes_every_market(afrr_run):
    fig = markets_figure(afrr_run)
    names = trace_names(fig)

    assert {"p_DayAhead", "p_up_AFRR", "p_down_AFRR", "p_act_up_AFRR", "p_act_down_AFRR"} <= names
    assert {"P_sell_DayAhead", "P_buy_DayAhead", "Band_up_AFRR", "Band_down_AFRR"} <= names
    assert {"P_up_AFRR", "P_down_AFRR"} <= names


def test_negative_series_stack_separately(afrr_run):
    groups = {trace.name: trace.stackgroup for trace in markets_figure(afrr_run).data}

    assert groups["P_buy_DayAhead"] == "negative"
    assert groups["Band_down_AFRR"] == "negative"
    assert groups["P_sell_DayAhead"] == "positive"
    assert groups["Band_up_AFRR"] == "positive"


def test_excess_figure(afrr_run):
    assert trace_names(excess_figure(afrr_run)) == {"P_excess"}


def test_app_builds_with_runs(afrr_run, tmp_path):
    afrr_run.save(tmp_path)
    app = create_app(tmp_path)

    layout = str(app.layout)
    for component_id in ("run-selector", "assets-graph", "markets-graph", "excess-graph"):
        assert component_id in layout

    row = list_runs(tmp_path).iloc[0]
    assert "With aFRR" in _run_option_label(row)
    assert "Total revenue" in str(_kpis_panel(afrr_run))


def test_app_builds_without_runs(tmp_path):
    assert create_app(tmp_path / "missing").layout is not None
