"""Visualization tab: overview of one saved run.

Sections: plant, headline numbers, checks, economics, energy flows, battery and a 7-day
operation detail. Only aggregated data (totals, per month/week/day, month x hour) is sent to
the browser, except in the detail. Computations live in ``overview_data.py``; this module turns
them into generic components and figures. Notes: ``.claude/dashboard/visualization.md``.
"""

import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, dcc

from ...visualization.styles import FLOW_COLORS, NODE_COLORS, STATUS_COLORS, market_color
from ..components import (
    EMPTY_FIGURE,
    chart_card,
    check_tile,
    columns,
    field,
    format_dt,
    info_row,
    info_tile,
    kpi_grid,
    kpi_group,
    kpi_tile,
    load_run,
    load_timeseries,
    note,
    section,
    stack,
)
from ..figures import (
    area_figure,
    hbar_figure,
    heatmap_figure,
    histogram_figure,
    line_figure,
    rows_figure,
    sankey_figure,
    stacked_bar_figure,
)
from . import overview_data as od
from .base import Tab

BAND_PREFIX = "Band_"
MARKET_OPERATION_PREFIXES = ("P_sell_", "P_buy_", "P_up_", "P_down_", "Band_up_", "Band_down_")

# Sankey nodes: label -> (color key, (x, y) centre position, 0-1 from the top left).
# Sources on the left (PV, small Grid import just below it), Battery in the middle, Grid export
# on the right. Loss and curtailment nodes get their own column (x=0.8) at the bottom, so they
# are not pushed under the tall Grid export node: their centres are 0.08 apart (~38 px on the
# 480 px plot area), more than their heights plus the node padding, so labels do not overlap.
# Labels of these right-hand nodes are drawn on their left (plotly does so for the last layer).
NODES = {
    "PV": ("pv", (0.01, 0.45)),
    "Grid import": ("grid", (0.01, 0.94)),
    "Battery": ("battery", (0.5, 0.55)),
    "Grid export": ("grid", (0.97, 0.42)),
    "System losses": ("losses", (0.8, 0.80)),
    "Curtailment": ("curtailment", (0.8, 0.88)),
    "Battery losses": ("losses", (0.8, 0.96)),
}
SINKS = {"Curtailment", "Battery losses", "System losses"}
SANKEY_HEIGHT = 520

OVERVIEW_GRAPHS = [
    "visualization-revenue",
    "visualization-revenue-streams",
    "visualization-energy-sankey",
    "visualization-energy-markets",
    "visualization-flows",
    "visualization-soc-heatmap",
    "visualization-daily-cycles",
]
FOOTNOTES = [
    "visualization-revenue-streams-note",
    "visualization-energy-markets-note",
    "visualization-daily-cycles-note",
]
# Cards whose title and hint follow the run (aggregation period).
DYNAMIC_HEADS = ["visualization-revenue", "visualization-flows", "visualization-soc-heatmap"]


