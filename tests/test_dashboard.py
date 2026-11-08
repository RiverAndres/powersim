"""Dashboard figures and app construction (no server is started)."""

from dataclasses import replace

import pytest
from test_runs import solve_known_case

pytest.importorskip("dash")

import pandas as pd  # noqa: E402

from powersim.dashboard.app import _run_option_label, create_app, status_row  # noqa: E402
from powersim.dashboard.components import (  # noqa: E402
    badge,
    card,
    chart_card,
    check_tile,
    columns,
    field,
    format_compact,
    format_dt,
    info_row,
    info_tile,
    kpi_grid,
    kpi_group,
    kpi_tile,
    note,
    option_card,
    section,
    side_panel,
    stack,
)
from powersim.dashboard.figures import (  # noqa: E402
    area_figure,
    hbar_figure,
    heatmap_figure,
    histogram_figure,
    line_figure,
    rows_figure,
    sankey_figure,
    series_color,
    stacked_bar_figure,
)
from powersim.dashboard.formatting import axis_scale  # noqa: E402
from powersim.dashboard.tabs import TABS, sandbox  # noqa: E402
from powersim.dashboard.tabs import overview_data as od  # noqa: E402
from powersim.dashboard.tabs import visualization as viz  # noqa: E402
from powersim.dashboard.tabs.base import computation_key, should_compute  # noqa: E402
from powersim.runs import list_runs  # noqa: E402
from powersim.visualization.styles import color_for, market_color  # noqa: E402


@pytest.fixture(scope="module")
def afrr_run():
    """Battery only (no PV), 8 hourly periods, DayAhead + aFRR."""
    return solve_known_case(with_afrr=True).results.to_run(label="With aFRR")


@pytest.fixture(scope="module")
def pv_run(afrr_run):
    """``afrr_run`` with synthetic PV generation, exported to the grid."""
    data = afrr_run.timeseries.copy()
    times = data["time"].unique()
    pv = pd.DataFrame(
        {
            "time": list(times) * 2,
            "variable": ["P_generation"] * len(times) + ["E_system_sell_generation"] * len(times),
            "value": [5.0] * len(times) * 2,
        }
    )
    data = data[~data["variable"].isin(["P_generation", "E_system_sell_generation"])]
    inputs = {**afrr_run.inputs, "generators": [{"peak_power": None, "name": "pv"}]}
    return replace(afrr_run, timeseries=pd.concat([data, pv]), inputs=inputs)


def trace_names(fig) -> set[str]:
    return {trace.name for trace in fig.data}


# ---------- App and tabs ----------


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
        "visualization-plant",
        "visualization-kpis",
        "visualization-checks",
        *viz.OVERVIEW_GRAPHS,
        *viz.FOOTNOTES,
        *[f"{card_id}-title" for card_id in viz.DYNAMIC_HEADS],
        "visualization-battery-charts",
        "visualization-battery-empty",
        "visualization-week",
        "visualization-assets",
        "visualization-markets",
    ):
        assert component_id in layout

    row = list_runs(tmp_path).iloc[0]
    assert "With aFRR" in str(_run_option_label(row))


def test_header_info_text(tmp_path):
    assert "My info" in str(create_app(tmp_path, info="My info").layout)


def test_app_builds_without_runs(tmp_path):
    assert create_app(tmp_path / "missing").layout is not None


def test_tabs_have_unique_prefixed_ids():
    assert [tab.id for tab in TABS] == ["visualization", "sandbox"]
    for tab in TABS:
        ids = [c.id for c in _walk(tab.layout()) if getattr(c, "id", None)]
        assert all(i.startswith(f"{tab.id}-") for i in ids), ids


def test_sandbox_is_empty():
    assert "No experiments right now" in str(sandbox.layout())


