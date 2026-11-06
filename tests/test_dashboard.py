"""Dashboard figures and app construction (no server is started)."""

import pytest
from test_runs import solve_known_case

pytest.importorskip("dash")

from powersim.dashboard.app import _run_option_label, create_app  # noqa: E402
from powersim.dashboard.components import format_dt  # noqa: E402
from powersim.dashboard.figures import (  # noqa: E402
    assets_figure,
    excess_figure,
    markets_figure,
)
from powersim.dashboard.tabs import TABS  # noqa: E402
from powersim.dashboard.tabs.sandbox import daily_revenue_figure, soc_heatmap_figure  # noqa: E402
from powersim.dashboard.tabs.visualization import kpi_cards  # noqa: E402
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
    for component_id in (
        "header-info",
        "tab-selector",
        "run-selector",
        "run-status",
        "tab-visualization",
        "tab-sandbox",
        "visualization-kpis",
        "visualization-assets",
        "visualization-markets",
        "visualization-excess",
        "sandbox-daily-revenue",
        "sandbox-soc-heatmap",
    ):
        assert component_id in layout

    row = list_runs(tmp_path).iloc[0]
    assert "With aFRR" in str(_run_option_label(row))
    cards = str(kpi_cards(afrr_run))
    assert "Total revenue" in cards
    assert "Revenue AFRR" in cards


def test_header_info_text(tmp_path):
    assert "My info" in str(create_app(tmp_path, info="My info").layout)


def test_app_builds_without_runs(tmp_path):
    assert create_app(tmp_path / "missing").layout is not None


def test_tabs_have_unique_prefixed_ids():
    assert [tab.id for tab in TABS] == ["visualization", "sandbox"]
    for tab in TABS:
        ids = [c.id for c in _walk(tab.layout()) if getattr(c, "id", None)]
        assert all(i.startswith(f"{tab.id}-") for i in ids), ids


def test_sandbox_figures(afrr_run):
    data = afrr_run.timeseries_wide()
    assert trace_names(daily_revenue_figure(data)) == {"DayAhead", "AFRR"}
    heatmap = soc_heatmap_figure(data)
    assert len(heatmap.data) == 1 and heatmap.data[0].type == "heatmap"


def test_format_dt():
    assert format_dt([1.0]) == "1 h"
    assert format_dt([0.25]) == "15 min"
    assert format_dt([]) == "-"


def _walk(components):
    for component in components:
        yield component
        children = getattr(component, "children", None)
        if isinstance(children, list):
            yield from _walk(children)
        elif children is not None and not isinstance(children, str):
            yield from _walk([children])