def layout() -> list:
    week = dcc.Dropdown(id="visualization-week", options=[], value=None, clearable=False)
    return [
        section("Plant", info_row([], id="visualization-plant"), hint="Simulation inputs"),
        section("Headline numbers", stack(id="visualization-kpis"), hint="Whole period"),
        section(
            "Checks",
            stack(id="visualization-checks"),
            hint="Does the simulation make sense?",
        ),
        section(
            "Economics",
            columns(
                [
                    chart_card(
                        "visualization-revenue",
                        "Revenue by month",
                        "€ per month, by market",
                        380,
                        dynamic_head=True,
                    ),
                    chart_card(
                        "visualization-revenue-streams",
                        "Revenue by stream",
                        "€ over the period",
                        380,
                        footnote_id="visualization-revenue-streams-note",
                    ),
                ],
                widths=[2, 1],
            ),
        ),
        section(
            "Energy flows",
            [
                columns(
                    [
                        chart_card(
                            "visualization-energy-sankey",
                            "Energy flows",
                            "MWh over the period",
                            SANKEY_HEIGHT,
                        ),
                        chart_card(
                            "visualization-energy-markets",
                            "Energy by market",
                            "MWh over the period · sold +, bought −",
                            SANKEY_HEIGHT,
                            footnote_id="visualization-energy-markets-note",
                        ),
                    ]
                ),
                chart_card(
                    "visualization-flows",
                    "Energy flows by month",
                    "MWh per month · export ↑ by source, battery charge ↓ by source",
                    340,
                    dynamic_head=True,
                ),
            ],
        ),
        section(
            "Battery",
            [
                columns(
                    [
                        chart_card(
                            "visualization-soc-heatmap",
                            "Battery state of charge",
                            "mean SOC by month and hour",
                            340,
                            dynamic_head=True,
                        ),
                        chart_card(
                            "visualization-daily-cycles",
                            "Daily cycles distribution",
                            "days per cycles/day bin",
                            340,
                            footnote_id="visualization-daily-cycles-note",
                        ),
                    ],
                    id="visualization-battery-charts",
                ),
                note("No battery in this run.", id="visualization-battery-empty", hidden=True),
            ],
        ),
        section(
            "Operation detail",
            [
                field("Week", week),
                chart_card(
                    "visualization-assets",
                    "Assets",
                    "Generation, storage and power at the POI · MW",
                    720,
                ),
                chart_card(
                    "visualization-markets",
                    "Markets",
                    "Prices and operation per market · bands as dashed lines",
                    620,
                ),
            ],
            hint="Full resolution, 7 days",
        ),
    ]


def register(app, run_input) -> None:
    @app.callback(
        Output("visualization-plant", "children"),
        Output("visualization-kpis", "children"),
        Output("visualization-checks", "children"),
        *[Output(graph_id, "figure") for graph_id in OVERVIEW_GRAPHS],
        *[Output(note_id, "children") for note_id in FOOTNOTES],
        *[
            Output(f"{card_id}-{part}", "children")
            for card_id in DYNAMIC_HEADS
            for part in ("title", "hint")
        ],
        Output("visualization-battery-charts", "hidden"),
        Output("visualization-battery-empty", "hidden"),
        Output("visualization-week", "options"),
        Output("visualization-week", "value"),
        run_input,
    )
    def show_overview(path):
        return overview_outputs(path)

    @app.callback(
        Output("visualization-assets", "figure"),
        Output("visualization-markets", "figure"),
        run_input,
        Input("visualization-week", "value"),
    )
    def show_detail(path, week):
        return detail_outputs(path, week)


def overview_outputs(path) -> tuple:
    """Outputs of the overview callback, in the order of its ``Output`` list."""
    if not path:
        return (
            *([], [], []),
            *[EMPTY_FIGURE] * len(OVERVIEW_GRAPHS),
            *[""] * len(FOOTNOTES),
            *[no_head for _ in DYNAMIC_HEADS for no_head in ("", "")],
            False,
            True,
            [],
            None,
        )
    run = load_run(path)
    data = load_timeseries(path)
    rule = od.period_rule(data.index)
    soc_by_month = rule is od.MONTHLY
    battery = od.has_battery(run.inputs)
    weeks = od.week_options(data.index)
    streams, streams_note = revenue_streams_view(data, run.kpis.get("revenue_total"))
    by_market, by_market_note = energy_by_market_view(data)
    cycles, cycles_note = daily_cycles_view(data, run.inputs)
    soc_unit = "month" if soc_by_month else "day"
    heads = [
        f"Revenue by {rule.noun}",
        f"€ per {rule.noun}, by market",
        f"Energy flows by {rule.noun}",
        f"MWh per {rule.noun} · export ↑ by source, battery charge ↓ by source",
        "Battery state of charge",
        f"mean SOC by {soc_unit} and hour",
    ]
    return (
        plant_tiles(run.inputs, data),
        headline_kpis(run, data),
        check_tiles(od.run_checks(run.inputs, run.kpis, data)),
        period_revenue_figure(data, rule),
        streams,
        energy_sankey_figure(data),
        by_market,
        period_flows_figure(data, rule),
        soc_heatmap_figure(data, by_month=soc_by_month),
        cycles,
        streams_note,
        by_market_note,
        cycles_note,
        *heads,
        not battery,
        battery,
        weeks,
        weeks[0]["value"] if weeks else None,
    )