def test_tab_callbacks_only_run_for_the_active_tab(tmp_path):
    app = create_app(tmp_path)
    tab_callbacks = [
        callback
        for callback in app.callback_map.values()
        if any(i["id"] == "run-selector" for i in callback["inputs"])
        and "run-status" not in str(callback["output"])
    ]
    assert tab_callbacks
    for callback in tab_callbacks:
        assert {"id": "tab-selector", "property": "value"} in callback["inputs"]

    key = computation_key(["runs/a"])
    assert should_compute("sandbox", "sandbox", key, None)
    assert not should_compute("sandbox", "visualization", key, None)  # hidden tab
    assert not should_compute("sandbox", "sandbox", key, key)  # already computed
    assert should_compute("sandbox", "sandbox", computation_key(["runs/b"]), key)


def test_status_row(afrr_run):
    row = str(status_row(afrr_run))
    assert "With aFRR" in row
    assert "AFRR" in row and "badge" in row


# ---------- Visualization: callbacks ----------


def test_overview_callback(afrr_run, tmp_path):
    path = str(afrr_run.save(tmp_path))
    outputs = viz.overview_outputs(path)
    plant, kpis, checks, *rest = outputs
    figures = rest[: len(viz.OVERVIEW_GRAPHS)]
    rest = rest[len(viz.OVERVIEW_GRAPHS) :]
    notes, rest = rest[: len(viz.FOOTNOTES)], rest[len(viz.FOOTNOTES) :]
    heads, rest = rest[: 2 * len(viz.DYNAMIC_HEADS)], rest[2 * len(viz.DYNAMIC_HEADS) :]
    charts_hidden, empty_hidden, weeks, week = rest
    assert all(hasattr(f, "data") for f in figures) and len(notes) == len(viz.FOOTNOTES)
    assert heads[0] == "Revenue by day" and "per day" in heads[1]  # 8-hour run
    assert (charts_hidden, empty_hidden) == (False, True)  # it has a battery
    assert "Battery capacity" in str(plant) and "PV peak power" not in str(plant)  # no PV
    assert "Total revenue" in str(kpis) and "PV generation" not in str(kpis)
    assert "Energy balance" in str(checks) and "Curtailment" not in str(checks)
    assert weeks and week == weeks[0]["value"]

    empty = viz.overview_outputs(None)
    assert empty[-2:] == ([], None) and len(empty) == len(outputs)


def test_detail_callback(afrr_run, tmp_path):
    path = str(afrr_run.save(tmp_path))
    assets, markets = viz.detail_outputs(path, None)
    window = od.time_window(afrr_run.timeseries_wide(), None)
    assert len(assets.data[0].x) == len(window) <= 7 * 24 * 4
    assert "PV generation" not in trace_names(assets)  # empty generation row left out
    assert "Battery charge" in trace_names(assets)
    assert all(
        "<i>P_" in trace.hovertemplate and " MW" in trace.hovertemplate for trace in assets.data
    )
    assert "DayAhead price" in trace_names(markets)
    bands = [t for t in markets.data if " band " in t.name and "price" not in t.name]
    assert bands and all(t.fill is None and t.stackgroup is None for t in bands)


def test_assets_rows_share_y_except_generation(pv_run):
    fig = viz.assets_figure_from(pv_run.timeseries_wide())
    assert "P_generation" in trace_names(fig)
    assert fig.layout.yaxis.matches is None  # generation keeps its own range
    assert fig.layout.yaxis3.matches == "y2"  # POI matched to storage


def test_markets_figure_includes_every_market(afrr_run):
    fig = viz.markets_figure_from(afrr_run.timeseries_wide())
    names = trace_names(fig)
    assert {"p_DayAhead", "p_up_AFRR", "p_down_AFRR", "p_act_up_AFRR", "p_act_down_AFRR"} <= names
    assert {"P_sell_DayAhead", "P_buy_DayAhead", "Band_up_AFRR", "Band_down_AFRR"} <= names
    groups = {trace.name: trace.stackgroup for trace in fig.data}
    assert groups["P_buy_DayAhead"] == "negative" and groups["Band_up_AFRR"] == "positive"


# ---------- Visualization: content ----------


