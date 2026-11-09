"""Visualization tab: overview of one saved run.

Sections: plant, headline numbers, checks (sizing questions, ``sizing_checks.py``), economics (with revenue quality), plant sizing,
energy flows, battery and a 7-day operation detail. Derived indicators come from
``powersim.runs.indicators`` (computed once per run in the overview callback). Only aggregated data (totals, per month/week/day, month x hour) is sent to
the browser, except in the detail. Computations live in ``overview_data.py``; this module turns
them into generic components and figures. Notes: ``.claude/dashboard/visualization.md``.
"""

import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, dcc

from ...runs._series import battery_power
from ...runs.indicators import Indicator, all_indicators
from ...visualization.styles import FLOW_COLORS, NODE_COLORS, STATUS_COLORS, market_color
from ..components import (
    EMPTY_FIGURE,
    chart_card,
    columns,
    data_table,
    field,
    hero_strip,
    load_run,
    load_timeseries,
    note,
    section,
    spec_card,
    stack,
    stat_list,
    stat_row,
)
from ..figures import (
    area_figure,
    hbar_figure,
    heatmap_figure,
    histogram_figure,
    line_figure,
    message_figure,
    rows_figure,
    sankey_figure,
    stacked_bar_figure,
)
from ..formatting import compact_text
from . import overview_data as od
from . import sizing_checks
from .base import Tab

BAND_PREFIX = "Band_"
MARKET_OPERATION_PREFIXES = ("P_sell_", "P_buy_", "P_up_", "P_down_", "Band_up_", "Band_down_")