def detail_outputs(path, week) -> tuple:
    """Outputs of the detail callback: assets and markets charts of the chosen 7-day window."""
    if not path:
        return EMPTY_FIGURE, EMPTY_FIGURE
    window = od.time_window(load_timeseries(path), week)
    labels = od.series_labels(window.columns)
    return (
        assets_figure_from(window, labels=labels),
        markets_figure_from(window, bands_as_lines=True, labels=labels),
    )


# ---------- Plant, headline numbers, checks ----------


def plant_tiles(inputs: dict, data: pd.DataFrame | None = None) -> list:
    """Info tiles describing the plant and the simulation setup (from ``run.inputs``).

    PV tiles only with PV and battery tiles only with a battery. A missing rating is replaced
    by the observed maximum in ``data`` when there is one (e.g. "PV max output").
    """
    data = data if data is not None else pd.DataFrame()
    batteries = inputs.get("batteries", [])
    system = inputs.get("system", {})
    period = inputs.get("period", {})
    ratings = od.plant_ratings(inputs)
    power, capacity = ratings["battery_power"], ratings["battery_capacity"]
    days = od.period_days(period)
    span = (
        f"{period['start'][:10]} → {period['end'][:10]} · {days:,.0f} d"
        if period.get("start") and period.get("end") and days
        else None
    )
    weighted_rte = [
        (b["rte"], b["capacity"]) for b in batteries if b.get("rte") and b.get("capacity")
    ]
    rte = (
        sum(r * c for r, c in weighted_rte) / sum(c for _, c in weighted_rte)
        if weighted_rte
        else None
    )
    markets = ", ".join(m["type"] for m in inputs.get("markets", [])) or None
    tiles = []
    if od.has_pv(inputs, data):
        tiles.append(
            _rated_or_observed(
                "PV peak power", ratings["pv_peak"], "PV max output", data, "P_generation"
            )
        )
    if od.has_battery(inputs):
        tiles += [
            _rated_or_observed(
                "Battery power", power, "Battery max output", data, "P_storage_discharge"
            ),
            info_tile("Battery capacity", _fmt(capacity, "MWh")),
            info_tile("Duration", _fmt(capacity / power if capacity and power else None, "h")),
            info_tile("RTE", f"{rte:.0%}" if rte else None),
        ]
    tiles += [
        _rated_or_observed(
            "Grid export", system.get("capacity_sell"), "Grid max export", data, "P_system_export"
        ),
        _rated_or_observed(
            "Grid import", system.get("capacity_buy"), "Grid max import", data, "P_system_import"
        ),
        info_tile("Period", span),
        info_tile("Resolution", format_dt(period.get("dt_hours"))),
        info_tile("Markets", markets),
    ]
    return tiles