def test_overview_figures(afrr_run):
    data = afrr_run.timeseries_wide()
    revenue = viz.period_revenue_figure(data)
    assert trace_names(revenue) == {"DayAhead", "AFRR"}
    assert all("€" in text for text in revenue.data[0].customdata)  # compact hover values

    streams, streams_note = viz.revenue_streams_view(data, afrr_run.kpis["revenue_total"])
    shown = set(streams.data[0].y)
    assert "AFRR · band up" in shown and not any("benefit" in label for label in shown)
    assert all(text for text in streams.data[0].text)  # value labels at the bar ends
    for label in {"DayAhead · buy", "AFRR · act up", "AFRR · act down"} - shown:
        assert label in streams_note

    by_market, _ = viz.energy_by_market_view(data)
    assert set(by_market.data[0].y) <= {
        "DayAhead · sell",
        "DayAhead · buy",
        "AFRR · up",
        "AFRR · down",
    }

    flows = viz.period_flows_figure(data)
    sides = {trace.name: trace.y for trace in flows.data}
    assert all((sides[name] <= 0).all() for name in sides if name.endswith("→ battery"))
    assert all((sides[name] >= 0).all() for name in sides if name.endswith("→ grid"))

    heatmap = viz.soc_heatmap_figure(data, by_month=False)
    assert heatmap.data[0].type == "heatmap" and heatmap.data[0].colorbar.tickformat == ".0%"
    assert len(heatmap.data[0].x) == data.index.strftime("%Y-%m-%d").nunique()

    cycles, _ = viz.daily_cycles_view(data, afrr_run.inputs)
    assert cycles.data[0].type == "histogram"


def test_sankey_balances_and_hovers(afrr_run):
    sankey = viz.energy_sankey_figure(afrr_run.timeseries_wide()).data[0]
    labels = [label.split(" · ")[0] for label in sankey.node.label]
    assert "Battery" in labels and "PV" not in labels  # no PV node without PV
    assert all(value > 0 for value in sankey.link.value)
    inflow = dict.fromkeys(labels, 0.0)
    outflow = dict.fromkeys(labels, 0.0)
    for source, target, value in zip(
        sankey.link.source, sankey.link.target, sankey.link.value, strict=True
    ):
        outflow[labels[source]] += value
        inflow[labels[target]] += value
    assert inflow["Battery"] == pytest.approx(outflow["Battery"], rel=1e-6)
    assert sankey.hoverlabel.bgcolor == "#232322"
    assert all("→" in text and " of " in text for text in sankey.link.customdata)
    assert all("in " in text or "out " in text for text in sankey.node.customdata)
    assert not any(" 0 " in text or text.endswith(" 0") for text in sankey.node.customdata)
    # Links and nodes need their own hoverlabel (plotly ignores the trace-level one for them).
    assert sankey.link.hoverlabel.bgcolor == sankey.node.hoverlabel.bgcolor == "#232322"
    assert sankey.link.hoverlabel.font.color == "#f0efec"


def test_sankey_small_nodes_do_not_overlap():
    for column_x in {x for _, (x, _y) in viz.NODES.values()}:
        ys = sorted(y for _, (x, y) in viz.NODES.values() if x == column_x and y > 0.7)
        assert all(b - a >= 0.07 for a, b in zip(ys, ys[1:], strict=False)), (column_x, ys)


def test_headline_numbers(afrr_run, pv_run):
    data = afrr_run.timeseries_wide()
    economics, energy = viz.headline_kpis(afrr_run, data)
    assert "avg sell price" in str(economics) and "extrapolated" in str(economics)
    total = format_compact(afrr_run.kpis["revenue_total"], "€", 0)[0]  # 3 digits, as the rest
    assert f"children=['{total}'" in str(economics)
    assert "Equivalent cycles" in str(energy) and "PV generation" not in str(energy)
    expected = data["B_sell_DayAhead"].sum() / data["E_sell_DayAhead"].sum()
    assert f"{expected:,.1f}" in str(viz.captured_price_tiles(data))

    _, pv_energy = viz.headline_kpis(pv_run, pv_run.timeseries_wide())
    assert "PV generation" in str(pv_energy) and "Curtailment" in str(pv_energy)

    no_battery = replace(afrr_run, inputs={**afrr_run.inputs, "batteries": []})
    _, energy = viz.headline_kpis(no_battery, data)
    assert "Equivalent cycles" not in str(energy)
    assert "Daily cycle limit" not in str(od.run_checks(no_battery.inputs, no_battery.kpis, data))