# Sankey nodes: label -> (color key, column). Sources on the left (PV above Grid import),
# Battery in the middle, Grid export on the right. Loss and curtailment nodes get their own x
# (0.8) so they are not pushed under the tall Grid export node, but are stacked with it ("out"),
# below it. y is computed from the flows (``sankey_figure(columns=...)``) so every column fits
# whatever the node sizes (a standalone battery has one tall Grid import node), with a 30 px gap
# that keeps the labels of small nodes apart. Labels of the right-hand nodes are drawn on their
# left (plotly does so for the last layer).
NODES = {
    "PV": ("pv", 0.01),
    "Grid import": ("grid", 0.01),
    "Battery": ("battery", 0.5),
    "Grid export": ("grid", (0.97, "out")),
    "System losses": ("losses", (0.8, "out")),
    "Curtailment": ("curtailment", (0.8, "out")),
    "Battery losses": ("losses", (0.8, "out")),
}
SINKS = {"Curtailment", "Battery losses", "System losses"}
SANKEY_HEIGHT = 520
INDICATOR_CHART_HEIGHT = 340
SPREAD_CHART_HEIGHT = 260
MIN_PERIOD_COVERAGE = 0.25  # averages of periods covered less than this are dropped
MARKET_PARAM_LABELS = {"act": "activation"}  # readable names of market parameters
REFERENCE_GREY = "#868e96"
NO_FLOWS = "No energy flows between the assets and the grid in this run"

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
        section("Plant", stack(id="visualization-plant"), hint="Simulation inputs"),
        section("Headline numbers", stack(id="visualization-kpis"), hint="Whole period"),
        section(
            "Checks",
            stack(id="visualization-checks"),
            hint="Is the plant well sized for its grid access?",
        ),
        section(
            "Economics",
            [
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
                stack(id="visualization-revenue-quality"),
            ],
        ),
        section(
            "Plant sizing",
            stack(id="visualization-sizing"),
            hint="Which component limits the plant?",
            id="visualization-sizing-section",
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
        Output("visualization-revenue-quality", "children"),
        Output("visualization-revenue-quality", "hidden"),
        Output("visualization-sizing", "children"),
        Output("visualization-sizing-section", "hidden"),
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
            [],
            True,
            [],
            True,
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
    results = all_indicators(run.inputs, run.kpis, data, run.market_data)
    quality = revenue_quality(results, rule)
    power = od.plant_ratings(run.inputs)["battery_power"]
    sizing = plant_sizing(results, power, od.battery_duration(data, power))
    heads = [
        f"Revenue by {rule.noun}",
        f"€ per {rule.noun}, by market",
        f"Energy flows by {rule.noun}",
        f"MWh per {rule.noun} · export ↑ by source, battery charge ↓ by source",
        "Battery state of charge",
        f"mean SOC by {soc_unit} and hour",
    ]
    return (
        [spec_card(plant_groups(run.inputs, data))],
        headline_blocks(run, data),
        sizing_checks.sizing_body(results, "visualization"),
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
        quality,
        not quality,
        sizing,
        not sizing,
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


def plant_groups(inputs: dict, data: pd.DataFrame | None = None) -> list[dict]:
    """``spec_card`` groups of the simulated plant, physical first: grid connection, one group
    per PV generator and per battery, then markets and period. PV / battery groups only when
    the run has them; a missing rating falls back to the observed maximum in ``data``."""
    data = data if data is not None else pd.DataFrame()
    groups = [grid_group(inputs, data)]
    if od.has_pv(inputs, data):
        groups += pv_groups(inputs, data)
    if od.has_battery(inputs):
        groups += battery_groups(inputs, data)
    markets = market_group(inputs)
    if markets["rows"]:
        groups.append(markets)
    groups.append(period_group(inputs))
    return groups


def grid_group(inputs: dict, data: pd.DataFrame) -> dict:
    """Grid connection: export / import capacity (MW) and system efficiency."""
    system = inputs.get("system", {})
    efficiency = system.get("efficiency")
    rows = [
        _rated_or_observed(
            "Export capacity", system.get("capacity_sell"), data, "P_system_export", "Max export"
        ),
        _rated_or_observed(
            "Import capacity", system.get("capacity_buy"), data, "P_system_import", "Max import"
        ),
    ]
    if efficiency is not None:
        rows.append(stat_row("Efficiency", f"{efficiency:.0%}"))
    return {"title": "Grid connection", "color": NODE_COLORS["grid"], "rows": rows}


def pv_groups(inputs: dict, data: pd.DataFrame) -> list[dict]:
    """One group per PV generator: peak power, location, orientation, tracker and performance
    factor (the ``losses`` input, which multiplies the PV output). Missing values are skipped."""
    generators = inputs.get("generators") or [{}]
    groups = []
    for generator in generators:
        rows = []
        if generator.get("peak_power") is not None:
            rows.append(stat_row("Peak power", _fmt(generator["peak_power"], "MW")))
        elif len(generators) == 1:
            rows.append(_rated_or_observed("Peak power", None, data, "P_generation", "Max output"))
        lat, lon = generator.get("latitude"), generator.get("longitude")
        if lat is not None and lon is not None:
            rows.append(
                stat_row(
                    "Location",
                    f"{abs(lat):.1f}° {'N' if lat >= 0 else 'S'} · "
                    f"{abs(lon):.1f}° {'E' if lon >= 0 else 'W'}",
                )
            )
        orientation = " · ".join(
            f"{name} {generator[key]:g}°"
            for name, key in (("tilt", "tilt"), ("azimuth", "azimuth"))
            if generator.get(key) is not None
        )
        if orientation:
            rows.append(stat_row("Orientation", orientation))
        if "tracker" in generator:
            rows.append(stat_row("Tracker", str(generator["tracker"] or "fixed")))
        if generator.get("losses") is not None:
            rows.append(
                stat_row(
                    "Performance factor",
                    f"{generator['losses']:.0%}",
                    title=f"PV output × {generator['losses']:g} (input 'losses')",
                )
            )
        groups.append(
            {
                "title": "PV",
                "color": NODE_COLORS["pv"],
                "subtitle": generator.get("name"),
                "rows": rows,
            }
        )
    return groups


def battery_groups(inputs: dict, data: pd.DataFrame) -> list[dict]:
    """One group per battery: power (and minimum), capacity, duration, RTE, usable and initial
    SOC and cycle limits. Missing values are skipped."""
    batteries = inputs.get("batteries", [])
    groups = []
    for battery in batteries:
        power = battery_power(battery)
        capacity = battery.get("capacity")
        rows = []
        if power is not None:
            minimum = battery.get("min_power_output")
            rows.append(
                stat_row(
                    "Power",
                    _fmt(power, "MW") + (f" · min {minimum:g}" if minimum else ""),
                    title=f"max {power:g} MW" + (f" · min {minimum:g} MW" if minimum else ""),
                )
            )
        elif len(batteries) == 1:
            rows.append(
                _rated_or_observed("Power", None, data, "P_storage_discharge", "Max output")
            )
        if capacity is not None:
            rows.append(stat_row("Capacity", _fmt(capacity, "MWh")))
        if capacity and power:
            rows.append(stat_row("Duration", _fmt(capacity / power, "h")))
        if battery.get("rte") is not None:
            rows.append(stat_row("RTE", f"{battery['rte']:.0%}"))
        dod, soc_max = battery.get("dod"), battery.get("soc_max")
        if dod is not None or soc_max is not None:
            low = 1 - (dod if dod is not None else 1.0)
            high = soc_max if soc_max is not None else 1.0
            rows.append(stat_row("Usable SOC", f"{low * 100:.0f}–{high * 100:.0f} %"))
        if battery.get("soc_initial") is not None:
            rows.append(stat_row("Initial SOC", f"{battery['soc_initial']:.0%}"))
        rows += [
            stat_row(label, f"{battery[key]:g} /day")
            for key, label in (
                ("max_cycles_day", "Max cycles"),
                ("max_cycles_day_monthly_avg", "Monthly avg limit"),
                ("max_cycles_day_yearly_avg", "Yearly avg limit"),
            )
            if battery.get(key) is not None
        ]
        groups.append(
            {
                "title": "Battery",
                "color": NODE_COLORS["battery"],
                "subtitle": battery.get("name"),
                "rows": rows,
            }
        )
    return groups


def market_group(inputs: dict) -> dict:
    """One row per market: its name and "energy", or its reserve band ("band ↑2.5 / ↓2.5 MW");
    every other parameter as an indented dim row below it (e.g. "activation  bin_max")."""
    rows = []
    for market in inputs.get("markets", []):
        params = dict(market.get("params") or {})
        up, down = params.pop("max_up", None), params.pop("max_down", None)
        band = " / ".join(
            f"{arrow}{value:g}" for arrow, value in (("↑", up), ("↓", down)) if value is not None
        )
        value = f"band {band} MW" if band else "energy"
        rows.append(stat_row(market["type"], value) | {"color": market_color(market["type"])})
        rows += [
            stat_row(MARKET_PARAM_LABELS.get(key, key), str(param)) | {"indent": True}
            for key, param in params.items()
            if param is not None
        ]
    return {"title": "Markets", "rows": rows}


def period_group(inputs: dict) -> dict:
    """Simulated period: dates and length in days (the resolution is in the status row)."""
    period = inputs.get("period", {})
    days = od.period_days(period)
    rows = []
    if period.get("start") and period.get("end"):
        rows.append(stat_row("Dates", f"{period['start'][:10]} → {period['end'][:10]}"))
    if days:
        rows.append(stat_row("Days", f"{days:,.0f} d"))
    return {"title": "Period", "rows": rows}


def headline_blocks(run, data: pd.DataFrame) -> list:
    """Left (2/3): hero strip (total, per year, cycles) above the markets table; right (1/3):
    the energy list. Columns keep their natural height. PV / battery rows only when the run has
    them."""
    markets = data_table(
        market_columns(data), market_rows(run.kpis, data), title="Markets", hint="whole period"
    )
    energy = stat_list("Energy", energy_rows(run, data), hint="MWh over the period")
    left = stack([hero_strip(hero_items(run)), markets])
    return [columns([left, energy], widths=[2, 1], align_start=True)]


def hero_items(run) -> list[dict]:
    """Headline numbers: total revenue, revenue per year and, with a battery, equivalent
    cycles (the battery wear behind the revenue)."""
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
    items = [
        {
            "label": "Total revenue",
            "value": total,
            "unit": "€",
            "decimals": 0,
            "compact": True,
            "primary": True,
        },
        {
            "label": "Revenue per year",
            "value": per_year,
            "unit": "€",
            "decimals": 0,
            "compact": True,
            "sub": " · ".join(per_year_sub) or None,
        },
    ]
    if od.has_battery(run.inputs):
        cycles = kpis.get("equivalent_cycles")
        items.append(
            {
                "label": "Equivalent cycles",
                "value": cycles,
                "unit": "",
                "decimals": 0 if cycles is not None and cycles >= 100 else 1,
                "sub": f"{cycles / days:.2f} per day" if cycles is not None and days else None,
            }
        )
    return items


def _price_directions(data: pd.DataFrame) -> list[str]:
    found = {item["direction"] for item in od.captured_prices(data)}
    return sorted(found, key=lambda d: (d not in ("sell", "buy"), d != "sell", d))


def market_columns(data: pd.DataFrame) -> list[str]:
    """Headers of the markets table: market, revenue, share and one captured price column per
    traded direction (sell, buy...)."""
    return [
        "Market",
        "Revenue",
        "Share",
        *[f"Avg {d.replace('_', ' ')} price · €/MWh" for d in _price_directions(data)],
    ]


def market_rows(kpis: dict, data: pd.DataFrame) -> list[dict]:
    """One row per market: revenue, share of the total and captured prices vs the market
    average (delta coloured: ok when favourable, warn otherwise). '-' where a market does not
    trade that direction (e.g. reserve bands)."""
    total = kpis.get("revenue_total")
    revenue = kpis.get("revenue_by_market", {})
    prices = {(item["market"], item["direction"]): item for item in od.captured_prices(data)}
    names = list(revenue) + [m for m, _ in prices if m not in revenue]
    names = list(dict.fromkeys(names))
    rows = []
    for market in names:
        value = revenue.get(market)
        cells = [
            {
                "value": compact_text(value, "€") if value is not None else None,
                "title": f"{value:,.0f} €" if value is not None else None,
            },
            f"{value / total:.0%}" if value is not None and total else None,
        ]
        for direction in _price_directions(data):
            item = prices.get((market, direction))
            cells.append(_price_cell(item) if item else None)
        rows.append({"label": market, "color": market_color(market), "cells": cells})
    return rows


def _price_cell(item: dict) -> dict:
    cell = {"value": f"{item['price']:,.1f}"}
    if item["market_avg"] is not None:
        delta = item["price"] - item["market_avg"]
        favourable = delta >= 0 if item["direction"] == "sell" else delta <= 0
        cell |= {
            "sub": f"{delta:+,.1f} vs mkt {item['market_avg']:,.1f}",
            "status": "ok" if favourable else "warn",
            "title": f"captured {item['direction']} price − time-average market price",
        }
    return cell


def energy_rows(run, data: pd.DataFrame) -> list[dict]:
    """Energy totals (MWh): PV, grid, battery (with losses) and curtailment rows, PV and
    battery rows only when the run has them."""
    kpis = run.kpis
    pv = od.energy(data, "P_generation") if od.has_pv(run.inputs, data) else None
    charged = kpis.get("energy_charged_MWh")
    discharged = kpis.get("energy_discharged_MWh")
    losses = charged - discharged if charged is not None and discharged is not None else None
    excess = kpis.get("excess_energy_MWh")
    rows = []
    if pv is not None:
        rows.append(stat_row("PV generation", pv, "MWh", 0, compact=True))
    rows += [
        stat_row("Exported", kpis.get("energy_exported_MWh"), "MWh", 0, compact=True),
        stat_row("Imported", kpis.get("energy_imported_MWh"), "MWh", 0, compact=True),
    ]
    if od.has_battery(run.inputs):
        rows += [
            stat_row("Battery charged", charged, "MWh", 0, compact=True),
            stat_row("Battery discharged", discharged, "MWh", 0, compact=True),
            stat_row(
                "Battery losses",
                losses,
                "MWh",
                0,
                compact=True,
                sub=f"{losses / charged:.1%} of charged"
                if losses is not None and charged
                else None,
            ),
        ]
    if pv is not None:
        rows.append(
            stat_row(
                "Curtailment",
                excess,
                "MWh",
                0,
                compact=True,
                sub=f"{excess / pv:.1%} of PV generation" if excess is not None and pv else None,
            )
        )
    return rows


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


def revenue_quality(results: dict[str, Indicator], rule: od.PeriodRule) -> list:
    """Revenue quality list (1/3) beside the spread chart (2/3), each only when available;
    the list takes the full width (two columns) without the chart. Empty list when nothing is
    available."""
    rows = quality_rows(results)
    spread = _kpis(results["spread"])
    note_text = (
        f"Run also trades {spread['other_energy_markets']}; battery flows valued at the "
        f"{spread['price_market']} price."
        if spread is not None and spread["other_energy_markets"]
        else None
    )
    chart = None
    if spread is not None:
        n = spread["tbn_hours"]
        chart = chart_card(
            "visualization-spread-periods",
            f"Spread by {rule.noun}: available vs realized",
            f"€/MWh · mean daily TB{n} spread vs battery realized spread",
            SPREAD_CHART_HEIGHT,
            figure=spread_period_figure(results["spread"].tables["daily"], rule, n),
        )
    quality = (
        stat_list(
            "Revenue quality",
            rows,
            columns=1 if chart is not None else 2,
            footnote=note_text,
        )
        if rows
        else None
    )
    if quality is not None and chart is not None:
        return [columns([quality, chart], widths=[1, 2], align_start=True)]
    return [block for block in (quality, chart) if block is not None]


def quality_rows(results: dict[str, Indicator]) -> list[dict]:
    """Rows of the revenue quality list: battery realized spread, value per cycle, PV capture
    rate and revenue concentration, each only when its indicator is available."""
    spread = _kpis(results["spread"])
    per_cycle = _kpis(results["per_cycle"])
    pv = _kpis(results["pv_capture"])
    concentration = _kpis(results["concentration"])
    rows = []
    if spread is not None:
        rows.append(
            stat_row(
                "Battery realized spread",
                spread["realized_spread"],
                "€/MWh",
                1,
                primary=True,
                sub=f"{_num(spread['avg_discharge_price'], 0)} − "
                f"{_num(spread['avg_charge_price'], 0)} €/MWh · break-even "
                f"{_num(spread['breakeven_spread'], 1)}",
                title="avg discharge − avg charge price · break-even = charge price × (1/RTE − 1)",
            )
        )
    if per_cycle is not None:
        rows.append(
            stat_row(
                "Value per cycle",
                per_cycle["value_per_cycle"],
                "€",
                0,
                compact=True,
                sub=f"{_num(per_cycle['value_per_mwh_discharged'], 0)} €/MWh discharged",
            )
        )
    if pv is not None:
        export_rate, uplift = pv["export_capture_rate"], pv["export_uplift"]
        with_storage = per_cycle is not None and export_rate is not None and uplift is not None
        rows.append(
            stat_row(
                "PV capture rate",
                _pct(pv["pv_capture_rate"]),
                "%",
                0,
                sub=f"{export_rate:.0%} with storage · {uplift * 100:+.0f} pp"
                if with_storage
                else f"{_num(pv['pv_weighted_price'], 1)} vs avg "
                f"{_num(pv['average_price'], 1)} €/MWh",
            )
        )
    if concentration is not None:
        rows.append(
            stat_row(
                "Top 10 % days",
                _pct(concentration["top10_days_share"]),
                "%",
                0,
                sub=f"of revenue · median day {compact_text(concentration['median_day'], '€')}"
                f" · best {compact_text(concentration['best_day'], '€')}",
            )
        )
    return rows


def spread_period_figure(daily: pd.DataFrame, rule: od.PeriodRule, n: int) -> go.Figure:
    """Per period: mean daily TBn spread and battery realized spread (energy-weighted, from the
    ``spread`` indicator daily table), side by side. Periods with less than
    ``MIN_PERIOD_COVERAGE`` of their days in the run are dropped (an average of one day would
    look like a whole month); other partial periods are translucent."""
    sums = od.aggregate(
        daily[["discharge_energy", "discharge_value", "charge_energy", "charge_value"]], rule
    )
    weekly = {"label": "left", "closed": "left"} if rule is od.WEEKLY else {}
    tbn = daily["tbn_spread"].resample(rule.rule, **weekly).mean()
    realized = _div(sums["discharge_value"], sums["discharge_energy"]) - _div(
        sums["charge_value"], sums["charge_energy"]
    )
    frame = pd.DataFrame({f"TB{n} spread": tbn, "Realized spread": realized})
    partial = None
    if rule is not od.DAILY:
        coverage = od.day_coverage(daily.index, rule).reindex(frame.index, fill_value=0.0)
        frame = frame[coverage >= MIN_PERIOD_COVERAGE]
        partial = od.partial_periods(daily.index, rule).reindex(frame.index, fill_value="")
    return stacked_bar_figure(
        frame,
        colors={f"TB{n} spread": REFERENCE_GREY, "Realized spread": NODE_COLORS["battery"]},
        unit="€/MWh",
        x_format=rule.x_format,
        partial=partial,
        grouped=True,
        height=SPREAD_CHART_HEIGHT,
    )


# ---------- Plant sizing ----------


def plant_sizing(
    results: dict[str, Indicator],
    battery_power: float | None = None,
    battery_curve: pd.DataFrame | None = None,
) -> list:
    """Which component limits the plant: a row with the "Grid connection" (1/3) and
    "Battery" (2/3, rows in two columns) lists (each only with data, natural height), then a row with the net POI (left) and battery (right)
    duration curves. The battery curve (``od.battery_duration``) is left out when it does not
    differ from the POI curve (``od.curves_differ``), e.g. battery-only runs; the POI curve
    then takes the full width. Empty list when there is nothing to show."""
    grid = _kpis(results["grid"])
    lists = []
    if grid is not None:
        lists.append(stat_list("Grid connection", grid_rows(grid)))
    battery = battery_rows(_kpis(results["battery_usage"]), _kpis(results["afrr"]), battery_power)
    if battery:
        lists.append(stat_list("Battery", battery, columns=2))
    widths = [1, 2] if len(lists) == 2 and grid is not None else None
    body = [columns(lists, widths=widths, align_start=True)] if lists else []

    charts = []
    grid_curve = results["grid"].tables["duration"] if grid is not None else None
    if grid is not None:
        charts.append(
            chart_card(
                "visualization-grid-duration",
                "Net POI power duration curve",
                "% of export / import limit, sorted from highest · dotted: ±100 %",
                INDICATOR_CHART_HEIGHT,
                figure=duration_figure(grid_curve, "Net POI power", NODE_COLORS["grid"]),
            )
        )
    if (
        battery_curve is not None
        and len(battery_curve)
        and (grid_curve is None or od.curves_differ(battery_curve, grid_curve))
    ):
        charts.append(
            chart_card(
                "visualization-battery-duration",
                "Battery power duration curve",
                "% of battery power, sorted from highest · + discharge, − charge · dotted: ±100 %",
                INDICATOR_CHART_HEIGHT,
                figure=duration_figure(battery_curve, "Battery net power", NODE_COLORS["battery"]),
            )
        )
    if charts:
        body.append(columns(charts))
    return body


def grid_rows(grid: dict) -> list[dict]:
    """Rows of the grid connection list (``grid`` indicator kpis)."""
    rows = [
        stat_row(
            "Time at export limit",
            _pct(grid["export_limit_share"]),
            "%",
            1,
            primary=True,
            sub=f"≥ 99 % of {grid['export_limit']:g} MW",
        )
    ]
    if grid["import_limit_share"] is not None:
        rows.append(
            stat_row(
                "Time at import limit",
                _pct(grid["import_limit_share"]),
                "%",
                1,
                sub=f"≥ 99 % of {grid['capacity_buy']:g} MW",
            )
        )
    rows.append(
        stat_row(
            "POI capacity factor",
            _pct(grid["capacity_factor"]),
            "%",
            1,
            sub="exported / (limit × hours)",
        )
    )
    return rows


def battery_rows(usage: dict | None, afrr: dict | None, battery_power=None) -> list[dict]:
    """Rows of the battery list: power limit, depth of discharge, SOC limits, idle time and,
    with aFRR, the average bands as a share of battery power (``battery_usage`` / ``afrr``
    indicator kpis, ``None`` when not available)."""
    rows = []
    if usage is not None:
        if usage.get("power_limit_share") is not None:
            rows.append(
                stat_row(
                    "Time at power limit",
                    _pct(usage["power_limit_share"]),
                    "%",
                    1,
                    primary=True,
                    sub=f"≥ 99 % of {battery_power:g} MW, charge or discharge"
                    if battery_power
                    else "charge or discharge",
                )
            )
        if usage.get("mean_daily_dod") is not None:
            rows.append(
                stat_row(
                    "Mean daily depth of discharge",
                    _pct(usage["mean_daily_dod"]),
                    "%",
                    0,
                    sub="daily max − min SOC",
                )
            )
        if usage.get("soc_min_share") is not None:
            rows += [
                stat_row(
                    "Time at min SOC",
                    _pct(usage["soc_min_share"]),
                    "%",
                    0,
                    sub="within 1 % of the minimum",
                ),
                stat_row(
                    "Time at max SOC",
                    _pct(usage["soc_max_share"]),
                    "%",
                    0,
                    sub="within 1 % of the maximum",
                ),
            ]
        rows.append(
            stat_row("Idle time", _pct(usage["idle_share"]), "%", 0, sub="no charge nor discharge")
        )
    if afrr is not None:
        for direction in ("up", "down"):
            share = afrr[f"band_{direction}_share_of_power"]
            if share is None:
                continue
            mean = afrr[f"band_{direction}_mean"]
            rows.append(
                stat_row(
                    f"Avg aFRR band {direction}",
                    _pct(share),
                    "%",
                    0,
                    sub=f"{mean:.1f} MW · of battery power" if mean is not None else None,
                )
            )
    return rows


def duration_figure(duration: pd.DataFrame, label: str, color: str) -> go.Figure:
    """Duration curve (``net_percent``, % of a limit, sorted from highest over the share of
    time) with dotted lines at the ±100 % limits."""
    frame = (duration[["net_percent"]] / 100).rename(columns={"net_percent": label})
    return line_figure(
        frame,
        colors={label: color},
        unit="%",
        x_title="Share of time (%)",
        reference_lines=(1.0, -1.0),
        height=INDICATOR_CHART_HEIGHT,
    )


# ---------- Energy flows ----------


def energy_sankey_figure(data: pd.DataFrame) -> go.Figure:
    """Total energy (MWh) between PV, grid and battery, balanced at every node."""
    links, _ = od.sankey_links(data)
    if not any(value > 1e-9 for _, _, value in links):  # e.g. a run without assets
        return message_figure(NO_FLOWS, SANKEY_HEIGHT)
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
        columns={label: x for label, (_, x) in NODES.items()},
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
    if flows.empty:
        return message_figure(NO_FLOWS, 340)
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


def _rated_or_observed(label, rated, data, variable, observed_label):
    """Row with a rating (MW); without one, the observed maximum of ``variable`` in ``data``
    labelled "<observed_label> (observed)"."""
    if rated is not None or data is None or variable not in data:
        return stat_row(label, _fmt(rated, "MW"))
    observed = float(data[variable].abs().max())
    return stat_row(
        f"{observed_label} (observed)",
        _fmt(round(observed, 1), "MW"),
        title=f"no {label.lower()} rating: maximum observed in the run",
    )


def _present(data: pd.DataFrame, variables: list[str]) -> pd.DataFrame:
    return data[[variable for variable in variables if variable in data]]


def _with_prefix(data: pd.DataFrame, prefixes: tuple[str, ...]) -> pd.DataFrame:
    return data[[column for column in data.columns if column.startswith(prefixes)]]


def _kpis(indicator: Indicator) -> dict | None:
    """KPIs of an available indicator, ``None`` otherwise."""
    return indicator.kpis if indicator.available else None


def _pct(value):
    return None if value is None else value * 100


def _num(value, decimals: int) -> str:
    return "-" if value is None else f"{value:,.{decimals}f}"


def _div(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    return numerator / denominator.where(denominator.abs() > 1e-9)


def _fmt(value, unit: str) -> str | None:
    return None if value is None else f"{value:,.4g} {unit}"


TAB = Tab(
    id="visualization",
    label="Visualization",
    description="Overview of a run",
    layout=layout,
    register=register,
)