def headline_kpis(run, data: pd.DataFrame) -> list:
    """KPI groups: economics (with captured prices) and energy (PV / battery tiles only when
    the run has them)."""
    kpis = run.kpis
    total = kpis.get("revenue_total")
    days = od.period_days(run.inputs.get("period", {}))
    years = days / 365.25 if days else None
    per_year = total / years if total is not None and years else None
    power = od.plant_ratings(run.inputs)["battery_power"]
    per_year_sub = []
    if per_year is not None and power:
        per_year_sub.append(f"{per_year / power / 1000:,.0f} k€/MW·year of battery")
    if days and days < 365:
        per_year_sub.append(f"extrapolated from {days:,.0f} d")

    economics = [
        kpi_tile("Total revenue", total, "€", 0, primary=True, compact=True),
        kpi_tile(
            "Revenue per year", per_year, "€", 0, compact=True, sub=" · ".join(per_year_sub) or None
        ),
    ]
    for market, value in kpis.get("revenue_by_market", {}).items():
        share = f"{value / total:.0%} of total" if value is not None and total else None
        economics.append(kpi_tile(f"Revenue {market}", value, "€", 0, sub=share, compact=True))
    economics += captured_price_tiles(data)

    pv = od.energy(data, "P_generation") if od.has_pv(run.inputs, data) else None
    charged = kpis.get("energy_charged_MWh")
    discharged = kpis.get("energy_discharged_MWh")
    losses = charged - discharged if charged is not None and discharged is not None else None
    cycles = kpis.get("equivalent_cycles")
    excess = kpis.get("excess_energy_MWh")
    energy = []
    if pv is not None:
        energy.append(kpi_tile("PV generation", pv, "MWh", 0, compact=True))
    energy += [
        kpi_tile("Energy exported", kpis.get("energy_exported_MWh"), "MWh", 0, compact=True),
        kpi_tile("Energy imported", kpis.get("energy_imported_MWh"), "MWh", 0, compact=True),
    ]
    if od.has_battery(run.inputs):
        energy += [
            kpi_tile("Energy charged", charged, "MWh", 0, compact=True),
            kpi_tile("Energy discharged", discharged, "MWh", 0, compact=True),
            kpi_tile(
                "Battery losses",
                losses,
                "MWh",
                0,
                compact=True,
                sub=f"{losses / charged:.1%} of charged"
                if losses is not None and charged
                else None,
            ),
            kpi_tile(
                "Equivalent cycles",
                cycles,
                "",
                0 if cycles is not None and cycles >= 100 else 1,
                sub=f"{cycles / days:.2f} per day" if cycles is not None and days else None,
            ),
        ]
    if pv is not None:
        energy.append(
            kpi_tile(
                "Curtailment",
                excess,
                "MWh",
                0,
                compact=True,
                sub=f"{excess / pv:.1%} of PV generation" if excess is not None and pv else None,
            )
        )
    return [
        kpi_group("Economics", economics, columns=grid_columns(len(economics))),
        kpi_group("Energy", energy, columns=grid_columns(len(energy))),
    ]


def captured_price_tiles(data: pd.DataFrame) -> list:
    """KPI tiles of the captured prices, with the market average as sub-line."""
    return [
        kpi_tile(
            f"{item['market']} · avg {item['direction'].replace('_', ' ')} price",
            item["price"],
            "€/MWh",
            1,
            sub=f"market avg {item['market_avg']:,.1f} €/MWh"
            if item["market_avg"] is not None
            else None,
        )
        for item in od.captured_prices(data)
    ]


def check_tiles(checks: list[dict]) -> list:
    """Check tiles in a grid without orphan tiles when possible."""
    tiles = [check_tile(**check) for check in checks]
    return [kpi_grid(tiles, columns=grid_columns(len(tiles)))]


def grid_columns(n: int) -> int:
    """Columns for ``n`` tiles without an orphan tile on the last row when possible."""
    for candidate in (4, 3):
        if n % candidate == 0:
            return candidate
    return n if n <= 5 else 4


# ---------- Economics ----------


def period_revenue_figure(data: pd.DataFrame, rule: od.PeriodRule | None = None) -> go.Figure:
    """Revenue per period (month/week/day) and market (sum of B_benefit_*), stacked bars."""
    rule = rule or od.period_rule(data.index)
    revenue = od.aggregate(od.by_market(data, od.REVENUE_PREFIX), rule)
    colors = {market: market_color(market) for market in revenue.columns}
    return stacked_bar_figure(
        revenue,
        colors=colors,
        unit="€",
        x_format=rule.x_format,
        partial=od.partial_periods(data.index, rule),
        height=380,
    )


