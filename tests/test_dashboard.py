"""Dashboard figures and app construction (no server is started)."""

from dataclasses import replace

import pytest
from test_runs import solve_known_case

pytest.importorskip("dash")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from powersim.dashboard.app import _run_option_label, create_app, status_row  # noqa: E402
from powersim.dashboard.components import (  # noqa: E402
    badge,
    card,
    chart_card,
    check_list,
    check_tile,
    columns,
    data_table,
    field,
    format_compact,
    format_dt,
    hero_strip,
    kpi_grid,
    kpi_group,
    kpi_tile,
    note,
    option_card,
    section,
    side_panel,
    spec_card,
    stack,
    stat_list,
    stat_row,
    status_summary,
)
from powersim.dashboard.figures import (  # noqa: E402
    area_figure,
    binned_histogram_figure,
    hbar_figure,
    heatmap_figure,
    histogram_figure,
    line_figure,
    rows_figure,
    sankey_figure,
    scatter_figure,
    series_color,
    stacked_bar_figure,
    stacked_node_positions,
)
from powersim.dashboard.formatting import axis_scale  # noqa: E402
from powersim.dashboard.tabs import TABS, developer, sandbox, sizing_checks  # noqa: E402
from powersim.dashboard.tabs import overview_data as od  # noqa: E402
from powersim.dashboard.tabs import visualization as viz  # noqa: E402
from powersim.dashboard.tabs.base import computation_key, should_compute  # noqa: E402
from powersim.runs import list_runs  # noqa: E402
from powersim.runs.indicators import Indicator, all_indicators, unavailable  # noqa: E402
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


@pytest.fixture(scope="module")
def pv_only_run(pv_run):
    """``pv_run`` without battery nor aFRR bands (PV plant selling to the grid)."""
    data = pv_run.timeseries
    data = data[~data["variable"].str.startswith(("Band_", "SOC_", "P_storage_"))]
    return replace(pv_run, timeseries=data, inputs={**pv_run.inputs, "batteries": []})


def indicators_of(run) -> dict:
    return all_indicators(run.inputs, run.kpis, run.timeseries_wide(), run.market_data)


def graph_ids(components) -> set[str]:
    return {c.id for c in _walk(components) if type(c).__name__ == "Graph"}


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
        "tab-developer",
        "developer-checks",
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


def test_callback_ids_exist_in_layout(tmp_path):
    """Every callback Input/Output id must be in the initial layout (Dash fails at runtime)."""
    app = create_app(tmp_path)
    layout_ids = {c.id for c in _walk([app.layout]) if getattr(c, "id", None)}
    for key, callback in app.callback_map.items():
        deps = [*callback["inputs"], *callback.get("state", [])]
        outputs = key.strip(".").split("...")  # "..a.children...b.hidden.." or "a.children"
        ids = {dep["id"] for dep in deps} | {out.rsplit(".", 1)[0] for out in outputs}
        assert ids <= layout_ids, ids - layout_ids


def test_tabs_have_unique_prefixed_ids():
    assert [tab.id for tab in TABS] == ["visualization", "sandbox", "developer"]
    for tab in TABS:
        ids = [c.id for c in _walk(tab.layout()) if getattr(c, "id", None)]
        assert all(i.startswith(f"{tab.id}-") for i in ids), ids


def test_sandbox_is_empty_without_experiments(tmp_path):
    """All experiments were moved or discarded (2026-11-09): only a note, no callbacks."""
    assert "No experiments right now" in str(sandbox.layout())
    app = create_app(tmp_path)
    assert not any("sandbox-" in key for key in app.callback_map if "computed" not in key)


def _sizing_results(sizing=None, grid=None, usage=None, afrr=None, pv=None) -> dict:
    def make(kpis):
        return Indicator(kpis=kpis) if kpis is not None else unavailable("n/a")

    return {
        "sizing": make(sizing),
        "grid": make(grid),
        "battery_usage": make(usage),
        "afrr": make(afrr),
        "pv_capture": make(pv),
    }