def test_grid_columns_avoid_orphans():
    assert [viz.grid_columns(n) for n in (3, 4, 6, 8, 9, 12)] == [3, 4, 3, 4, 3, 4]


def test_plant_tiles():
    tiles = str(viz.plant_tiles({"batteries": [{"capacity": 4, "c_rate": 0.5, "rte": 0.9}]}))
    assert "2 MW" in tiles and "4 MWh" in tiles and "2 h" in tiles and "90%" in tiles
    assert "'-'" in tiles  # grid capacities
    assert "PV peak power" not in tiles  # no PV

    data = pd.DataFrame({"P_generation": [0.0, 12.34, 3.0]})
    observed = str(viz.plant_tiles({"generators": [{"peak_power": None}]}, data))
    assert "PV max output" in observed and "12.3 MW" in observed
    assert "Battery capacity" not in observed  # no battery


# ---------- Overview data ----------


def test_partial_periods():
    index = pd.date_range("2025-01-01", "2025-03-01 23:00", freq="h")  # Jan, Feb, 1 day of Mar
    notes = od.partial_periods(index, od.MONTHLY)
    assert list(notes) == ["", "", "partial · 1 of 31 days"]
    daily = od.partial_periods(pd.date_range("2025-01-01 12:00", periods=36, freq="h"), od.DAILY)
    assert list(daily) == ["partial · 12 of 24 h", ""]


def test_period_rule():
    def index(days):
        return pd.date_range("2025-01-01", periods=days * 24, freq="h")

    assert od.period_rule(index(2)) is od.DAILY
    assert od.period_rule(index(30)) is od.WEEKLY
    assert od.period_rule(index(200)) is od.MONTHLY
    frame = pd.DataFrame({"x": 1.0}, index=index(30))
    weekly = od.aggregate(frame, od.WEEKLY)
    assert weekly["x"].sum() == len(frame) and (weekly.index.dayofweek == 0).all()


def test_run_checks(afrr_run):
    data = afrr_run.timeseries_wide()
    checks = {c["label"]: c for c in od.run_checks(afrr_run.inputs, afrr_run.kpis, data)}
    assert {
        "Daily cycle limit",
        "Simultaneous charge and discharge",
        "Energy balance",
        "Export consistency",
    } <= set(checks)
    assert all(check["status"] in {"ok", "warn", "info"} for check in checks.values())
    assert checks["Simultaneous charge and discharge"]["detail"] == "allowed by the model"
    assert checks["Energy balance"]["status"] == "ok"  # the flows close by construction


def test_check_functions():
    cycles = pd.Series([1.0, 1.6, 1.7, 0.5])
    assert od.check_cycle_limit(cycles, 1.5)["value"] == "2 days above 1.5/day"
    assert od.check_cycle_limit(cycles, 1.5)["status"] == "warn"
    assert od.check_cycle_limit(cycles, 2.0)["status"] == "ok"
    assert od.check_cycle_limit(cycles, None)["value"] == "no limit set"

    data = pd.DataFrame({"P_storage_charge": [-1.0, -1.0, 0.0], "P_storage_discharge": [1.0, 0, 0]})
    assert od.check_simultaneous(data)["value"] == "1 periods (33.3%)"

    links = [("PV", "Grid export", 90.0), ("PV", "Battery", 5.0), ("Battery", "Grid export", 5.0)]
    assert od.check_energy_balance(links, 100.0)["status"] == "warn"  # 5 MWh missing
    assert od.check_energy_balance(links, 95.0)["status"] == "ok"

    exports = pd.DataFrame({"E_system_sell_generation": [50.0], "E_system_sell_storage": [50.0]})
    assert od.check_export(exports, 100.0)["status"] == "ok"
    assert od.check_export(exports, 101.0)["status"] == "warn"

    assert od.check_curtailment(6.0, 100.0)["status"] == "warn"
    assert od.check_curtailment(1.0, 100.0)["value"] == "1.0% of PV generation"