def revenue_streams_view(data: pd.DataFrame, total_revenue=None) -> tuple[go.Figure, str]:
    """Total per revenue stream; streams below 0.5% of the total revenue are hidden and listed
    in the returned footnote."""
    totals, market_of = od.revenue_streams(data)
    if total_revenue is None:
        total_revenue = float(od.by_market(data, od.REVENUE_PREFIX).sum().sum())
    shown, footnote = od.hide_small(totals, abs(total_revenue), "of total revenue")
    colors = {label: market_color(market) for label, market in market_of.items()}
    figure = hbar_figure(shown, colors=colors, unit="€", value_labels=True, height=380)
    return figure, footnote


# ---------- Energy flows ----------


def energy_sankey_figure(data: pd.DataFrame) -> go.Figure:
    """Total energy (MWh) between PV, grid and battery, balanced at every node."""
    links, _ = od.sankey_links(data)
    node_colors = {label: NODE_COLORS[key] for label, (key, _) in NODES.items()}
    # Links take their source color, except those into loss/curtailment nodes (target color).
    link_colors = [node_colors[t] if t in SINKS else node_colors[s] for s, t, _ in links]
    return sankey_figure(
        list(NODES),
        links,
        node_colors=node_colors,
        link_colors=link_colors,
        unit="MWh",
        show_totals=True,
        positions={label: position for label, (_, position) in NODES.items()},
        height=SANKEY_HEIGHT,
    )


def energy_by_market_view(data: pd.DataFrame) -> tuple[go.Figure, str]:
    """Total energy per market and direction, signed; entries below 0.5% of the largest one
    are hidden and listed in the returned footnote."""
    totals, market_of = od.market_energy(data)
    largest = float(totals.abs().max()) if len(totals) else 0.0
    shown, footnote = od.hide_small(totals, largest, "of the largest")
    colors = {label: market_color(market) for label, market in market_of.items()}
    figure = hbar_figure(shown, colors=colors, unit="MWh", value_labels=True, height=SANKEY_HEIGHT)
    return figure, footnote


def period_flows_figure(data: pd.DataFrame, rule: od.PeriodRule | None = None) -> go.Figure:
    """Energy per period: exported to the grid by source (up), charged into the battery by
    source (down)."""
    rule = rule or od.period_rule(data.index)
    flows = od.aggregate(od.flows_frame(data), rule)
    flows = flows.loc[:, (flows.abs() > 1e-9).any()]  # e.g. no PV flows without PV
    colors = {label: FLOW_COLORS[key] for label, _, key, _ in od.FLOWS}
    return stacked_bar_figure(
        flows,
        colors=colors,
        unit="MWh",
        x_format=rule.x_format,
        partial=od.partial_periods(data.index, rule),
        height=340,
    )


# ---------- Battery ----------


def soc_heatmap_figure(data: pd.DataFrame, by_month: bool = True) -> go.Figure:
    """Mean SOC of all batteries (0-1) as a heatmap: month (or day) on x, hour of day on y."""
    rule = od.MONTHLY if by_month else od.DAILY
    return heatmap_figure(
        od.soc_grid(data, by_month),
        zmin=0,
        zmax=1,
        colorbar_title="SOC",
        colorbar_format=".0%",
        hovertemplate=f"%{{x|{rule.x_format}}} · %{{y}}:00<br>SOC %{{z:.0%}}<extra></extra>",
        y_title="Hour of day",
        y_dtick=3,
        x_format=rule.x_format,
        height=340,
    )


