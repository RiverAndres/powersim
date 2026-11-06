"""Plotly figures of a SimulationRun: the same three charts as SimulationResult.plot_operation().

Series are chosen by variable prefix (not by market name), so new markets appear without code
changes. Signs follow SimulationResult.operation_timeseries: import, charge, purchases and
downward bands are negative.
"""

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from ..runs import SimulationRun
from ..visualization.styles import color_for

PRICE_PREFIX = "p_"
MARKET_OPERATION_PREFIXES = ("P_sell_", "P_buy_", "P_up_", "P_down_", "Band_up_", "Band_down_")

_LAYOUT = {"template": "plotly_white", "hovermode": "x unified", "margin": {"t": 60, "b": 40}}


def assets_figure(run: SimulationRun) -> go.Figure:
    """Generation, storage and point-of-interconnection power (3 rows, shared axes)."""
    data = run.timeseries_wide()
    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        subplot_titles=(
            "Generation modules power production",
            "Storage modules power",
            "Power output at POI",
        ),
    )
    rows = {
        1: ["P_generation"],
        2: ["P_storage_charge", "P_storage_discharge"],
        3: ["P_system_export", "P_system_import"],
    }
    for row, variables in rows.items():
        for variable in variables:
            if variable in data:
                _add_area(fig, data[variable], variable, row=row)

    fig.update_yaxes(matches="y", title_text="MW")
    fig.update_layout(height=750, title_text="Assets", **_LAYOUT)
    return fig


def markets_figure(run: SimulationRun) -> go.Figure:
    """Market prices and stacked market operation (2 rows, shared x axis)."""
    data = run.timeseries_wide()
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=("Market prices", "Market operation"),
    )
    for variable in _columns_with_prefix(data, (PRICE_PREFIX,)):
        fig.add_trace(
            go.Scatter(
                x=data.index,
                y=data[variable],
                name=variable,
                mode="lines",
                line={"color": color_for(variable), "width": 1.5},
            ),
            row=1,
            col=1,
        )

    for variable in _columns_with_prefix(data, MARKET_OPERATION_PREFIXES):
        series = data[variable]
        # Negative series stack downwards in their own group, so stacking stays correct.
        group = "negative" if (series <= 0).all() else "positive"
        _add_area(fig, series, variable, row=2, stackgroup=group)

    fig.update_yaxes(title_text="EUR/MWh", row=1, col=1)
    fig.update_yaxes(title_text="MW", row=2, col=1)
    fig.update_layout(height=650, title_text="Markets", **_LAYOUT)
    return fig


def excess_figure(run: SimulationRun) -> go.Figure:
    """Excess power that cannot be exported (curtailment)."""
    data = run.timeseries_wide()
    fig = go.Figure()
    if "P_excess" in data:
        _add_area(fig, data["P_excess"], "P_excess")
    fig.update_yaxes(title_text="MW")
    fig.update_layout(height=320, title_text="Excess power", **_LAYOUT)
    return fig


def _columns_with_prefix(data: pd.DataFrame, prefixes: tuple[str, ...]) -> list[str]:
    return [column for column in data.columns if column.startswith(prefixes)]


def _add_area(fig, series: pd.Series, name: str, row=None, stackgroup=None) -> None:
    trace = go.Scatter(
        x=series.index,
        y=series.to_numpy(),
        name=name,
        mode="lines",
        line={"color": color_for(name), "width": 0.5},
        **({"stackgroup": stackgroup} if stackgroup else {"fill": "tozeroy"}),
    )
    if row is None:
        fig.add_trace(trace)
    else:
        fig.add_trace(trace, row=row, col=1)