def test_daily_cycles_highlight_days_above_limit():
    index = pd.date_range("2025-01-01", periods=3 * 24, freq="h")
    data = pd.DataFrame({"P_storage_discharge": [0.0] * 24 + [3.0] * 24 + [1.0] * 24}, index=index)
    inputs = {"batteries": [{"capacity": 40, "max_cycles_day": 1.5}]}
    figure, footnote = viz.daily_cycles_view(data, inputs)
    assert footnote == "1 days above the limit"  # 72 MWh / 40 MWh = 1.8 cycles
    assert len(figure.data) == 2 and figure.data[1].marker.color == "#ffa94d"
    assert figure.layout.annotations[0].text == "max 1.5/day"


def test_series_labels():
    labels = od.series_labels(
        ["P_generation", "p_DayAhead", "p_act_up_AFRR", "Band_down_AFRR", "P_sell_X", "SOC_b"]
    )
    assert labels == {
        "P_generation": "PV generation",
        "p_DayAhead": "DayAhead price",
        "p_act_up_AFRR": "AFRR activation up price",
        "Band_down_AFRR": "AFRR band down",
        "P_sell_X": "X sell",
    }


def test_format_dt():
    assert format_dt([1.0]) == "1 h"
    assert format_dt([0.25]) == "15 min"
    assert format_dt([]) == "-"


# ---------- Generic components and figure builders ----------


@pytest.fixture
def frame():
    index = pd.date_range("2025-01-01", periods=48, freq="h")
    return pd.DataFrame(
        {"P_sell_X": [1.0] * 48, "P_buy_X": [-1.0] * 48, "p_X": range(48)}, index=index
    )


def test_line_and_area_figures(frame):
    lines = line_figure(frame, y_title="MW", height=300)
    assert trace_names(lines) == set(frame.columns)
    assert lines.layout.height == 300 and lines.layout.yaxis.title.text == "MW"
    assert lines.data[0].line.color == series_color("P_sell_X")

    overlapping = area_figure(frame[["P_sell_X"]], colors={"P_sell_X": "#123456"})
    assert overlapping.data[0].fill == "tozeroy" and overlapping.data[0].line.color == "#123456"

    stacked = area_figure(frame, stacked=True)
    groups = {trace.name: trace.stackgroup for trace in stacked.data}
    assert groups == {"P_sell_X": "positive", "P_buy_X": "negative", "p_X": "positive"}


def test_stacked_bar_figure(frame):
    fig = stacked_bar_figure(frame.resample("D").sum(), y_title="€")
    assert fig.layout.barmode == "relative"
    assert all(trace.type == "bar" for trace in fig.data) and len(fig.data) == 3


def test_heatmap_figure(frame):
    grid = frame[["p_X"]].T
    fig = heatmap_figure(grid, zmin=0, zmax=47, y_dtick=1)
    assert fig.data[0].type == "heatmap" and fig.layout.hovermode == "closest"
    assert len(heatmap_figure(pd.DataFrame()).data) == 0


def test_rows_figure(frame):
    fig = rows_figure(
        [line_figure(frame[["p_X"]], y_title="EUR/MWh"), area_figure(frame[["P_sell_X"]])],
        subplot_titles=["Prices", "Operation"],
        shared_y=True,
        height=500,
    )
    assert [trace.yaxis for trace in fig.data] == ["y", "y2"]
    assert fig.layout.yaxis.title.text == "EUR/MWh"
    assert fig.layout.yaxis2.matches == "y" and fig.layout.height == 500


