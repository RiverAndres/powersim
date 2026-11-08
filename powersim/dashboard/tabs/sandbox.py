"""Sandbox tab: candidate "overview" page of a run, to decide what the dashboard should show.

Everything here is provisional. When a view is approved, it moves to the tab where it belongs;
then it is removed from here. Notes and decisions: ``.claude/dashboard/sandbox.md``.

Only aggregated data (totals, monthly, month x hour, daily) is sent to the browser, except in
the operation detail section, which shows a 7-day window at full resolution.
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
    hbar_figure,
    heatmap_figure,
    histogram_figure,
    sankey_figure,
    stacked_bar_figure,
)
from ..formatting import compact_text
from .base import Tab
from .visualization import assets_figure_from, markets_figure_from

REVENUE_PREFIX = "B_benefit_"
REVENUE_STREAM_PREFIX = "B_"
ENERGY_PREFIX = "E_"
PRICE_PREFIX = "p_"
SOC_PREFIX = "SOC_"
MARKET_ENERGY_PREFIXES = ("E_sell_", "E_buy_", "E_up_", "E_down_")
SYSTEM_SELL_PREFIX = "E_system_sell_"
DETAIL_DAYS = 7
SMALL_SHARE = 0.005  # bars below 0.5% of the reference are hidden (listed in a footnote)

# Energy flows between PV, battery and grid: (label, variable, color key, side). Charges are
# stored negative in the run; flows are positive energies. Side: +1 export, -1 battery charge.
FLOWS = [
    ("PV → grid", "E_system_sell_generation", "pv_to_grid", 1),
    ("Battery → grid", "E_system_sell_storage", "battery_to_grid", 1),
    ("PV → battery", "E_storage_charge_generation", "pv_to_battery", -1),
    ("Grid → battery", "E_storage_charge_grid", "grid_to_battery", -1),
]

# Sankey nodes: label -> (color key, (x, y) centre position, 0-1 from the top left).
# Sources on the left (PV, small Grid import just below it), Battery in the middle, Grid export
# on the right. Loss and curtailment nodes get their own column (x=0.8) at the bottom, so they
# are not pushed under the tall Grid export node: their centres are 0.08 apart (~38 px on the
# 480 px plot area), more than their heights plus the node padding, so labels do not overlap.
NODES = {
    "PV": ("pv", (0.01, 0.45)),
    "Grid import": ("grid", (0.01, 0.94)),
    "Battery": ("battery", (0.5, 0.55)),
    "Grid export": ("grid", (0.99, 0.42)),
    "System losses": ("losses", (0.8, 0.80)),
    "Curtailment": ("curtailment", (0.8, 0.88)),
    "Battery losses": ("losses", (0.8, 0.96)),
}
SANKEY_HEIGHT = 520

# Human labels of operation series in the detail charts: fixed names, then "<market> <what>"
# by prefix (longest prefixes first).
SERIES_LABELS = {
    "P_generation": "PV generation",
    "P_storage_charge": "Battery charge",
    "P_storage_discharge": "Battery discharge",
    "P_system_export": "Grid export",
    "P_system_import": "Grid import",
    "P_excess": "Curtailment",
}
SERIES_PREFIX_LABELS = [
    ("p_act_up_", "activation up price"),
    ("p_act_down_", "activation down price"),
    ("p_up_", "band up price"),
    ("p_down_", "band down price"),
    ("p_", "price"),
    ("P_sell_", "sell"),
    ("P_buy_", "buy"),
    ("P_up_", "activation up"),
    ("P_down_", "activation down"),
    ("Band_up_", "band up"),
    ("Band_down_", "band down"),
]

# Checks thresholds.
BALANCE_TOLERANCE = 0.001  # largest node imbalance, share of PV generation
EXPORT_TOLERANCE = 0.001  # relative difference between the two export measures
CURTAILMENT_WARNING = 0.05  # share of PV generation
SINKS = {"Curtailment", "Battery losses", "System losses"}

OVERVIEW_GRAPHS = [
    "sandbox-monthly-revenue",
    "sandbox-revenue-streams",
    "sandbox-energy-sankey",
    "sandbox-energy-markets",
    "sandbox-monthly-flows",
    "sandbox-soc-heatmap",
    "sandbox-daily-cycles",
]
FOOTNOTES = [
    "sandbox-revenue-streams-note",
    "sandbox-energy-markets-note",
    "sandbox-daily-cycles-note",
]


def layout() -> list:
    intro = note("Sandbox: candidate overview page of a run. Approved views move to their own tab.")
    week = dcc.Dropdown(id="sandbox-week", options=[], value=None, clearable=False)
    return [
        intro,
        section("Plant", info_row([], id="sandbox-plant"), hint="Simulation inputs"),
        section("Headline numbers", stack(id="sandbox-kpis"), hint="Whole period"),
        section(
            "Checks",
            kpi_grid(id="sandbox-checks", columns=3),
            hint="Does the simulation make sense?",
        ),
        section(
            "Economics",
            columns(
                [
                    chart_card(
                        "sandbox-monthly-revenue", "Monthly revenue by market", "€ per month", 380
                    ),
                    chart_card(
                        "sandbox-revenue-streams",
                        "Revenue by stream",
                        "€ over the period",
                        380,
                        footnote_id="sandbox-revenue-streams-note",
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
                            "sandbox-energy-sankey",
                            "Energy flows",
                            "MWh over the period",
                            SANKEY_HEIGHT,
                        ),
                        chart_card(
                            "sandbox-energy-markets",
                            "Energy by market",
                            "MWh over the period · sold +, bought −",
                            SANKEY_HEIGHT,
                            footnote_id="sandbox-energy-markets-note",
                        ),
                    ]
                ),
                chart_card(
                    "sandbox-monthly-flows",
                    "Monthly energy flows",
                    "MWh per month · export ↑ by source, battery charge ↓ by source",
                    340,
                ),
            ],
        ),
        section(
            "Battery",
            columns(
                [
                    chart_card(
                        "sandbox-soc-heatmap",
                        "Battery state of charge",
                        "mean SOC by month and hour",
                        340,
                    ),
                    chart_card(
                        "sandbox-daily-cycles",
                        "Daily cycles distribution",
                        "days per cycles/day bin",
                        340,
                        footnote_id="sandbox-daily-cycles-note",
                    ),
                ]
            ),
        ),
        section(
            "Operation detail",
            [
                field("Week", week),
                chart_card(
                    "sandbox-assets",
                    "Assets",
                    "Generation, storage and power at the POI · MW",
                    720,
                ),
                chart_card(
                    "sandbox-markets",
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
        Output("sandbox-plant", "children"),
        Output("sandbox-kpis", "children"),
        Output("sandbox-checks", "children"),
        *[Output(graph_id, "figure") for graph_id in OVERVIEW_GRAPHS],
        *[Output(note_id, "children") for note_id in FOOTNOTES],
        Output("sandbox-week", "options"),
        Output("sandbox-week", "value"),
        run_input,
    )
    def show_overview(path):
        return overview_outputs(path)

    @app.callback(
        Output("sandbox-assets", "figure"),
        Output("sandbox-markets", "figure"),
        run_input,
        Input("sandbox-week", "value"),
    )
    def show_detail(path, week):
        return detail_outputs(path, week)


def overview_outputs(path) -> tuple:
    """Outputs of the overview callback: plant, KPIs, checks, figures, footnotes, week
    options/value."""
    if not path:
        return (
            *([], [], []),
            *[EMPTY_FIGURE] * len(OVERVIEW_GRAPHS),
            *[""] * len(FOOTNOTES),
            [],
            None,
        )
    run = load_run(path)
    data = load_timeseries(path)
    weeks = week_options(data.index)
    streams, streams_note = revenue_streams_view(data, run.kpis.get("revenue_total"))
    by_market, by_market_note = energy_by_market_view(data)
    cycles, cycles_note = daily_cycles_view(data, run.inputs)
    return (
        plant_tiles(run.inputs, data),
        headline_kpis(run, data),
        [check_tile(**check) for check in run_checks(run, data)],
        monthly_revenue_figure(data),
        streams,
        energy_sankey_figure(data),
        by_market,
        monthly_flows_figure(data),
        soc_heatmap_figure(data),
        cycles,
        streams_note,
        by_market_note,
        cycles_note,
        weeks,
        weeks[0]["value"] if weeks else None,
    )


def detail_outputs(path, week) -> tuple:
    """Outputs of the detail callback: assets and markets charts of the chosen 7-day window."""
    if not path:
        return EMPTY_FIGURE, EMPTY_FIGURE
    window = time_window(load_timeseries(path), week, days=DETAIL_DAYS)
    labels = series_labels(window.columns)
    return (
        assets_figure_from(window, labels=labels),
        markets_figure_from(window, bands_as_lines=True, labels=labels),
    )


# ---------- Plant and headline numbers ----------


def plant_tiles(inputs: dict, data: pd.DataFrame | None = None) -> list:
    """Info tiles describing the plant and the simulation setup (from ``run.inputs``).

    A missing rating is replaced by the observed maximum in ``data`` when there is one (e.g.
    "PV max output" from ``P_generation``).
    """
    batteries = inputs.get("batteries", [])
    system = inputs.get("system", {})
    period = inputs.get("period", {})
    ratings = plant_ratings(inputs)
    power, capacity = ratings["battery_power"], ratings["battery_capacity"]
    days = _period_days(period)
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
    return [
        _rated_or_observed(
            "PV peak power", ratings["pv_peak"], "PV max output", data, "P_generation"
        ),
        _rated_or_observed(
            "Battery power", power, "Battery max output", data, "P_storage_discharge"
        ),
        info_tile("Battery capacity", _fmt(capacity, "MWh")),
        info_tile("Duration", _fmt(capacity / power if capacity and power else None, "h")),
        info_tile("RTE", f"{rte:.0%}" if rte else None),
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


def plant_ratings(inputs: dict) -> dict:
    """Rated PV peak power (MW), battery power (MW) and capacity (MWh); None when unknown."""
    batteries = inputs.get("batteries", [])
    return {
        "pv_peak": _sum_known(g.get("peak_power") for g in inputs.get("generators", [])),
        "battery_power": _sum_known(_battery_power(b) for b in batteries),
        "battery_capacity": _sum_known(b.get("capacity") for b in batteries),
    }


def headline_kpis(run, data: pd.DataFrame) -> list:
    """KPI groups: economics (with captured prices) and energy."""
    kpis = run.kpis
    total = kpis.get("revenue_total")
    days = _period_days(run.inputs.get("period", {}))
    years = days / 365.25 if days else None
    per_year = total / years if total is not None and years else None
    power = plant_ratings(run.inputs)["battery_power"]

    economics = [
        kpi_tile("Total revenue", total, "€", 0, primary=True, compact=True, digits=4),
        kpi_tile(
            "Revenue per year",
            per_year,
            "€",
            0,
            compact=True,
            sub=f"{per_year / power / 1000:,.0f} k€/MW·year of battery"
            if per_year is not None and power
            else None,
        ),
    ]
    for market, value in kpis.get("revenue_by_market", {}).items():
        share = f"{value / total:.0%} of total" if value is not None and total else None
        economics.append(kpi_tile(f"Revenue {market}", value, "€", 0, sub=share, compact=True))

    dt = period_hours(data.index)
    pv = float((data["P_generation"] * dt).sum()) if "P_generation" in data else None
    charged = kpis.get("energy_charged_MWh")
    discharged = kpis.get("energy_discharged_MWh")
    losses = charged - discharged if charged is not None and discharged is not None else None
    cycles = kpis.get("equivalent_cycles")
    excess = kpis.get("excess_energy_MWh")
    energy = [
        kpi_tile("PV generation", pv, "MWh", 0, compact=True),
        kpi_tile("Energy exported", kpis.get("energy_exported_MWh"), "MWh", 0, compact=True),
        kpi_tile("Energy imported", kpis.get("energy_imported_MWh"), "MWh", 0, compact=True),
        kpi_tile("Energy charged", charged, "MWh", 0, compact=True),
        kpi_tile("Energy discharged", discharged, "MWh", 0, compact=True),
        kpi_tile(
            "Battery losses",
            losses,
            "MWh",
            0,
            compact=True,
            sub=f"{losses / charged:.1%} of charged" if losses is not None and charged else None,
        ),
        kpi_tile(
            "Equivalent cycles",
            cycles,
            "",
            0,
            sub=f"{cycles / days:.2f} per day" if cycles is not None and days else None,
        ),
        kpi_tile(
            "Curtailment",
            excess,
            "MWh",
            0,
            compact=True,
            sub=f"{excess / pv:.1%} of PV generation" if excess is not None and pv else None,
        ),
    ]
    economics += captured_price_tiles(data)
    return [kpi_group("Economics", economics, columns=3), kpi_group("Energy", energy, columns=4)]


def captured_prices(data: pd.DataFrame) -> list[dict]:
    """Average captured price per market and direction: ``B_<dir>_<m>`` / ``E_<dir>_<m>``.

    Pairs with (almost) no energy are skipped. ``market_avg`` is the time-average market price
    ``p_<m>`` (None if missing). Items: ``market, direction, price, market_avg`` (€/MWh).
    """
    prices = []
    for market in _markets(data):
        for column in data.columns:
            if not (column.startswith(ENERGY_PREFIX) and column.endswith(f"_{market}")):
                continue
            direction = column.removeprefix(ENERGY_PREFIX).removesuffix(f"_{market}")
            revenue_column = f"{REVENUE_STREAM_PREFIX}{direction}_{market}"
            energy = float(data[column].sum())
            if revenue_column not in data or abs(energy) < 1e-6:
                continue
            market_price = f"{PRICE_PREFIX}{market}"
            prices.append(
                {
                    "market": market,
                    "direction": direction,
                    "price": float(data[revenue_column].sum()) / energy,
                    "market_avg": float(data[market_price].mean())
                    if market_price in data
                    else None,
                }
            )
    return prices


def captured_price_tiles(data: pd.DataFrame) -> list:
    """KPI tiles of ``captured_prices``, with the market average as sub-line."""
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
        for item in captured_prices(data)
    ]


# ---------- Checks ----------


def run_checks(run, data: pd.DataFrame) -> list[dict]:
    """Sanity checks of a run, as ``check_tile`` arguments (label, value, status, detail)."""
    links, pv = sankey_links(data)
    checks = [
        check_cycle_limit(daily_cycles(data, run.inputs), cycle_limit(run.inputs)),
        check_simultaneous(data),
        check_energy_balance(links, pv),
        check_export(data, run.kpis.get("energy_exported_MWh")),
        check_curtailment(run.kpis.get("excess_energy_MWh"), pv),
    ]
    for item in captured_prices(data):
        if item["direction"] == "sell" and item["market_avg"] is not None:
            checks.append(
                {
                    "label": f"{item['market']} captured vs market",
                    "value": f"{item['price'] - item['market_avg']:+,.1f} €/MWh",
                    "status": "info",
                    "detail": f"sell {item['price']:,.1f} vs avg {item['market_avg']:,.1f} €/MWh",
                }
            )
    return checks


def check_cycle_limit(cycles: pd.Series, limit: float | None) -> dict:
    """Days whose equivalent cycles exceed the battery daily limit."""
    peak = f"max {cycles.max():.2f}/day" if len(cycles) else None
    check = {"label": "Daily cycle limit", "status": "info", "detail": peak}
    if limit is None:
        return {**check, "value": "no limit set"}
    days = int((cycles > limit + 1e-9).sum())
    return {
        **check,
        "value": f"{days} days above {limit:g}/day",
        "status": "warn" if days else "ok",
        "detail": f"{peak} · daily discharged / capacity" if peak else None,
    }


def check_simultaneous(data: pd.DataFrame) -> dict:
    """Periods where the battery charges and discharges at the same time (allowed)."""
    check = {
        "label": "Simultaneous charge and discharge",
        "status": "info",
        "detail": "allowed by the model",
    }
    if "P_storage_charge" not in data or "P_storage_discharge" not in data:
        return {**check, "value": None}
    both = (data["P_storage_charge"].abs() > 1e-6) & (data["P_storage_discharge"].abs() > 1e-6)
    share = both.mean() if len(both) else 0.0
    return {**check, "value": f"{int(both.sum()):,} periods ({share:.1%})"}


def check_energy_balance(links: list[tuple[str, str, float]], pv: float) -> dict:
    """Largest imbalance of the energy flows (PV against its generation, every node with
    inflows and outflows), as a share of PV generation."""
    inflow, outflow = {}, {}
    for source, target, value in links:
        outflow[source] = outflow.get(source, 0.0) + value
        inflow[target] = inflow.get(target, 0.0) + value
    inflow["PV"] = inflow.get("PV", 0.0) + pv
    imbalance = max(
        (abs(inflow[node] - outflow[node]) for node in inflow if node in outflow), default=0.0
    )
    reference = pv or sum(inflow.values()) or 1.0
    share = imbalance / reference
    return {
        "label": "Energy balance",
        "value": f"{share:.3%} max imbalance",
        "status": "ok" if share < BALANCE_TOLERANCE else "warn",
        "detail": f"largest node gap {compact_text(imbalance, 'MWh')} · share of PV generation",
    }


def check_export(data: pd.DataFrame, exported_kpi: float | None) -> dict:
    """Exported energy measured two ways: Σ E_system_sell_* (flows) and the run KPI."""
    flows = sum(_abs_total(data, c) for c in data.columns if c.startswith(SYSTEM_SELL_PREFIX))
    check = {"label": "Export consistency", "status": "info"}
    if not exported_kpi:
        return {**check, "value": compact_text(flows, "MWh"), "detail": "no export KPI"}
    difference = flows / exported_kpi - 1
    return {
        **check,
        "value": f"{compact_text(flows, 'MWh')} vs {compact_text(exported_kpi, 'MWh')}",
        "status": "warn" if abs(difference) > EXPORT_TOLERANCE else "ok",
        "detail": f"Δ {difference:+.2%} · Σ E_system_sell vs Σ P_system_export·dt",
    }


def check_curtailment(excess: float | None, pv: float) -> dict:
    """Curtailed energy as a share of PV generation."""
    check = {"label": "Curtailment", "status": "info"}
    if excess is None or not pv:
        return {**check, "value": compact_text(excess, "MWh") if excess is not None else None}
    share = excess / pv
    return {
        **check,
        "value": f"{share:.1%} of PV generation",
        "status": "warn" if share > CURTAILMENT_WARNING else "info",
        "detail": compact_text(excess, "MWh"),
    }


# ---------- Economics ----------


def monthly_revenue_figure(data: pd.DataFrame) -> go.Figure:
    """Revenue per month and market (sum of B_benefit_*), stacked bars."""
    monthly = _monthly(_by_market(data, REVENUE_PREFIX))
    colors = {market: market_color(market) for market in monthly.columns}
    return stacked_bar_figure(monthly, y_title="€", colors=colors, height=380)


def revenue_streams_view(data: pd.DataFrame, total_revenue=None) -> tuple[go.Figure, str]:
    """Total per revenue component (``B_<component>_<market>``, except ``B_benefit_*``).

    Streams below 0.5% of the total revenue are hidden and listed in the returned footnote.
    """
    markets = _markets(data)
    totals, colors = {}, {}
    for column in data.columns:
        if not column.startswith(REVENUE_STREAM_PREFIX) or column.startswith(REVENUE_PREFIX):
            continue
        market = next((m for m in markets if column.endswith(f"_{m}")), None)
        if market is None:
            continue
        component = column.removeprefix(REVENUE_STREAM_PREFIX).removesuffix(f"_{market}")
        label = f"{market} · {component.replace('_', ' ')}"
        totals[label] = float(data[column].sum())
        colors[label] = market_color(market)
    totals = pd.Series(totals, dtype=float)
    if total_revenue is None:
        total_revenue = float(_by_market(data, REVENUE_PREFIX).sum().sum())
    shown, footnote = _hide_small(totals, abs(total_revenue), "of total revenue")
    figure = hbar_figure(shown, colors=colors, unit="€", value_labels=True, height=380)
    return figure, footnote


# ---------- Energy flows ----------


def energy_sankey_figure(data: pd.DataFrame) -> go.Figure:
    """Total energy (MWh) between PV, grid and battery, balanced at every node (see
    ``sankey_links``)."""
    links, _ = sankey_links(data)
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


def sankey_links(data: pd.DataFrame) -> tuple[list[tuple[str, str, float]], float]:
    """Energy flows (source, target, MWh) and the PV generation (MWh).

    Battery losses are what enters the battery and is not discharged. System losses are the
    residual between what PV generates / the battery discharges and what reaches the grid or
    the battery (system efficiency).
    """
    flow = {label: _abs_total(data, variable) for label, variable, *_ in FLOWS}
    dt = period_hours(data.index)

    def energy(variable):
        return abs(float((data[variable] * dt).sum())) if variable in data else 0.0

    pv = energy("P_generation")
    curtailment = energy("P_excess")
    discharged = energy("P_storage_discharge")
    battery_in = flow["PV → battery"] + flow["Grid → battery"]
    battery_losses = max(battery_in - discharged, 0.0)
    system_from_pv = max(pv - flow["PV → grid"] - flow["PV → battery"] - curtailment, 0.0)
    system_from_battery = max(battery_in - battery_losses - flow["Battery → grid"], 0.0)
    links = [
        ("PV", "Grid export", flow["PV → grid"]),
        ("PV", "Battery", flow["PV → battery"]),
        ("Grid import", "Battery", flow["Grid → battery"]),
        ("Battery", "Grid export", flow["Battery → grid"]),
        ("PV", "Curtailment", curtailment),
        ("PV", "System losses", _negligible(system_from_pv, pv)),
        ("Battery", "System losses", _negligible(system_from_battery, battery_in)),
        ("Battery", "Battery losses", battery_losses),
    ]
    return links, pv


def energy_by_market_view(data: pd.DataFrame) -> tuple[go.Figure, str]:
    """Total energy per market and direction (E_sell_/E_buy_/E_up_/E_down_), signed.

    Entries below 0.5% of the largest one are hidden and listed in the returned footnote.
    """
    totals, colors = {}, {}
    for column in data.columns:
        prefix = next((p for p in MARKET_ENERGY_PREFIXES if column.startswith(p)), None)
        if prefix is None:
            continue
        market = column.removeprefix(prefix)
        label = f"{market} · {prefix.removeprefix(ENERGY_PREFIX).rstrip('_')}"
        totals[label] = float(data[column].sum())
        colors[label] = market_color(market)
    totals = pd.Series(totals, dtype=float)
    largest = float(totals.abs().max()) if len(totals) else 0.0
    shown, footnote = _hide_small(totals, largest, "of the largest")
    figure = hbar_figure(shown, colors=colors, unit="MWh", value_labels=True, height=SANKEY_HEIGHT)
    return figure, footnote


def monthly_flows_figure(data: pd.DataFrame) -> go.Figure:
    """Energy per month: exported to the grid by source (up), charged into the battery by
    source (down)."""
    present = [flow for flow in FLOWS if flow[1] in data]
    flows = pd.DataFrame(
        {label: side * data[variable].abs() for label, variable, _, side in present},
        index=data.index,
    )
    colors = {label: FLOW_COLORS[key] for label, _, key, _ in present}
    return stacked_bar_figure(_monthly(flows), y_title="MWh", colors=colors, height=340)


# ---------- Battery ----------


def soc_heatmap_figure(data: pd.DataFrame) -> go.Figure:
    """Mean SOC of all batteries (0-1) as a heatmap: month on x, hour of day on y."""
    soc_columns = [c for c in data.columns if c.startswith(SOC_PREFIX)]
    grid = pd.DataFrame()
    if soc_columns:
        soc = data[soc_columns].mean(axis=1)
        month = pd.DatetimeIndex(soc.index.strftime("%Y-%m-01"))
        grid = soc.groupby([month, soc.index.hour]).mean().unstack(level=0).sort_index()
    return heatmap_figure(
        grid,
        zmin=0,
        zmax=1,
        colorbar_title="SOC",
        hovertemplate="%{x|%b %Y} · %{y}:00<br>SOC %{z:.0%}<extra></extra>",
        y_title="Hour",
        y_dtick=3,
        height=340,
    )


def daily_cycles(data: pd.DataFrame, inputs: dict) -> pd.Series:
    """Equivalent cycles per day: daily discharged energy / total battery capacity."""
    capacity = plant_ratings(inputs)["battery_capacity"]
    if not capacity or "P_storage_discharge" not in data:
        return pd.Series(dtype=float)
    discharged = data["P_storage_discharge"].abs() * period_hours(data.index)
    return discharged.resample("D").sum() / capacity


def cycle_limit(inputs: dict) -> float | None:
    """Strictest ``max_cycles_day`` of the batteries (None if none is set)."""
    limits = [b["max_cycles_day"] for b in inputs.get("batteries", []) if b.get("max_cycles_day")]
    return min(limits) if limits else None


def daily_cycles_view(data: pd.DataFrame, inputs: dict) -> tuple[go.Figure, str]:
    """Histogram of equivalent cycles per day, and a footnote with the days above the limit.

    The battery ``max_cycles_day`` limit, when set, is drawn as a vertical marker and the days
    above it in the warning color.
    """
    cycles = daily_cycles(data, inputs)
    limit = cycle_limit(inputs)
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
    if limit is not None:
        footnote = f"{int((cycles > limit + 1e-9).sum())} days above the limit"
    return figure, footnote


# ---------- Operation detail ----------


def week_options(index: pd.DatetimeIndex) -> list[dict]:
    """Consecutive 7-day windows from the first period: dropdown options (value = start date)."""
    if len(index) == 0:
        return []
    starts = pd.date_range(index.min().normalize(), index.max(), freq=f"{DETAIL_DAYS}D")
    return [
        {
            "label": f"Week {i} · {start:%Y-%m-%d} → "
            f"{start + pd.Timedelta(days=DETAIL_DAYS - 1):%Y-%m-%d}",
            "value": start.isoformat(),
        }
        for i, start in enumerate(starts, start=1)
    ]


def time_window(data: pd.DataFrame, start, days: int = DETAIL_DAYS) -> pd.DataFrame:
    """Rows of ``data`` in ``[start, start + days)``; from the first period if ``start`` is None."""
    if data.empty:
        return data
    begin = data.index.min() if start is None else pd.Timestamp(start)
    if begin.tzinfo is None and data.index.tz is not None:
        begin = begin.tz_localize(data.index.tz)
    window = data[(data.index >= begin) & (data.index < begin + pd.Timedelta(days=days))]
    if window.empty:  # stale value from another run
        return time_window(data, None, days)
    return window


# ---------- Helpers ----------


def period_hours(index: pd.DatetimeIndex) -> pd.Series:
    """Length of each period in hours (the last one repeats the previous)."""
    if len(index) < 2:
        return pd.Series(1.0, index=index)
    hours = pd.Series(index, index=index).diff().shift(-1).dt.total_seconds() / 3600
    return hours.fillna(hours.iloc[-2])


def series_labels(variables) -> dict[str, str]:
    """Human labels of operation series ("PV generation", "AFRR band up"...) by name/prefix."""
    labels = {}
    for variable in variables:
        if variable in SERIES_LABELS:
            labels[variable] = SERIES_LABELS[variable]
            continue
        for prefix, what in SERIES_PREFIX_LABELS:
            if variable.startswith(prefix):
                labels[variable] = f"{variable.removeprefix(prefix)} {what}"
                break
    return labels


def _markets(data: pd.DataFrame) -> list[str]:
    return [c.removeprefix(REVENUE_PREFIX) for c in data.columns if c.startswith(REVENUE_PREFIX)]


def _hide_small(values: pd.Series, reference: float, what: str) -> tuple[pd.Series, str]:
    """Drop entries below ``SMALL_SHARE`` of ``reference``; footnote listing them."""
    if not reference:
        return values, ""
    small = values.abs() < SMALL_SHARE * reference
    if not small.any():
        return values, ""
    hidden = ", ".join(values.index[small])
    return values[~small], f"Hidden (<{SMALL_SHARE:.1%} {what}): {hidden}"


def _negligible(value: float, reference: float) -> float:
    """``value``, or 0 when it is a rounding residual (< 0.01% of ``reference``)."""
    return value if value > 1e-4 * max(reference, 1.0) else 0.0


def _rated_or_observed(label, rated, observed_label, data, variable):
    if rated is not None or data is None or variable not in data:
        return info_tile(label, _fmt(rated, "MW"))
    observed = float(data[variable].abs().max())
    return info_tile(observed_label, _fmt(round(observed, 1), "MW"))


def _by_market(data: pd.DataFrame, prefix: str) -> pd.DataFrame:
    selected = [c for c in data.columns if c.startswith(prefix)]
    return data[selected].rename(columns=lambda c: c.removeprefix(prefix))


def _monthly(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.resample("MS").sum()


def _abs_total(data: pd.DataFrame, variable: str) -> float:
    return float(data[variable].abs().sum()) if variable in data else 0.0


def _battery_power(battery: dict):
    if battery.get("max_power_output") is not None:
        return battery["max_power_output"]
    if battery.get("capacity") is not None and battery.get("c_rate") is not None:
        return battery["capacity"] * battery["c_rate"]
    return None


def _sum_known(values):
    known = [v for v in values if v is not None]
    return sum(known) if known else None


def _period_days(period: dict) -> float | None:
    dt_hours = period.get("dt_hours") or []
    n_periods = period.get("n_periods")
    if len(dt_hours) == 1 and n_periods:
        return n_periods * dt_hours[0] / 24
    if period.get("start") and period.get("end"):
        span = pd.Timestamp(period["end"]) - pd.Timestamp(period["start"])
        return span.total_seconds() / 86400 + (min(dt_hours) / 24 if dt_hours else 0)
    return None


def _fmt(value, unit: str) -> str | None:
    return None if value is None else f"{value:,.4g} {unit}"


TAB = Tab(
    id="sandbox",
    label="Sandbox",
    description="Experiments for new views",
    layout=layout,
    register=register,
)
