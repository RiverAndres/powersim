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

# Dark theme matching assets/style.css. Titles live in the card headers, not in the figures.
_TEXT = "#c3c2b7"
_GRID = "#383835"
_LAYOUT = {
    "template": "plotly_dark",
    "hovermode": "x unified",
    "paper_bgcolor": "rgba(0,0,0,0)",
    "plot_bgcolor": "rgba(0,0,0,0)",
    "font": {"family": "Inter, system-ui, sans-serif", "color": _TEXT, "size": 12},
    "margin": {"t": 30, "b": 30, "l": 60, "r": 20},
    "legend": {
        "orientation": "h",
        "y": 1.02,
        "yanchor": "bottom",
        "x": 0,
        "bgcolor": "rgba(0,0,0,0)",
    },
    "hoverlabel": {"bgcolor": "#232322", "bordercolor": "#4a4a46"},
}
# Colors from styles.py that are invisible on a dark background.
_DARK_OVERRIDES = {"black": "#c3c2b7"}


def assets_figure(run: SimulationRun) -> go.Figure:
    """Generation, storage and point-of-interconnection power (3 rows, shared axes)."""
    data = run.timeseries_wide()
    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
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
    apply_theme(fig, height=720)
    return fig


def markets_figure(run: SimulationRun) -> go.Figure:
    """Market prices and stacked market operation (2 rows, shared x axis)."""
    data = run.timeseries_wide()
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.1,
        subplot_titles=("Market prices", "Market operation"),
    )
    for variable in _columns_with_prefix(data, (PRICE_PREFIX,)):
        fig.add_trace(
            go.Scatter(
                x=data.index,
                y=data[variable],
                name=variable,
                mode="lines",
                line={"color": _color(variable), "width": 1.5},
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
    apply_theme(fig, height=620)
    return fig


def excess_figure(run: SimulationRun) -> go.Figure:
    """Excess power that cannot be exported (curtailment)."""
    data = run.timeseries_wide()
    fig = go.Figure()
    if "P_excess" in data:
        _add_area(fig, data["P_excess"], "P_excess")
    fig.update_yaxes(title_text="MW")
    apply_theme(fig, height=280)
    return fig


def _columns_with_prefix(data: pd.DataFrame, prefixes: tuple[str, ...]) -> list[str]:
    return [column for column in data.columns if column.startswith(prefixes)]


def _add_area(fig, series: pd.Series, name: str, row=None, stackgroup=None) -> None:
    trace = go.Scatter(
        x=series.index,
        y=series.to_numpy(),
        name=name,
        mode="lines",
        line={"color": _color(name), "width": 0.5},
        **({"stackgroup": stackgroup} if stackgroup else {"fill": "tozeroy"}),
    )
    if row is None:
        fig.add_trace(trace)
    else:
        fig.add_trace(trace, row=row, col=1)


def apply_theme(fig: go.Figure, height: int) -> go.Figure:
    """Dashboard dark theme (layout, axes and subplot titles) with the given height."""
    fig.update_layout(height=height, **_LAYOUT)
    _style_axes(fig)
    return fig


def series_color(variable: str) -> str:
    """Color of a series in the dashboard (styles.py colors adapted to the dark theme)."""
    return _color(variable)


def _color(variable: str) -> str:
    color = color_for(variable)
    return _DARK_OVERRIDES.get(color, color)


def _style_axes(fig: go.Figure) -> None:
    fig.update_xaxes(gridcolor=_GRID, zerolinecolor=_GRID, linecolor=_GRID)
    fig.update_yaxes(gridcolor=_GRID, zerolinecolor="#4a4a46", linecolor=_GRID)
    # Subplot titles: small, dim and left-aligned, like card sub-headers.
    fig.update_annotations(font={"size": 12, "color": "#a3a29a"}, xanchor="left", x=0)