def test_generic_components():
    tile = str(kpi_tile("Revenue", 1234.6, "€", decimals=0, primary=True, sub="50%"))
    assert "1,235" in tile and "kpi-primary" in tile and "50%" in tile
    assert "-" in str(kpi_tile("Missing", None, "MWh"))
    assert kpi_grid([], id="x-kpis").id == "x-kpis"

    graph_card = chart_card("x-graph", "Title", "hint", height=250)
    assert "x-graph" in str(graph_card) and "250px" in str(graph_card)
    assert "Body" in str(card("Plain", children="Body"))
    assert "Group" in str(section("Group", [card("A")]))
    assert badge("AFRR").className == "badge"
    assert note("Hello").className == "note"
    assert "meta" in str(option_card("label", "meta"))
    panel = side_panel("Panel", [note("x")], actions=badge("a"), class_name="sidebar-left")
    assert panel.className == "sidebar sidebar-left"


def test_format_compact():
    assert format_compact(37241389.49, "€", digits=4) == ("37.24", "M€")
    assert format_compact(5782826, "€") == ("5.78", "M€")
    assert format_compact(83581.3, "MWh") == ("83.6", "GWh")
    assert format_compact(9876.5, "MWh", decimals=0) == ("9,876", "MWh")
    assert format_compact(-25000, "€") == ("-25.0", "k€")
    assert format_compact(123456, "") == ("123k", "")
    assert format_compact(None, "€") == ("-", "€")


def test_compact_kpi_tile_keeps_full_value_in_tooltip():
    tile = kpi_tile("Revenue", 37241389.49, "€", decimals=0, compact=True, digits=4)
    assert tile.title == "37,241,389 €"
    assert "37.24" in str(tile) and "M€" in str(tile)


def test_layout_components():
    grid = kpi_grid([kpi_tile("A", 1, "")], columns=4)
    assert "kpi-grid-fixed" in grid.className and grid.style["--kpi-columns"] == 4
    assert "Group" in str(kpi_group("Group", [], columns=2))
    assert columns([note("a"), note("b")], widths=[2, 1]).style["--columns"] == (
        "minmax(0, 2fr) minmax(0, 1fr)"
    )
    assert "'-'" in str(info_tile("Missing", None))
    assert info_row([info_tile("A", 1)], id="x-row").id == "x-row"
    assert stack(id="x-stack").id == "x-stack"
    assert "Week" in str(field("Week", note("control")))


def test_hbar_and_sankey_figures():
    bars = hbar_figure(pd.Series({"a": 1.0, "b": -3.0, "c": 2.0}), colors={"a": "#111111"})
    assert list(bars.data[0].y) == ["b", "a", "c"] and bars.data[0].orientation == "h"
    assert bars.data[0].marker.color[1] == "#111111"

    fig = sankey_figure(
        ["A", "B", "C", "Unused"],
        [("A", "B", 5.0), ("A", "C", 0.0), ("B", "C", -2.0)],
        node_colors={"A": "#ff0000"},
    )
    sankey = fig.data[0]
    assert list(sankey.node.label) == ["A", "B", "C"]
    assert list(sankey.link.value) == [5.0, 2.0]
    assert sankey.link.color[0] == "rgba(255, 64, 64, 0.4)"  # lighter, translucent


def test_generic_builders_options():
    index = pd.date_range("2025-01-01", periods=4, freq="h")
    frame = pd.DataFrame({"Band_up_X": [5.0] * 4, "P_up_X": [1.0] * 4}, index=index)
    fig = area_figure(frame, stacked=True, line_columns=["Band_up_X"])
    band, power = fig.data
    assert band.line.dash == "dash" and band.stackgroup is None and band.fill is None
    assert power.stackgroup == "positive"

    sankey = sankey_figure(
        ["A", "B"], [("A", "B", 12000.0)], unit="MWh", show_totals=True, positions={"A": (0, 0.5)}
    ).data[0]
    assert list(sankey.node.label) == ["A · 12.0 GWh", "B · 12.0 GWh"]
    assert sankey.node.x[0] == 0

    hist = histogram_figure(
        pd.Series([0.5, 1.0, 1.2]), bin_size=0.1, marker=1.5, marker_label="max"
    )
    assert hist.data[0].type == "histogram" and hist.layout.shapes[0].x0 == 1.5