def daily_cycles_view(data: pd.DataFrame, inputs: dict) -> tuple[go.Figure, str]:
    """Histogram of equivalent cycles per day, and a footnote with the days above the limit.

    The battery ``max_cycles_day`` limit, when set, is drawn as a vertical marker and the days
    above it in the warning color.
    """
    cycles = od.daily_cycles(data, inputs)
    limit = od.cycle_limit(inputs)
    figure = histogram_figure(
        cycles,
        bin_size=0.1,
        x_title="Equivalent cycles per day",
        y_title="Days",
        color=NODE_COLORS["battery"],
        marker=limit,
        marker_label=f"max {limit:g}/day" if limit else None,
        highlight_above=limit,
        highlight_color=STATUS_COLORS["warn"],
        height=340,
    )
    footnote = ""
    if limit is not None and len(cycles):
        footnote = f"{int((cycles > limit + 1e-9).sum())} days above the limit"
    return figure, footnote


# ---------- Operation detail ----------


def assets_figure_from(data: pd.DataFrame, labels: dict[str, str] | None = None) -> go.Figure:
    """Generation, storage and point-of-interconnection power (rows sharing the x axis).

    Storage and POI rows share their y range; generation (≥ 0) keeps its own. Rows without
    data (e.g. no PV) are left out. ``labels`` renames the series in legends.
    """
    rows = [
        ("Generation modules power production", ["P_generation"], False),
        ("Storage modules power", ["P_storage_charge", "P_storage_discharge"], True),
        ("Power output at POI", ["P_system_export", "P_system_import"], True),
    ]
    kept = [
        (title, frame, shared)
        for title, variables, shared in rows
        if not (frame := _present(data, variables)).empty and (frame.abs() > 1e-9).any().any()
    ]
    shared_rows = [i for i, (_, _, shared) in enumerate(kept, start=1) if shared]
    return rows_figure(
        [area_figure(frame, y_title="MW", labels=labels, unit="MW") for _, frame, _ in kept],
        subplot_titles=[title for title, _, _ in kept],
        shared_y=shared_rows if len(shared_rows) > 1 else False,
        height=720,
    )


def markets_figure_from(
    data: pd.DataFrame, bands_as_lines: bool = False, labels: dict[str, str] | None = None
) -> go.Figure:
    """Market prices and stacked market operation (2 rows, shared x axis).

    ``bands_as_lines=True`` draws the offered bands (``Band_*``) as dashed lines instead of
    stacked areas, so they do not hide the energy traded in the markets. ``labels`` renames the
    series in legends.
    """
    prices = line_figure(
        _with_prefix(data, (od.PRICE_PREFIX,)), y_title="€/MWh", labels=labels, unit="€/MWh"
    )
    operation_data = _with_prefix(data, MARKET_OPERATION_PREFIXES)
    bands = (
        [c for c in operation_data.columns if c.startswith(BAND_PREFIX)] if bands_as_lines else []
    )
    operation = area_figure(
        operation_data, stacked=True, y_title="MW", line_columns=bands, labels=labels, unit="MW"
    )
    return rows_figure(
        [prices, operation],
        subplot_titles=["Market prices", "Market operation"],
        vertical_spacing=0.1,
        height=620,
    )


# ---------- Helpers ----------


def _rated_or_observed(label, rated, observed_label, data, variable):
    if rated is not None or data is None or variable not in data:
        return info_tile(label, _fmt(rated, "MW"))
    observed = float(data[variable].abs().max())
    return info_tile(observed_label, _fmt(round(observed, 1), "MW"))


def _present(data: pd.DataFrame, variables: list[str]) -> pd.DataFrame:
    return data[[variable for variable in variables if variable in data]]


def _with_prefix(data: pd.DataFrame, prefixes: tuple[str, ...]) -> pd.DataFrame:
    return data[[column for column in data.columns if column.startswith(prefixes)]]


def _fmt(value, unit: str) -> str | None:
    return None if value is None else f"{value:,.4g} {unit}"


TAB = Tab(
    id="visualization",
    label="Visualization",
    description="Overview of a run",
    layout=layout,
    register=register,
)
