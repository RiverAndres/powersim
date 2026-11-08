"""Generic Plotly figure builders for the dashboard, themed to match ``assets/style.css``.

Builders take pandas objects (one series per column, time on the index) and know nothing about
runs or markets: the tabs choose which variables to plot and how to aggregate them. Series
colors default to ``series_color(column)``; pass ``colors`` to override them.

Single-row figures: ``line_figure``, ``area_figure``, ``stacked_bar_figure``, ``hbar_figure``,
``histogram_figure``, ``heatmap_figure``. ``rows_figure`` stacks several of them as rows sharing
the x axis. ``sankey_figure`` draws flows between nodes.
"""

from collections.abc import Iterable

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from ..visualization.styles import color_for
from .formatting import compact_text

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


def line_figure(
    frame: pd.DataFrame,
    y_title: str | None = None,
    colors: dict[str, str] | None = None,
    width: float = 1.5,
    height: int = 400,
    labels: dict[str, str] | None = None,
) -> go.Figure:
    """One line per column of ``frame``. ``labels`` renames series (see ``_naming``)."""
    fig = go.Figure()
    for column in frame.columns:
        fig.add_trace(
            go.Scatter(
                x=frame.index,
                y=frame[column],
                mode="lines",
                line={"color": _pick(colors, column), "width": width},
                **_naming(column, labels),
            )
        )
    return _finish(fig, y_title, height)


def area_figure(
    frame: pd.DataFrame,
    stacked: bool = False,
    y_title: str | None = None,
    colors: dict[str, str] | None = None,
    height: int = 400,
    line_columns: Iterable[str] = (),
    labels: dict[str, str] | None = None,
) -> go.Figure:
    """One filled area per column of ``frame``.

    ``stacked=False`` fills each series to zero (overlapping). ``stacked=True`` stacks them;
    series that are never positive stack downwards in their own group, so mixed signs stack
    correctly. Columns in ``line_columns`` are drawn as dashed lines instead (no fill, not
    stacked), e.g. limits or offered bands that would hide the other series. ``labels``
    renames series (see ``_naming``).
    """
    fig = go.Figure()
    line_columns = set(line_columns)
    for column in frame.columns:
        series = frame[column]
        if column in line_columns:
            fig.add_trace(
                go.Scatter(
                    x=series.index,
                    y=series.to_numpy(),
                    mode="lines",
                    line={"color": _pick(colors, column), "width": 1.5, "dash": "dash"},
                    **_naming(column, labels),
                )
            )
            continue
        if stacked:
            fill = {"stackgroup": "negative" if (series <= 0).all() else "positive"}
        else:
            fill = {"fill": "tozeroy"}
        fig.add_trace(
            go.Scatter(
                x=series.index,
                y=series.to_numpy(),
                mode="lines",
                line={"color": _pick(colors, column), "width": 0.5},
                **fill,
                **_naming(column, labels),
            )
        )
    return _finish(fig, y_title, height)


def stacked_bar_figure(
    frame: pd.DataFrame,
    y_title: str | None = None,
    colors: dict[str, str] | None = None,
    height: int = 400,
) -> go.Figure:
    """One bar series per column of ``frame``, stacked (negatives stack downwards)."""
    fig = go.Figure()
    for column in frame.columns:
        fig.add_trace(
            go.Bar(x=frame.index, y=frame[column], name=column, marker_color=_pick(colors, column))
        )
    fig.update_layout(barmode="relative")
    return _finish(fig, y_title, height)


def hbar_figure(
    values: pd.Series,
    colors: dict[str, str] | None = None,
    x_title: str | None = None,
    unit: str = "",
    sort: bool = True,
    height: int = 400,
    value_labels: bool = False,
) -> go.Figure:
    """Horizontal bars, one per item of ``values`` (index = labels).

    ``sort=True`` puts the largest value on top. Colors per label (``colors``), else
    ``series_color(label)``. ``value_labels=True`` writes the compact value (with ``unit``) at
    the end of each bar.
    """
    if sort:
        values = values.sort_values()
    suffix = f" {unit}" if unit else ""
    labels = {}
    if value_labels:
        labels = {
            "text": [compact_text(v, unit, decimals=0) for v in values],
            "textposition": "outside",
            "cliponaxis": False,
            "textfont": {"color": _TEXT, "size": 11},
        }
    fig = go.Figure(
        go.Bar(
            x=values.to_numpy(),
            y=list(values.index),
            orientation="h",
            marker_color=[_pick(colors, label) for label in values.index],
            hovertemplate=f"%{{y}}: %{{x:,.0f}}{suffix}<extra></extra>",
            showlegend=False,
            **labels,
        )
    )
    if x_title:
        fig.update_xaxes(title_text=x_title)
    if value_labels and len(values):
        # Room for the labels beyond the longest bars.
        low, high = min(values.min(), 0.0), max(values.max(), 0.0)
        pad = 0.3 * (high - low or 1.0)
        fig.update_xaxes(range=[low - (pad if low < 0 else 0), high + (pad if high > 0 else 0)])
    fig = apply_theme(fig, height=height)
    fig.update_layout(hovermode="closest", margin={"l": 140})
    return fig