def test_check_tile_and_labels_option():
    tile = check_tile("Energy balance", "0.000%", "ok", "detail")
    assert tile.className == "check check-ok" and "detail" in str(tile)
    assert check_tile("X", None).className == "check check-info"

    frame = pd.DataFrame({"P_x": [1.0, 2.0]})
    fig = line_figure(frame, labels={"P_x": "Nice name"})
    assert fig.data[0].name == "Nice name" and "P_x" in fig.data[0].hovertemplate
    assert area_figure(frame).data[0].name == "P_x"  # default keeps raw names


def test_market_base_colors():
    assert market_color("AFRR") == color_for("B_benefit_AFRR") == color_for("E_up_AFRR")
    assert color_for("p_act_up_AFRR") == "red"  # fixed colors keep priority


def test_units_hover_and_axes():
    index = pd.date_range("2025-01-01", periods=3, freq="MS")
    revenue = pd.DataFrame({"A": [1.5e6, 2.0e6, -0.2e6]}, index=index)
    bars = stacked_bar_figure(revenue, unit="€", x_format="%b %Y")
    assert bars.layout.yaxis.title.text == "M€" and bars.data[0].y[0] == 1.5
    assert bars.data[0].customdata[0] == "1.50 M€"
    # One horizontal tick per bar, year on a second line.
    assert list(bars.layout.xaxis.ticktext) == ["Jan<br>2025", "Feb<br>2025", "Mar<br>2025"]
    assert bars.layout.xaxis.tickangle == 0

    many = pd.DataFrame({"A": range(24)}, index=pd.date_range("2025-01-01", periods=24, freq="MS"))
    ticks = stacked_bar_figure(many, x_format="%b %Y").layout.xaxis
    assert len(ticks.tickvals) == 8 and ticks.ticktext[1] == "Apr<br>2025"  # every 3 months

    partial = pd.Series(["", "", "partial · 1 of 31 days"], index=index)
    marked = stacked_bar_figure(revenue, unit="€", partial=partial).data[0]
    assert list(marked.marker.opacity) == [1.0, 1.0, 0.45]
    assert marked.customdata[2] == "-200 k€ · partial · 1 of 31 days"

    energy = hbar_figure(pd.Series({"a": 83000.0}), unit="MWh", value_labels=True)
    assert energy.layout.xaxis.title.text == "GWh" and energy.data[0].text[0] == "83.0 GWh"

    lines = line_figure(pd.DataFrame({"p_X": [1.0]}), unit="€/MWh")
    assert lines.data[0].hovertemplate == "%{y:,.1f} €/MWh"
    assert lines.layout.hoverlabel.font.color == "#f0efec"
    assert lines.layout.legend.yanchor == "top" and lines.layout.legend.y < 0  # below the plot

    assert axis_scale(1.5e6, "€") == (1e6, "M€")
    assert axis_scale(5000, "€") == (1.0, "€")
    assert axis_scale(83000, "MWh") == (1e3, "GWh")


def test_histogram_integer_ticks_and_marker_inside():
    fig = histogram_figure(
        pd.Series([1.0, 1.05, 2.0]), bin_size=0.1, marker=1.5, marker_label="max"
    )
    assert fig.layout.yaxis.dtick == 1 and fig.layout.yaxis.tick0 == 0
    label = fig.layout.annotations[0]
    assert label.text == "max" and label.yref == "paper" and label.y < 1 and label.xanchor == "left"


def test_rows_figure_partial_shared_y(frame):
    fig = rows_figure(
        [area_figure(frame[["P_sell_X"]]) for _ in range(3)], shared_y=[2, 3], height=600
    )
    assert fig.layout.yaxis.matches is None and fig.layout.yaxis3.matches == "y2"


def _walk(components):
    for component in components:
        yield component
        children = getattr(component, "children", None)
        if isinstance(children, list):
            yield from _walk(children)
        elif children is not None and not isinstance(children, str):
            yield from _walk([children])