def test_sizing_checks_verdicts():
    battery = {
        "battery_power": 5.0,
        "extra_power_value": 3_000.0,
        "average_power_value": 85_000.0,
        "duration_hours": 2.0,
        "full_range_days_share": 0.99,
        "next_hour_value": 37_000.0,
        "last_hour_value": 41_000.0,
        "average_energy_value": 42_000.0,
        "mean_cycles_day": 1.3,
        "yearly_budget_used": 0.7,
        "days_at_cycle_limit_share": 0.0,
        "band_cap_share": 0.97,
        "band_cap": 2.5,
    }
    grid = {"capacity_sell": 5.0, "capacity_buy": 5.0, "capacity_factor": 0.2}
    usage = {"soc_min": 0.0, "soc_max": 1.0, "mean_daily_dod": 0.99, "idle_share": 0.5}

    def verdicts(sizing, grid=grid, usage=usage, **others):
        results = _sizing_results(sizing, grid, usage, **others)
        return {c["label"]: c for c in sizing_checks.sizing_checks(results)}

    by_label = verdicts(battery, afrr={"market": "AFRR"})
    labels = list(by_label)
    # The grid access comes first, as a given condition (no status).
    assert labels[0] == "Grid access" and by_label["Grid access"]["status"] is None
    access = by_label["Is the battery power coherent with the grid access?"]
    assert access["status"] == "ok" and access["value"].startswith("Matched")
    hours = by_label["Do the battery hours make sense?"]
    assert hours["status"] == "warn" and hours["value"].startswith("Short")
    assert by_label["AFRR band"]["status"] is None  # informative row
    assert "Is the PV peak coherent with the grid access?" not in by_label  # no PV

    # Battery below the access: worth filling only if one more MW earns enough.
    small = {**battery, "battery_power": 3.0}
    access = verdicts(small)["Is the battery power coherent with the grid access?"]
    assert access["status"] == "ok" and "adds only" in access["value"]
    access = verdicts({**small, "extra_power_value": 60_000.0})[
        "Is the battery power coherent with the grid access?"
    ]
    assert access["status"] == "warn"
    above = verdicts({**battery, "battery_power": 7.0})
    assert above["Is the battery power coherent with the grid access?"]["status"] == "info"

    # PV: battery absorbs the small excess, little clipping → room for more PV.
    pv = {"pv_energy_mwh": 100.0, "pv_peak": 6.0, "pv_max_mw": 5.7, "pv_excess_mw": 0.7}
    pv |= {"pv_above_connection_mwh": 0.4, "pv_spilled_battery_full_mwh": 0.8}
    pv |= {"dc_ac_ratio": 1.2, "battery_charge_from_pv_share": 0.8}
    by_label = verdicts({**battery, **pv}, pv={})
    assert by_label["Is the battery power coherent with the PV?"]["status"] == "ok"
    assert by_label["Is the PV peak coherent with the grid access?"]["value"].startswith("Room")
    # Too much PV: lost with the battery full; battery smaller than the PV excess.
    lots = {**battery, **pv, "pv_spilled_battery_full_mwh": 5.0, "pv_excess_mw": 6.0}
    by_label = verdicts(lots, pv={})
    assert by_label["Is the battery power coherent with the PV?"]["value"].startswith("Too small")
    assert by_label["Is the PV peak coherent with the grid access?"]["status"] == "warn"

    # Long battery: the last installed hour earns little.
    long = {**battery, "full_range_days_share": 0.2, "last_hour_value": 5_000.0}
    hours = verdicts(long)["Do the battery hours make sense?"]
    assert hours["status"] == "info" and hours["value"].startswith("Long")
    # The cycle limit binding also asks for more hours.
    tight = {**long, "last_hour_value": 41_000.0, "yearly_budget_used": 0.99}
    assert verdicts(tight)["Do the battery hours make sense?"]["value"] == (
        "Short · the cycle limit binds"
    )
    assert sizing_checks.sizing_checks(_sizing_results()) == []

    # Plant without assets (limit case): import 0 MW is shown, no battery shares in the band.
    bare = verdicts(
        {"band_cap_share": 0.9, "band_cap": 2.5},
        grid={**grid, "capacity_buy": 0},
        usage=None,
        afrr={"market": "AFRR"},
    )
    assert bare["Grid access"]["value"] == "export 5 MW · import 0 MW"
    assert bare["AFRR band"]["detail"] == "cap 2.5 MW"


def test_developer_checks(afrr_run, tmp_path):
    assert "developer-checks" in str(developer.layout())
    checks = str(developer.checks_outputs(str(afrr_run.save(tmp_path))))
    assert "Energy balance" in checks and "Curtailment" not in checks
    assert "Reserve band backed by the assets" in checks and "Exports at price ≤ 0" in checks
    assert developer.checks_outputs(None) == []


def test_flow_charts_without_flows(frame):
    """A run without assets (limit case) has no flows: a message instead of empty axes."""
    zero = frame.assign(**{c: 0.0 for c in frame.columns if c.startswith(("P_", "E_"))})
    for fig in (viz.energy_sankey_figure(zero), viz.period_flows_figure(zero)):
        assert not fig.data and fig.layout.annotations[0].text == viz.NO_FLOWS


