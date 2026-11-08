"""Visualization tab: main KPIs and the operation charts of the selected run.

The charts are the same three as ``SimulationResult.plot_operation()``. Series are chosen by
variable prefix (not by market name), so new markets appear without code changes. Signs follow
``SimulationResult.operation_timeseries``: import, charge, purchases and downward bands are
negative.
"""

import pandas as pd
import plotly.graph_objects as go
from dash import Output

from ...runs import SimulationRun
from ..components import EMPTY_FIGURE, chart_card, kpi_grid, kpi_tile, load_run
from ..figures import area_figure, line_figure, rows_figure
from .base import Tab

PRICE_PREFIX = "p_"
BAND_PREFIX = "Band_"
MARKET_OPERATION_PREFIXES = ("P_sell_", "P_buy_", "P_up_", "P_down_", "Band_up_", "Band_down_")

# (graph id, card title, card hint, height in px)
CHART_CARDS = [
    ("visualization-assets", "Assets", "Generation, storage and power at the POI · MW", 720),
    ("visualization-markets", "Markets", "Prices and operation per market", 620),
    ("visualization-excess", "Excess power", "Power that cannot be exported · MW", 280),
]


def layout() -> list:
    return [kpi_grid(id="visualization-kpis"), *[chart_card(*card) for card in CHART_CARDS]]


def register(app, run_input) -> None:
    @app.callback(
        Output("visualization-kpis", "children"),
        *[Output(graph_id, "figure") for graph_id, *_ in CHART_CARDS],
        run_input,
    )
    def show_run(path):
        if not path:
            return [], EMPTY_FIGURE, EMPTY_FIGURE, EMPTY_FIGURE
        run = load_run(path)
        return kpi_cards(run), assets_figure(run), markets_figure(run), excess_figure(run)


def kpi_cards(run) -> list:
    kpis = run.kpis
    revenue_total = kpis.get("revenue_total")
    cards = [kpi_tile("Total revenue", revenue_total, "€", decimals=0, primary=True)]
    for market, value in kpis.get("revenue_by_market", {}).items():
        share = (
            f"{value / revenue_total:.0%} of total" if value is not None and revenue_total else None
        )
        cards.append(kpi_tile(f"Revenue {market}", value, "€", decimals=0, sub=share))
    cards += [
        kpi_tile("Energy exported", kpis.get("energy_exported_MWh"), "MWh"),
        kpi_tile("Energy imported", kpis.get("energy_imported_MWh"), "MWh"),
        kpi_tile("Energy charged", kpis.get("energy_charged_MWh"), "MWh"),
        kpi_tile("Energy discharged", kpis.get("energy_discharged_MWh"), "MWh"),
        kpi_tile("Equivalent cycles", kpis.get("equivalent_cycles"), "", decimals=2),
        kpi_tile("Excess energy", kpis.get("excess_energy_MWh"), "MWh"),
    ]
    return cards


# ---------- Figures ----------


def assets_figure(run: SimulationRun) -> go.Figure:
    """Generation, storage and point-of-interconnection power (3 rows, shared axes)."""
    return assets_figure_from(run.timeseries_wide())


def assets_figure_from(data: pd.DataFrame, labels: dict[str, str] | None = None) -> go.Figure:
    """``assets_figure`` from the wide time series (any time window of it).

    ``labels`` renames the series in legends (raw names by default).
    """
    rows = [
        ["P_generation"],
        ["P_storage_charge", "P_storage_discharge"],
        ["P_system_export", "P_system_import"],
    ]
    return rows_figure(
        [area_figure(_present(data, variables), y_title="MW", labels=labels) for variables in rows],
        subplot_titles=[
            "Generation modules power production",
            "Storage modules power",
            "Power output at POI",
        ],
        shared_y=True,
        height=720,
    )


def markets_figure(run: SimulationRun) -> go.Figure:
    """Market prices and stacked market operation (2 rows, shared x axis)."""
    return markets_figure_from(run.timeseries_wide())


def markets_figure_from(
    data: pd.DataFrame, bands_as_lines: bool = False, labels: dict[str, str] | None = None
) -> go.Figure:
    """``markets_figure`` from the wide time series (any time window of it).

    ``bands_as_lines=True`` draws the offered bands (``Band_*``) as dashed lines instead of
    stacked areas, so they do not hide the energy traded in the markets. ``labels`` renames the
    series in legends (raw names by default).
    """
    prices = line_figure(_with_prefix(data, (PRICE_PREFIX,)), y_title="EUR/MWh", labels=labels)
    operation_data = _with_prefix(data, MARKET_OPERATION_PREFIXES)
    bands = (
        [c for c in operation_data.columns if c.startswith(BAND_PREFIX)] if bands_as_lines else []
    )
    operation = area_figure(
        operation_data, stacked=True, y_title="MW", line_columns=bands, labels=labels
    )
    return rows_figure(
        [prices, operation],
        subplot_titles=["Market prices", "Market operation"],
        vertical_spacing=0.1,
        height=620,
    )


def excess_figure(run: SimulationRun) -> go.Figure:
    """Excess power that cannot be exported (curtailment)."""
    data = run.timeseries_wide()
    return area_figure(_present(data, ["P_excess"]), y_title="MW", height=280)


def _present(data: pd.DataFrame, variables: list[str]) -> pd.DataFrame:
    return data[[variable for variable in variables if variable in data]]


def _with_prefix(data: pd.DataFrame, prefixes: tuple[str, ...]) -> pd.DataFrame:
    return data[[column for column in data.columns if column.startswith(prefixes)]]


TAB = Tab(
    id="visualization",
    label="Visualization",
    description="KPIs and operation of a run",
    layout=layout,
    register=register,
)