def sankey_figure(
    nodes: list[str],
    links: list[tuple[str, str, float]],
    node_colors: dict[str, str] | None = None,
    link_colors: list[str] | None = None,
    unit: str = "",
    show_totals: bool = False,
    positions: dict[str, tuple[float, float]] | None = None,
    height: int = 400,
) -> go.Figure:
    """Flows between nodes: ``links`` are ``(source, target, value)`` with node labels.

    - Links with a zero value and nodes without links are left out.
    - Link colors (one per link) default to their source node color; they are drawn lighter and
      translucent so they read as the node color.
    - ``show_totals=True`` appends each node's total (largest of inflow and outflow) to its
      label, e.g. "PV · 89.8 GWh".
    - ``positions`` fixes ``(x, y)`` of nodes (0-1, x left to right, y top to bottom), e.g. to
      keep small nodes and their labels apart.
    """
    kept = [(i, link) for i, link in enumerate(links) if link[2] and abs(link[2]) > 1e-9]
    used = [node for node in nodes if any(node in (s, t) for _, (s, t, _v) in kept)]
    index = {node: i for i, node in enumerate(used)}
    node_color = [_pick(node_colors, node) for node in used]
    link_color = [
        _translucent(_lighten(link_colors[i] if link_colors else node_color[index[s]]), 0.4)
        for i, (s, _t, _v) in kept
    ]
    labels = list(used)
    if show_totals:
        inflow = dict.fromkeys(used, 0.0)
        outflow = dict.fromkeys(used, 0.0)
        for _, (source, target, value) in kept:
            outflow[source] += abs(value)
            inflow[target] += abs(value)
        labels = [
            f"{node} · {compact_text(max(inflow[node], outflow[node]), unit)}" for node in used
        ]
    node = {
        "label": labels,
        "color": node_color,
        "pad": 18,
        "thickness": 14,
        "line": {"width": 0},
        "hovertemplate": "%{label}<extra></extra>",
    }
    if positions:
        node["x"] = [positions.get(n, (0.5, 0.5))[0] for n in used]
        node["y"] = [positions.get(n, (0.5, 0.5))[1] for n in used]
    fig = go.Figure(
        go.Sankey(
            arrangement="snap" if positions else None,
            valueformat=",.0f",
            valuesuffix=f" {unit}" if unit else "",
            node=node,
            link={
                "source": [index[s] for _, (s, _t, _v) in kept],
                "target": [index[t] for _, (_s, t, _v) in kept],
                "value": [abs(v) for _, (_s, _t, v) in kept],
                "color": link_color,
            },
        )
    )
    fig = apply_theme(fig, height=height)
    fig.update_layout(hovermode="closest", margin={"t": 20, "b": 20, "l": 20, "r": 20})
    return fig


def histogram_figure(
    values: pd.Series,
    bin_size: float | None = None,
    x_title: str | None = None,
    y_title: str | None = None,
    color: str | None = None,
    marker: float | None = None,
    marker_label: str | None = None,
    highlight_above: float | None = None,
    highlight_color: str = "#ffa94d",
    height: int = 400,
) -> go.Figure:
    """Histogram of ``values`` (count per bin), with an optional vertical marker line.

    ``highlight_above`` draws the values above it in ``highlight_color`` (same bins, stacked).
    """
    bins = {"start": 0.0, "size": bin_size} if bin_size else None
    above = pd.Series(False, index=values.index)
    if highlight_above is not None:
        above = values > highlight_above
    fig = go.Figure()
    for selected, bar_color in ((~above, color or _TEXT), (above, highlight_color)):
        if selected.any() or bar_color != highlight_color:
            fig.add_trace(
                go.Histogram(
                    x=values[selected].to_numpy(),
                    xbins=bins,
                    marker_color=bar_color,
                    showlegend=False,
                    hovertemplate="%{x}: %{y}<extra></extra>",
                )
            )
    if marker is not None:
        fig.add_vline(
            x=marker,
            line={"color": "#ff6b6b", "width": 1.5, "dash": "dash"},
            annotation_text=marker_label,
            annotation_font={"color": "#ff6b6b", "size": 11},
            annotation_position="top",
        )
    if x_title:
        fig.update_xaxes(title_text=x_title)
    fig = _finish(fig, y_title, height)
    fig.update_layout(hovermode="closest", bargap=0.05, barmode="stack")
    return fig