def test_reserve_checks_against_assets():
    index = pd.date_range("2026-01-01", periods=4, freq="h", tz="UTC")
    data = pd.DataFrame(
        {
            "P_generation": [0.0, 3.0, 3.0, 0.0],
            "Band_up_AFRR": [2.0, 2.0, 0.0, 0.0],
            "Band_down_AFRR": [0.0, 0.0, -1.0, 0.0],  # down series are stored < 0
            "P_up_AFRR": [0.0, 2.0, 0.0, 0.0],
            "P_down_AFRR": [-1.0, 0.0, -1.0, 0.0],  # 1st period: down without down band
        },
        index=index,
    )
    # No battery: the 1st period (no PV) has 2 MW of band with nothing behind it.
    backing = developer.band_backing_check(data, battery_power=0.0)
    assert backing["status"] == "warn" and backing["value"].startswith("33%")
    assert "largest excess 2.00 MW" in backing["detail"]
    assert developer.band_backing_check(data, battery_power=2.0)["status"] == "ok"
    activation = developer.activation_check(data)
    assert activation["status"] == "warn" and "down 1 periods" in activation["detail"]
    assert "1 MWh" in activation["detail"]
    within = data.assign(P_down_AFRR=[0.0, 0.0, -1.0, 0.0])
    assert developer.activation_check(within)["status"] == "ok"
    no_band = data.drop(columns=[c for c in data if "AFRR" in c])
    assert developer.band_backing_check(no_band, 0.0) is None
    assert developer.activation_check(no_band) is None


def test_status_summary_names():
    text = str(status_summary(["warn", "ok", "ok"], {"warn": ("limiting", "limiting")}))
    assert "1 limiting" in text and "2 ok" in text


def _graph_heights(components) -> dict:
    """Container height (px) of every dcc.Graph in a layout, by id."""
    return {
        c.id: int(c.style["height"].removesuffix("px"))
        for c in _walk(components)
        if type(c).__name__ == "Graph"
    }


def test_figure_heights_match_their_cards(afrr_run, pv_run, tmp_path):
    """The svg must be as tall as its container, or legends and axis titles leak out."""
    # Visualization: static cards, figures from the callbacks.
    heights = _graph_heights(viz.layout())
    path = str(afrr_run.save(tmp_path / "c"))
    overview = viz.overview_outputs(path)
    figures = dict(
        zip(viz.OVERVIEW_GRAPHS, overview[3 : 3 + len(viz.OVERVIEW_GRAPHS)], strict=True)
    )
    figures |= dict(
        zip(
            ["visualization-assets", "visualization-markets"],
            viz.detail_outputs(path, None),
            strict=True,
        )
    )
    assert set(figures) == set(heights)
    for graph_id, figure in figures.items():
        assert figure.layout.height == heights[graph_id], graph_id
    # Cards built in the overview callback (revenue quality, plant sizing) carry their figure.
    built = [
        c
        for c in _walk([*overview[2], *overview[-4], *overview[-2]])
        if type(c).__name__ == "Graph"
    ]
    assert built
    for graph in built:
        assert graph.figure.layout.height == int(graph.style["height"][:-2]), graph.id


def test_new_generic_builders():
    counts = pd.DataFrame({"up": [1.0, 2.0], "down": [0.0, 3.0]}, index=[0.0, 100.0])
    fig = binned_histogram_figure(
        counts, bin_size=10, regions=[(100, 120)], x_suffix="%", x_range=(0, 120), marker=100
    )
    # Two series side by side within each 10 % bin.
    assert [trace.width for trace in fig.data] == [4.5, 4.5]
    assert list(fig.data[0].x) == [2.5, 102.5] and list(fig.data[1].x) == [7.5, 107.5]
    # Series keep their colors; the region beyond the limit is shaded behind the bars.
    assert fig.data[0].marker.color != "#ffa94d" and list(fig.layout.xaxis.range) == [0, 120]
    region, line = fig.layout.shapes
    assert (region.x0, region.x1, region.layer) == (100, 120, "below") and line.x0 == 100
    # Legend (2 series) and x title fit inside the figure: bottom margin reserves their space.
    titled = binned_histogram_figure(counts, bin_size=10, x_title="Band", height=340)
    assert titled.layout.margin.b >= 45 + 20 + 25 and titled.layout.legend.y < 0

    revenue = pd.Series(np.random.default_rng(0).normal(5000, 1000, 300))
    hist = histogram_figure(revenue, y_title="Days")
    assert hist.data[0].xbins.size == 250 and hist.layout.yaxis.dtick >= 1  # nice bins, int ticks
    assert "kpi-unit" not in str(kpi_tile("Missing", None, "%"))

    index = pd.date_range("2025-01-01", periods=3, freq="D")
    scatter = scatter_figure(
        pd.Series([1.0, 2.0, 3.0], index), pd.Series([1.0, 1.5, 4.0], index), diagonal=True
    )
    assert len(scatter.data) == 2 and scatter.data[0].customdata[0] == "01 Jan 2025"

    grouped = stacked_bar_figure(pd.DataFrame({"a": [1.0], "b": [2.0]}, index[:1]), grouped=True)
    assert grouped.layout.barmode == "group"
    card = chart_card("x-graph", "T", figure=grouped, footnote="note")
    assert "note" in str(card) and card.children[1].figure is grouped


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
    charts_hidden, empty_hidden, weeks, week, quality, quality_hidden, sizing, sizing_hidden = rest
    assert all(hasattr(f, "data") for f in figures) and len(notes) == len(viz.FOOTNOTES)
    assert heads[0] == "Revenue by day" and "per day" in heads[1]  # 8-hour run
    assert (charts_hidden, empty_hidden) == (False, True)  # it has a battery
    titles = [c.children for c in _walk(plant) if getattr(c, "className", None) == "spec-title"]
    assert titles == ["Grid connection", "Battery", "Markets", "Period"]  # no PV
    assert "Total revenue" in str(kpis) and "PV generation" not in str(kpis)
    # Checks: sizing questions, the grid access first; simulation checks live in Developer.
    assert "Grid access" in str(checks) and "Do the battery hours make sense?" in str(checks)
    assert "visualization-limits-monthly" in str(checks) and "Energy balance" not in str(checks)
    assert weeks and week == weeks[0]["value"]
    assert "Revenue quality" in str(quality) and not quality_hidden
    assert "Grid connection" in str(sizing) and not sizing_hidden

    empty = viz.overview_outputs(None)
    assert empty[-6:] == ([], None, [], True, [], True) and len(empty) == len(outputs)


def labels(rows: list[dict]) -> list[str]:
    return [row["label"] for row in rows]


def stat_labels(components) -> list[str]:
    """Labels of the stat rows of a layout, in order."""
    return [c.children for c in _walk(components) if getattr(c, "className", None) == "stat-label"]


def test_revenue_quality_blocks(afrr_run, pv_run, pv_only_run):
    rule = od.DAILY
    # Battery + aFRR, no PV: list (1/3) beside the spread chart (2/3), no PV capture row.
    results = indicators_of(afrr_run)
    rows = viz.quality_rows(results)
    assert labels(rows) == ["Battery realized spread", "Value per cycle", "Top 10 % days"]
    assert [row["primary"] for row in rows] == [True, False, False]
    assert "break-even" in rows[0]["sub"] and "discharge" not in rows[0]["sub"]
    (row,) = viz.revenue_quality(results, rule)
    assert "columns-start" in row.className
    assert row.style["--columns"] == "minmax(0, 1fr) minmax(0, 2fr)"
    assert graph_ids([row]) == {"visualization-spread-periods"}
    assert "Spread by day: available vs realized" in str(row)
    spread_card = row.children[1]
    assert spread_card.children[1].style["height"] == f"{viz.SPREAD_CHART_HEIGHT}px"

    # PV + battery: 4 rows; the PV row shows the export capture with storage.
    with_pv = viz.quality_rows(indicators_of(pv_run))
    assert len(with_pv) == 4 and "with storage · " in with_pv[2]["sub"]

    # PV only: no battery rows, no chart; the list takes the full width in two columns.
    pv_only = viz.revenue_quality(indicators_of(pv_only_run), rule)
    assert stat_labels(pv_only) == ["PV capture rate", "Top 10 % days"]
    assert "vs avg" in str(pv_only) and graph_ids(pv_only) == set()
    assert pv_only[0].children[1].style["--stat-columns"] == 2

    figure = viz.spread_period_figure(results["spread"].tables["daily"], rule, 4)
    assert trace_names(figure) == {"TB4 spread", "Realized spread"}


def test_spread_chart_drops_barely_covered_periods():
    days = pd.date_range("2025-09-10", "2025-11-01", freq="D")  # Sep 21/30, Oct full, Nov 1/30
    daily = pd.DataFrame(
        {
            "tbn_spread": 50.0,
            "discharge_energy": 1.0,
            "discharge_value": 100.0,
            "charge_energy": 1.0,
            "charge_value": 40.0,
        },
        index=days,
    )
    coverage = od.day_coverage(days, od.MONTHLY)
    assert coverage.round(2).tolist() == [0.7, 1.0, 0.03]
    figure = viz.spread_period_figure(daily, od.MONTHLY, 4)
    months = [pd.Timestamp(x).month for x in figure.data[0].x]
    assert months == [9, 10]  # November (1 day) dropped