def heatmap_figure(
    grid: pd.DataFrame,
    zmin: float | None = None,
    zmax: float | None = None,
    colorscale: str = "Viridis",
    colorbar_title: str | None = None,
    hovertemplate: str | None = None,
    y_title: str | None = None,
    y_dtick: float | None = None,
    height: int = 400,
) -> go.Figure:
    """Heatmap of ``grid``: columns on x, index on y. An empty grid gives an empty figure."""
    fig = go.Figure()
    if not grid.empty:
        fig.add_trace(
            go.Heatmap(
                x=grid.columns,
                y=grid.index,
                z=grid.to_numpy(dtype="float32"),  # half the payload; enough to display
                zmin=zmin,
                zmax=zmax,
                colorscale=colorscale,
                colorbar={"title": colorbar_title} if colorbar_title else None,
                hovertemplate=hovertemplate,
            )
        )
    if y_dtick is not None:
        fig.update_yaxes(dtick=y_dtick)
    fig = _finish(fig, y_title, height)
    fig.update_layout(hovermode="closest")
    return fig


def rows_figure(
    rows: list[go.Figure],
    subplot_titles: list[str] | None = None,
    shared_y: bool = False,
    vertical_spacing: float = 0.08,
    height: int = 600,
) -> go.Figure:
    """Stack single-row figures (from the builders above) as rows sharing the x axis.

    Takes each figure's traces and y axis title. ``shared_y=True`` also gives every row the same
    y range.
    """
    fig = make_subplots(
        rows=len(rows),
        cols=1,
        shared_xaxes=True,
        vertical_spacing=vertical_spacing,
        subplot_titles=subplot_titles,
    )
    for row, source in enumerate(rows, start=1):
        for trace in source.data:
            fig.add_trace(trace, row=row, col=1)
        y_title = source.layout.yaxis.title.text
        if y_title:
            fig.update_yaxes(title_text=y_title, row=row, col=1)
    if shared_y:
        fig.update_yaxes(matches="y")
    return apply_theme(fig, height=height)


def apply_theme(fig: go.Figure, height: int) -> go.Figure:
    """Dashboard dark theme (layout, axes and subplot titles) with the given height."""
    fig.update_layout(height=height, **_LAYOUT)
    _style_axes(fig)
    return fig


def series_color(variable: str) -> str:
    """Color of a series in the dashboard (styles.py colors adapted to the dark theme)."""
    color = color_for(variable)
    return _DARK_OVERRIDES.get(color, color)


def _naming(column: str, labels: dict[str, str] | None) -> dict:
    """Trace name: ``labels[column]`` if given, keeping the raw variable name in the hover."""
    label = (labels or {}).get(column)
    if not label:
        return {"name": column}
    return {"name": label, "hovertemplate": f"%{{y:,.2f}} <i>{column}</i>"}


def _pick(colors: dict[str, str] | None, column: str) -> str:
    return (colors or {}).get(column) or series_color(column)


def _lighten(color: str, amount: float = 0.25) -> str:
    """Hex color mixed with white by ``amount`` (0-1); other formats are returned unchanged."""
    if color.startswith("#") and len(color) == 7:
        channels = (int(color[i : i + 2], 16) for i in (1, 3, 5))
        return "#" + "".join(f"{round(c + (255 - c) * amount):02x}" for c in channels)
    return color


def _translucent(color: str, alpha: float = 0.45) -> str:
    """Hex color as rgba with ``alpha``; other color formats are returned unchanged."""
    if color.startswith("#") and len(color) == 7:
        red, green, blue = (int(color[i : i + 2], 16) for i in (1, 3, 5))
        return f"rgba({red}, {green}, {blue}, {alpha})"
    return color


def _finish(fig: go.Figure, y_title: str | None, height: int) -> go.Figure:
    if y_title:
        fig.update_yaxes(title_text=y_title)
    return apply_theme(fig, height=height)


def _style_axes(fig: go.Figure) -> None:
    fig.update_xaxes(gridcolor=_GRID, zerolinecolor=_GRID, linecolor=_GRID)
    fig.update_yaxes(gridcolor=_GRID, zerolinecolor="#4a4a46", linecolor=_GRID)
    # Subplot titles: small, dim and left-aligned, like card sub-headers.
    fig.update_annotations(font={"size": 12, "color": "#a3a29a"}, xanchor="left", x=0)