def test_curves_differ():
    index = pd.Index(np.linspace(0, 100, 201), name="time_share")
    curve = pd.DataFrame({"net_percent": np.linspace(100, -100, 201)}, index=index)
    assert not od.curves_differ(curve, curve.copy())
    assert not od.curves_differ(curve, curve + 4.9)
    assert od.curves_differ(curve, curve + 5.0)
    assert od.curves_differ(curve, curve.iloc[:0])  # nothing to compare: keep both


def test_battery_duration():
    index = pd.date_range("2025-01-01", periods=4, freq="h")
    data = pd.DataFrame(
        {"P_storage_discharge": [10.0, 5.0, 0.0, 0.0], "P_storage_charge": [0.0, 0.0, 0.0, -10.0]},
        index=index,
    )
    curve = od.battery_duration(data, 10.0)
    assert len(curve) == 201 and curve.index.name == "time_share"
    assert curve["net_percent"].iloc[0] == 100.0 and curve["net_percent"].iloc[-1] == -100.0
    assert curve["net_percent"].is_monotonic_decreasing
    assert od.battery_duration(data, None).empty
    assert od.battery_duration(data[[]], 10.0).empty


def test_plant_sizing_blocks(afrr_run, pv_run, pv_only_run):
    results = indicators_of(afrr_run)
    data = afrr_run.timeseries_wide()
    curve = od.battery_duration(data, 2.5)  # 2.5 MW battery vs 10 MW grid: curves differ
    sizing = viz.plant_sizing(results, battery_power=2.5, battery_curve=curve)
    lists, charts = sizing
    grid_card, battery_card = lists.children
    assert "columns-start" in lists.className
    assert lists.style["--columns"] == "minmax(0, 1fr) minmax(0, 2fr)"
    assert battery_card.children[1].style["--stat-columns"] == 2
    assert grid_card.children[0].children[0].children == "Grid connection"
    assert battery_card.children[0].children[0].children == "Battery"
    grid_rows = viz.grid_rows(results["grid"].kpis)
    assert [(r["label"], r["primary"]) for r in grid_rows] == [
        ("Time at export limit", True),
        ("Time at import limit", False),
        ("POI capacity factor", False),
    ]
    battery_rows = viz.battery_rows(
        results["battery_usage"].kpis, results["afrr"].kpis, battery_power=2.5
    )
    assert [(r["label"], r["primary"]) for r in battery_rows] == [
        ("Time at power limit", True),
        ("Mean daily depth of discharge", False),
        ("Time at min SOC", False),
        ("Time at max SOC", False),
        ("Idle time", False),
        ("Avg aFRR band up", False),
        ("Avg aFRR band down", False),
    ]
    assert stat_labels([battery_card]) == labels(battery_rows)
    assert "≥ 99 % of 2.5 MW, charge or discharge" in str(sizing)
    # Without aFRR: 5 battery rows.
    assert len(viz.battery_rows(results["battery_usage"].kpis, None)) == 5

    # POI curve on the left, battery curve on the right, with the ±100 % lines.
    assert [c.children[1].id for c in charts.children] == [
        "visualization-grid-duration",
        "visualization-battery-duration",
    ]
    for chart in charts.children:
        figure = chart.children[1].figure
        assert sorted(shape.y0 for shape in figure.layout.shapes) == [-1.0, 1.0]

    # Battery curve identical to the POI curve (battery-only run, battery power = grid
    # limit): left out, the POI curve takes the full width; both lists stay.
    same = viz.plant_sizing(results, battery_curve=results["grid"].tables["duration"].copy())
    assert graph_ids(same) == {"visualization-grid-duration"}
    assert len(same[0].children) == 2 and len(same[1].children) == 1
    # PV run: the battery curve differs from the POI curve, both shown.
    pv_results = indicators_of(pv_run)
    pv_curve = od.battery_duration(pv_run.timeseries_wide(), 2.5)
    assert od.curves_differ(pv_curve, pv_results["grid"].tables["duration"])
    assert len(graph_ids(viz.plant_sizing(pv_results, battery_curve=pv_curve))) == 2

    # No battery nor aFRR: only the grid list and the POI curve (full width).
    pv_only = viz.plant_sizing(
        indicators_of(pv_only_run),
        battery_curve=od.battery_duration(pv_only_run.timeseries_wide(), None),
    )
    assert "Grid connection" in str(pv_only) and "Battery" not in str(pv_only)
    assert graph_ids(pv_only) == {"visualization-grid-duration"}
    assert len(pv_only[0].children) == 1 and len(pv_only[-1].children) == 1

    # Nothing available: empty (the section is hidden).
    unavailable = {name: replace(r, available=False) for name, r in results.items()}
    assert viz.plant_sizing(unavailable) == []
    assert viz.revenue_quality(unavailable, od.DAILY) == []


def test_indicator_checks():
    prices = {"export_at_nonpositive_mwh": 5.0, "price_market": "DayAhead"}
    (exports,) = od.indicator_checks(prices, 100.0)
    assert exports["status"] == "info"
    assert exports["detail"] == "5.0% of exported energy · DayAhead price"
    assert od.indicator_checks(None, None) == []


def test_line_figure_reference_lines():
    lines = line_figure(pd.DataFrame({"a": [0.5, -0.5]}), unit="%", reference_lines=(1.0, -1.0))
    assert len(lines.layout.shapes) == 2 and lines.layout.shapes[0].line.dash == "dot"


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


def test_sankey_nodes_fit_and_do_not_overlap():
    pad = 0.06
    # Standalone battery: one tall Grid import node must stay inside the plot.
    totals = {"Grid import": 100.0, "Battery": 100.0, "Grid export": 90.0, "Losses": 10.0}
    columns = {"Grid import": 0.0, "Battery": 0.5, "Grid export": (1.0, "out")}
    columns["Losses"] = (0.8, "out")
    positions = stacked_node_positions(totals, columns, pad)
    scale = (1 - pad) / 100  # the "out" stack (2 nodes) needs the most room
    for node, (_, y) in positions.items():
        half = totals[node] * scale / 2
        assert y - half >= -1e-9 and y + half <= 1 + 1e-9, node
    assert positions["Grid import"] == (0.0, pytest.approx(0.5))
    # Stacked nodes keep their own x, one below the other with the gap between them.
    export, losses = positions["Grid export"], positions["Losses"]
    assert losses[0] == 0.8 and losses[1] - export[1] == pytest.approx((100 * scale) / 2 + pad)
    assert stacked_node_positions({"A": 1.0}, {}, pad) == {}


def test_energy_sankey_positions_follow_the_flows(afrr_run, pv_run):
    for run in (afrr_run, pv_run):
        sankey = viz.energy_sankey_figure(run.timeseries_wide()).data[0]
        assert all(0 < y < 1 for y in sankey.node.y)
        labels = [label.split(" · ")[0] for label in sankey.node.label]
        ys = dict(zip(labels, sankey.node.y, strict=True))
        losses = sorted(ys[n] for n in viz.SINKS if n in ys)
        assert all(b - a >= 0.06 for a, b in zip(losses, losses[1:], strict=False))


def test_headline_numbers(afrr_run, pv_run):
    data = afrr_run.timeseries_wide()
    (row,) = viz.headline_blocks(afrr_run, data)
    left, energy_card = row.children
    hero, markets_card = left.children
    assert "columns-start" in row.className and row.style["--columns"].endswith("1fr)")
    assert "Energy" in str(energy_card)
    items = viz.hero_items(afrr_run)
    assert [i["label"] for i in items] == ["Total revenue", "Revenue per year", "Equivalent cycles"]
    assert items[0]["primary"] and "extrapolated" in items[1]["sub"]
    assert "per day" in items[2]["sub"]
    total = format_compact(afrr_run.kpis["revenue_total"], "€", 0)[0]  # 3 digits, as the rest
    assert f"children=['{total}'" in str(hero)

    # Markets table: one row per market; captured price vs market average in the cell.
    assert viz.market_columns(data)[:3] == ["Market", "Revenue", "Share"]
    assert any("sell" in c for c in viz.market_columns(data))
    rows = {r["label"]: r for r in viz.market_rows(afrr_run.kpis, data)}
    assert set(rows) == {"DayAhead", "AFRR"}
    expected = data["B_sell_DayAhead"].sum() / data["E_sell_DayAhead"].sum()
    sell = viz.market_columns(data).index("Avg sell price · €/MWh") - 1
    cell = rows["DayAhead"]["cells"][sell]
    assert cell["value"] == f"{expected:,.1f}" and "vs mkt" in cell["sub"]
    assert cell["status"] in {"ok", "warn"}
    assert rows["AFRR"]["cells"][sell] is None  # no energy traded: "-"
    assert rows["DayAhead"]["color"] == market_color("DayAhead")
    assert "data-table" in str(markets_card)

    energy = labels(viz.energy_rows(afrr_run, data))
    assert "Battery losses" in energy and "PV generation" not in energy
    assert "Equivalent cycles" not in energy  # in the hero strip
    pv_energy = labels(viz.energy_rows(pv_run, pv_run.timeseries_wide()))
    assert "PV generation" in pv_energy and "Curtailment" in pv_energy

    no_battery = replace(afrr_run, inputs={**afrr_run.inputs, "batteries": []})
    assert len(viz.hero_items(no_battery)) == 2
    assert "Battery losses" not in labels(viz.energy_rows(no_battery, data))
    assert "Daily cycle limit" not in str(od.run_checks(no_battery.inputs, no_battery.kpis, data))


def test_compact_components():
    hero = hero_strip(
        [
            {
                "label": "A",
                "value": 12_345_678,
                "unit": "€",
                "decimals": 0,
                "compact": True,
                "primary": True,
            },
            {"label": "B", "value": None, "unit": "€", "sub": "note"},
        ]
    )
    assert "hero-strip" in hero.className and len(hero.children) == 2
    assert "hero-primary" in hero.children[0].className
    assert hero.children[0].children[1].title == "12,345,678 €"  # full value in the tooltip
    assert "M€" in str(hero) and "note" in str(hero)

    rows = [
        stat_row("Exported", 1234.0, "MWh", 0, sub="sub text", primary=True),
        stat_row("Ratio", None, "%"),
        stat_row("Status", "3 days", status="warn"),
    ]
    stats = stat_list("Energy", rows, hint="h", columns=2, footnote="foot")
    rendered = [c for c in _walk([stats]) if "stat-row" in str(getattr(c, "className", ""))]
    assert [r.className for r in rendered] == [
        "stat-row stat-primary",
        "stat-row",
        "stat-row stat-warn",
    ]
    assert "1,234" in str(stats) and "foot" in str(stats) and "-" in str(rendered[1])
    assert stats.children[1].style["--stat-columns"] == 2
    # Two columns are filled column by column: ceil(3 / 2) = 2 rows per column.
    assert "stat-list-flow" in stats.children[1].className
    assert stats.children[1].style["--stat-rows"] == 2
    single = stat_list("One", rows)
    assert single.children[1].className == "stat-list"

    checks = check_list(
        [
            {"label": "A", "value": "fine", "status": "ok", "detail": "d"},
            {"label": "B", "value": None, "status": "warn"},
        ]
    )
    assert stat_labels([checks]) == ["B", "A"]  # warnings first
    summary = checks.children[0]
    assert summary.className == "status-summary"
    counts = [c for c in summary.children if "status-count" in c.className]
    assert [(c.children, c.className) for c in counts] == [
        ("1 warning", "status-count status-warn"),
        ("1 ok", "status-count status-ok"),
    ]
    plural = status_summary(["warn", "warn", "info", "ok", "ok", "ok"])
    assert [c.children for c in plural.children if "status-count" in c.className] == [
        "2 warnings",
        "3 ok",
        "1 info",
    ]
    assert "status-summary" not in str(check_list([], summary=False))

    table = data_table(
        ["Market", "Revenue", "Price"],
        [
            {
                "label": "X",
                "color": "#fff",
                "cells": ["1 M€", {"value": "50.0", "sub": "+2", "status": "ok"}],
            },
            {"label": "Y", "cells": [None, None]},
        ],
        title="Markets",
    )
    text = str(table)
    assert "table-swatch" in text and "table-sub table-ok" in text
    cells = [c for c in _walk([table]) if getattr(c, "className", None) == "table-value"]
    assert [c.children for c in cells] == ["1 M€", "50.0", "-", "-"]


def test_grid_columns_avoid_orphans():
    assert [viz.grid_columns(n) for n in (3, 4, 6, 8, 9, 12)] == [3, 4, 3, 4, 3, 4]


def rows_of(group: dict) -> dict[str, str]:
    return {row["label"]: row["value"] for row in group["rows"]}


def test_plant_groups(pv_run):
    inputs = {
        "system": {"capacity_sell": 5, "capacity_buy": 5, "efficiency": 0.98},
        "batteries": [
            {
                "capacity": 20,
                "rte": 0.91,
                "c_rate": 0.25,
                "dod": 1,
                "soc_max": 1,
                "soc_initial": 0,
                "max_cycles_day": 2,
                "max_cycles_day_monthly_avg": None,
                "max_cycles_day_yearly_avg": 1.5,
                "max_power_output": 5.0,
                "min_power_output": 0.1,
                "name": "bess001",
            }
        ],
        "generators": [
            {
                "peak_power": 6,
                "latitude": 41,
                "longitude": -0.5,
                "tracker": None,
                "tilt": 41,
                "azimuth": 180,
                "losses": 0.85,
                "name": "PV6",
            }
        ],
        "markets": [
            {"type": "DayAhead", "params": {}},
            {"type": "AFRR", "params": {"act": "bin_max", "max_up": 2.5, "max_down": 2.5}},
        ],
        "period": {
            "start": "2026-01-01T00:00:00+00:00",
            "end": "2026-11-01T23:45:00+00:00",
            "n_periods": 29280,
            "dt_hours": [0.25],
        },
    }
    groups = viz.plant_groups(inputs)
    assert [g["title"] for g in groups] == ["Grid connection", "PV", "Battery", "Markets", "Period"]
    grid, pv, battery, markets, period = map(rows_of, groups)
    assert grid == {"Export capacity": "5 MW", "Import capacity": "5 MW", "Efficiency": "98%"}
    assert pv == {
        "Peak power": "6 MW",
        "Location": "41.0° N · 0.5° W",
        "Orientation": "tilt 41° · azimuth 180°",
        "Tracker": "fixed",
        "Performance factor": "85%",
    }
    assert groups[1]["subtitle"] == "PV6" and groups[2]["subtitle"] == "bess001"
    assert battery == {
        "Power": "5 MW · min 0.1",
        "Capacity": "20 MWh",
        "Duration": "4 h",
        "RTE": "91%",
        "Usable SOC": "0–100 %",
        "Initial SOC": "0%",
        "Max cycles": "2 /day",
        "Yearly avg limit": "1.5 /day",
    }
    assert markets == {"DayAhead": "energy", "AFRR": "band ↑2.5 / ↓2.5 MW", "activation": "bin_max"}
    market_rows = groups[3]["rows"]
    assert market_rows[1]["color"] == market_color("AFRR") and market_rows[2]["indent"]
    assert period == {"Dates": "2026-01-01 → 2026-11-01", "Days": "305 d"}
    assert "Resolution" not in str(groups)

    # Several batteries: one group each; no PV / battery: groups absent; missing values skipped.
    two = viz.plant_groups({**inputs, "batteries": inputs["batteries"] * 2, "generators": []})
    assert [g["title"] for g in two].count("Battery") == 2 and "PV" not in str(two)
    bare = viz.plant_groups({"batteries": [{"capacity": 4, "c_rate": 0.5}]})
    assert [g["title"] for g in bare] == ["Grid connection", "Battery", "Period"]
    assert rows_of(bare[1]) == {"Power": "2 MW", "Capacity": "4 MWh", "Duration": "2 h"}
    assert rows_of(bare[0])["Export capacity"] is None  # shown as "-"

    # Missing rating: observed maximum from the data.
    data = pd.DataFrame({"P_generation": [0.0, 12.34, 3.0]})
    observed = viz.plant_groups({"generators": [{"peak_power": None}]}, data)
    assert rows_of(observed[1]) == {"Max output (observed)": "12.3 MW"}

    card = spec_card(viz.plant_groups(pv_run.inputs, pv_run.timeseries_wide()))
    assert "spec-card" in card.className


def test_spec_card():
    card = spec_card(
        [
            {
                "title": "A",
                "color": "#fff",
                "subtitle": "name",
                "rows": [
                    stat_row("Power", 12_345_678, "€", 0, compact=True),
                    stat_row("Missing", None),
                    stat_row("Market", "energy", title="tip") | {"color": "#000"},
                ],
            },
            {"title": "B", "rows": []},
        ],
        id="x-spec",
    )
    assert card.id == "x-spec" and len(card.children) == 2
    group = card.children[0]
    head, *rows = group.children
    assert [c.className for c in head.children if c is not None] == [
        "spec-swatch",
        "spec-title",
        "spec-subtitle",
    ]
    values = [row.children[1].children for row in rows]
    assert values == ["12.3 M€", "-", "energy"]
    assert rows[0].title == "Power: 12,345,678 €" and rows[2].title == "tip"
    indented = spec_card([{"title": "M", "rows": [stat_row("act", "x") | {"indent": True}]}])
    assert "spec-row-indent" in indented.children[0].children[1].className
    assert "spec-swatch" in str(rows[2]) and "spec-swatch" not in str(rows[0])


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
    # No rows (e.g. a run whose assets never produce): a message instead of an error.
    empty = rows_figure([], height=300)
    assert not empty.data and empty.layout.annotations and empty.layout.height == 300


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
    assert format_compact(-1e-12, "MWh", decimals=0) == ("0", "MWh")  # solver noise, no "-0"
    assert format_compact(-0.4, "MWh", decimals=1) == ("-0.4", "MWh")


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
