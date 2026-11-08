"""Generic Plotly figure builders for the dashboard, themed to match ``assets/style.css``.

Builders take pandas objects (one series per column, time on the index) and know nothing about
runs or markets: the tabs choose which variables to plot and how to aggregate them. Series
colors default to ``series_color(column)``; pass ``colors`` to override them.

Single-row figures: ``line_figure``, ``area_figure``, ``stacked_bar_figure``, ``hbar_figure``,
``histogram_figure``, ``heatmap_figure``. ``rows_figure`` stacks several of them as rows sharing
the x axis. ``sankey_figure`` draws flows between nodes.

Units: pass ``unit`` ("MW", "MWh", "€", "€/MWh"...) so hovers show values with their unit and
sensible decimals. Aggregated charts (bars) also scale their value axis to a readable unit
(k€/M€, GWh) and show compact values in the hover ("1.52 M€").
"""

import math
from collections.abc import Iterable

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from ..visualization.styles import color_for
from .formatting import axis_scale, compact_text

# Dark theme matching assets/style.css. Titles live in the card headers, not in the figures.
_TEXT = "#c3c2b7"
_GRID = "#383835"
HOVER_LABEL = {
    "bgcolor": "#232322",
    "bordercolor": "#4a4a46",
    "font": {"family": "Inter, system-ui, sans-serif", "color": "#f0efec", "size": 13},
}
_LAYOUT = {
    "template": "plotly_dark",
    "hovermode": "x unified",
    "paper_bgcolor": "rgba(0,0,0,0)",
    "plot_bgcolor": "rgba(0,0,0,0)",
    "font": {"family": "Inter, system-ui, sans-serif", "color": _TEXT, "size": 12},
    "margin": {"t": 30, "b": 30, "l": 60, "r": 20},
    "hoverlabel": HOVER_LABEL,
}
# Legend below the plot area (never under the toolbar, which sits at the top right): its top
# edge this many px below the plot, leaving room for the x tick labels.
_LEGEND_GAP_PX = 45
_DIM = "#a3a29a"
# Period axes: up to this many periods get one tick each; with more, one tick every few
# periods (2, 3, 4, 6, 12...) so that there are at most MAX_PERIOD_TICKS_THINNED ticks.
MAX_PERIOD_TICKS = 12
MAX_PERIOD_TICKS_THINNED = 8
_TICK_STEPS = (2, 3, 4, 6, 12, 24, 52)
PARTIAL_OPACITY = 0.45
BAR_GAP = 0.2
# Number format (d3) of hover values per unit; others use ",.2f".
_HOVER_FORMATS = {"MW": ",.1f", "€/MWh": ",.1f", "MWh": ",.0f", "€": ",.0f", "%": ".0%"}
# Decimals of compact values (below 10,000) per unit.
_COMPACT_DECIMALS = {"MW": 1, "€/MWh": 1, "MWh": 0, "€": 0}
# Colors from styles.py that are invisible on a dark background.
_DARK_OVERRIDES = {"black": "#c3c2b7"}


def line_figure(
    frame: pd.DataFrame,
    y_title: str | None = None,
    colors: dict[str, str] | None = None,
    width: float = 1.5,
    height: int = 400,
    labels: dict[str, str] | None = None,
    unit: str = "",
) -> go.Figure:
    """One line per column of ``frame``. ``labels`` renames series (raw name kept in hover)."""
    fig = go.Figure()
    for column in frame.columns:
        fig.add_trace(
            go.Scatter(
                x=frame.index,
                y=frame[column],
                mode="lines",
                line={"color": _pick(colors, column), "width": width},
                **_naming(column, labels, unit),
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
    unit: str = "",
) -> go.Figure:
    """One filled area per column of ``frame``.

    ``stacked=False`` fills each series to zero (overlapping). ``stacked=True`` stacks them;
    series that are never positive stack downwards in their own group, so mixed signs stack
    correctly. Columns in ``line_columns`` are drawn as dashed lines instead (no fill, not
    stacked), e.g. limits or offered bands that would hide the other series. ``labels``
    renames series (raw name kept in hover).
    """
    fig = go.Figure()
    line_columns = set(line_columns)
    for column in frame.columns:
        series = frame[column]
        if column in line_columns:
            style = {"line": {"color": _pick(colors, column), "width": 1.5, "dash": "dash"}}
        elif stacked:
            group = "negative" if (series <= 0).all() else "positive"
            style = {"line": {"color": _pick(colors, column), "width": 0.5}, "stackgroup": group}
        else:
            style = {"line": {"color": _pick(colors, column), "width": 0.5}, "fill": "tozeroy"}
        fig.add_trace(
            go.Scatter(
                x=series.index,
                y=series.to_numpy(),
                mode="lines",
                **style,
                **_naming(column, labels, unit),
            )
        )
    return _finish(fig, y_title, height)


def stacked_bar_figure(
    frame: pd.DataFrame,
    y_title: str | None = None,
    colors: dict[str, str] | None = None,
    height: int = 400,
    unit: str = "",
    x_format: str | None = None,
    partial: pd.Series | None = None,
) -> go.Figure:
    """One bar series per column of ``frame``, stacked (negatives stack downwards).

    - ``unit``: the value axis is scaled to a readable unit (titled with it unless ``y_title``
      is given) and hovers show compact values.
    - ``x_format`` (strftime-style, e.g. "%b %Y") formats the time ticks and the hover header;
      ticks follow ``_period_ticks`` (one per bar, or every few bars, horizontal labels).
    - ``partial``: per bar, a note ("partial · 1 of 30 days") for periods not fully covered,
      or "" for complete ones. Partial bars are drawn translucent and the note is added to the
      hover.
    """
    factor, scaled_unit = axis_scale(_max_stack(frame), unit) if unit else (1.0, "")
    notes = (
        partial.reindex(frame.index).fillna("")
        if partial is not None
        else pd.Series("", index=frame.index)
    )
    opacity = [PARTIAL_OPACITY if note else 1.0 for note in notes]
    fig = go.Figure()
    for column in frame.columns:
        values = _compact_values(frame[column], unit) if unit else [""] * len(frame)
        text = [f"{v} · {n}" if n else v for v, n in zip(values, notes, strict=True)]
        fig.add_trace(
            go.Bar(
                x=frame.index,
                y=frame[column] / factor,
                name=column,
                marker={"color": _pick(colors, column), "opacity": opacity},
                customdata=text,
                hovertemplate="%{customdata}" if unit or notes.any() else None,
            )
        )
    fig.update_layout(barmode="relative", bargap=BAR_GAP)
    if x_format:
        fig.update_xaxes(hoverformat=x_format)
        _period_ticks(fig, frame.index, x_format)
    return _finish(fig, y_title or scaled_unit or None, height)


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
    ``series_color(label)``. With ``unit`` the value axis is scaled to a readable unit and the
    hover shows compact values; ``value_labels=True`` also writes them at the bar ends.
    """
    if sort:
        values = values.sort_values()
    factor, scaled_unit = axis_scale(values.abs().max() if len(values) else 0, unit)
    texts = _compact_values(values, unit)
    labels = {}
    if value_labels:
        labels = {
            "text": texts,
            "textposition": "outside",
            "cliponaxis": False,
            "textfont": {"color": _TEXT, "size": 11},
        }
    scaled = values / factor
    fig = go.Figure(
        go.Bar(
            x=scaled.to_numpy(),
            y=list(values.index),
            orientation="h",
            marker_color=[_pick(colors, label) for label in values.index],
            customdata=texts,
            hovertemplate="%{y}: %{customdata}<extra></extra>",
            showlegend=False,
            **labels,
        )
    )
    title = x_title or scaled_unit
    if title:
        fig.update_xaxes(title_text=title)
    if value_labels and len(values):
        # Room for the labels beyond the longest bars.
        low, high = min(scaled.min(), 0.0), max(scaled.max(), 0.0)
        pad = 0.3 * (high - low or 1.0)
        fig.update_xaxes(range=[low - (pad if low < 0 else 0), high + (pad if high > 0 else 0)])
    fig = apply_theme(fig, height=height)
    # Left margin grows to fit the labels (automargin) instead of a fixed width.
    fig.update_layout(hovermode="closest", bargap=BAR_GAP, margin={"l": 10})
    fig.update_yaxes(automargin=True, ticksuffix="  ")
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
    - Hovers: link "PV → Grid export / 50.2 GWh · 56 % of PV"; node "PV / in 0 · out 89.8 GWh".
    """
    kept = [link for link in links if link[2] and abs(link[2]) > 1e-9]
    kept_colors = (
        [link_colors[i] for i, link in enumerate(links) if link[2] and abs(link[2]) > 1e-9]
        if link_colors
        else None
    )
    used = [node for node in nodes if any(node in (s, t) for s, t, _v in kept)]
    index = {node: i for i, node in enumerate(used)}
    node_color = [_pick(node_colors, node) for node in used]
    link_color = [
        _translucent(_lighten(kept_colors[i] if kept_colors else node_color[index[s]]), 0.4)
        for i, (s, _t, _v) in enumerate(kept)
    ]
    inflow = dict.fromkeys(used, 0.0)
    outflow = dict.fromkeys(used, 0.0)
    for source, target, value in kept:
        outflow[source] += abs(value)
        inflow[target] += abs(value)

    def sides(node_label: str) -> str:
        parts = [
            f"{name} {compact_text(value, unit)}"
            for name, value in (("in", inflow[node_label]), ("out", outflow[node_label]))
            if value
        ]
        return " · ".join(parts)

    labels = list(used)
    if show_totals:
        labels = [f"{n} · {compact_text(max(inflow[n], outflow[n]), unit)}" for n in used]
    node = {
        "label": labels,
        "color": node_color,
        "pad": 18,
        "thickness": 14,
        "line": {"width": 0},
        "customdata": [f"{n}<br>{sides(n)}" for n in used],
        "hovertemplate": "%{customdata}<extra></extra>",
        # Sankey links and nodes take their hover style from link/node.hoverlabel (not from
        # the trace or the layout): without it plotly paints the tooltip with the link color.
        "hoverlabel": HOVER_LABEL,
    }
    if positions:
        node["x"] = [positions.get(n, (0.5, 0.5))[0] for n in used]
        node["y"] = [positions.get(n, (0.5, 0.5))[1] for n in used]
    link_text = [
        f"{s} → {t}<br>{compact_text(abs(v), unit)} · {abs(v) / outflow[s]:.0%} of {s}"
        for s, t, v in kept
    ]
    fig = go.Figure(
        go.Sankey(
            arrangement="snap" if positions else None,
            node=node,
            link={
                "source": [index[s] for s, _t, _v in kept],
                "target": [index[t] for _s, t, _v in kept],
                "value": [abs(v) for _s, _t, v in kept],
                "color": link_color,
                "customdata": link_text,
                "hovertemplate": "%{customdata}<extra></extra>",
                "hoverlabel": HOVER_LABEL,
            },
            hoverlabel=HOVER_LABEL,
        )
    )
    fig = apply_theme(fig, height=height)
    # Labels of the right-most nodes are drawn on their left; the right margin only has to fit
    # the node bars themselves.
    fig.update_layout(hovermode="closest", margin={"t": 20, "b": 20, "l": 20, "r": 40})
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
    The hover reads "<bin range>: <count> <y_title>".
    """
    bins = {"start": 0.0, "size": bin_size} if bin_size else None
    above = pd.Series(False, index=values.index)
    if highlight_above is not None:
        above = values > highlight_above
    count = f" {y_title.lower()}" if y_title else ""
    fig = go.Figure()
    for selected, bar_color in ((~above, color or _TEXT), (above, highlight_color)):
        if selected.any() or bar_color != highlight_color:
            fig.add_trace(
                go.Histogram(
                    x=values[selected].to_numpy(),
                    xbins=bins,
                    marker_color=bar_color,
                    showlegend=False,
                    hovertemplate=f"%{{x}}: %{{y}}{count}<extra></extra>",
                )
            )
    if x_title:
        fig.update_xaxes(title_text=x_title)
    # Counts are integers: integer ticks only, about five of them.
    largest = _largest_bin(values, bin_size)
    fig.update_yaxes(tick0=0, dtick=max(1, math.ceil(largest / 5)), rangemode="tozero")
    fig = _finish(fig, y_title, height)
    fig.update_layout(hovermode="closest", bargap=0.05, barmode="stack")
    if marker is not None:  # after the theme, which restyles annotations as subplot titles
        fig.add_vline(x=marker, line={"color": highlight_color, "width": 1.5, "dash": "dash"})
        if marker_label:
            # Inside the plot, just right of the line and below the top edge (the toolbar).
            fig.add_annotation(
                x=marker,
                y=0.96,
                xref="x",
                yref="paper",
                text=marker_label,
                showarrow=False,
                xanchor="left",
                yanchor="top",
                xshift=4,
                font={"color": _DIM, "size": 11},
            )
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
    colorbar_format: str | None = None,
    x_format: str | None = None,
) -> go.Figure:
    """Heatmap of ``grid``: columns on x, index on y. An empty grid gives an empty figure.

    ``colorbar_format`` (d3, e.g. ".0%") formats the colorbar ticks; ``x_format`` the x
    ticks when the columns are periods (dates), as in ``stacked_bar_figure``.
    """
    fig = go.Figure()
    if not grid.empty:
        colorbar = {"thickness": 10, "len": 0.9, "outlinewidth": 0, "tickfont": {"size": 11}}
        if colorbar_title:
            colorbar["title"] = {"text": colorbar_title, "font": {"size": 12}}
        if colorbar_format:
            colorbar["tickformat"] = colorbar_format
        fig.add_trace(
            go.Heatmap(
                x=grid.columns,
                y=grid.index,
                z=grid.to_numpy(dtype="float32"),  # half the payload; enough to display
                zmin=zmin,
                zmax=zmax,
                colorscale=colorscale,
                colorbar=colorbar,
                hovertemplate=hovertemplate,
            )
        )
    if y_dtick is not None:
        fig.update_yaxes(dtick=y_dtick)
    if x_format and not grid.empty:
        _period_ticks(fig, pd.DatetimeIndex(grid.columns), x_format)
    fig = _finish(fig, y_title, height)
    fig.update_layout(hovermode="closest")
    return fig


def rows_figure(
    rows: list[go.Figure],
    subplot_titles: list[str] | None = None,
    shared_y: bool | list[int] = False,
    vertical_spacing: float = 0.08,
    height: int = 600,
) -> go.Figure:
    """Stack single-row figures (from the builders above) as rows sharing the x axis.

    Takes each figure's traces and y axis title. ``shared_y=True`` gives every row the same y
    range; a list of row numbers (from 1) matches only those rows to each other.
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
    if shared_y is True:
        fig.update_yaxes(matches="y")
    elif shared_y:
        first, *others = shared_y
        anchor = "y" if first == 1 else f"y{first}"
        for row in others:
            fig.update_yaxes(matches=anchor, row=row, col=1)
    return apply_theme(fig, height=height)


def apply_theme(fig: go.Figure, height: int) -> go.Figure:
    """Dashboard dark theme (layout, hover, legend below the plot, axes, subplot titles)."""
    plot_height = max(height - _LAYOUT["margin"]["t"] - _LAYOUT["margin"]["b"], 100)
    legend = {
        "orientation": "h",
        "x": 0,
        "y": -_LEGEND_GAP_PX / plot_height,
        "yanchor": "top",
        "bgcolor": "rgba(0,0,0,0)",
        "font": {"size": 11},
        "itemsizing": "constant",
        "itemwidth": 30,
    }
    fig.update_layout(height=height, legend=legend, **_LAYOUT)
    _style_axes(fig)
    return fig


def series_color(variable: str) -> str:
    """Color of a series in the dashboard (styles.py colors adapted to the dark theme)."""
    color = color_for(variable)
    return _DARK_OVERRIDES.get(color, color)


def _naming(column: str, labels: dict[str, str] | None, unit: str = "") -> dict:
    """Trace name (``labels[column]`` if given) and a hover value with its unit; a renamed
    series keeps its raw variable name in the hover."""
    label = (labels or {}).get(column)
    value = f"%{{y:{_HOVER_FORMATS.get(unit, ',.2f')}}}"
    if unit and unit != "%":
        value += f" {unit}"
    if not label:
        return {"name": column, "hovertemplate": value}
    return {"name": label, "hovertemplate": f"{value} <i>{column}</i>"}


def _period_ticks(fig: go.Figure, index: pd.DatetimeIndex, x_format: str) -> None:
    """Ticks on period positions only, never between periods, with horizontal labels.

    Up to ``MAX_PERIOD_TICKS`` periods get one tick each; with more, one tick every few
    periods. The year goes to a second line ("Jan<br>2025") so labels stay short.
    """
    if len(index) == 0:
        return
    step = _tick_step(len(index))
    ticks = index[::step]
    label_format = x_format.replace(" %Y", "<br>%Y")
    fig.update_xaxes(
        tickmode="array",
        tickvals=list(ticks),
        ticktext=[t.strftime(label_format) for t in ticks],
        tickangle=0,
    )


def _tick_step(n: int) -> int:
    """Periods between ticks for ``n`` periods (see ``MAX_PERIOD_TICKS``)."""
    if n <= MAX_PERIOD_TICKS:
        return 1
    for step in _TICK_STEPS:
        if math.ceil(n / step) <= MAX_PERIOD_TICKS_THINNED:
            return step
    return math.ceil(n / MAX_PERIOD_TICKS_THINNED)


def _largest_bin(values: pd.Series, bin_size: float | None) -> int:
    """Count of the fullest histogram bin (bins of ``bin_size`` from 0)."""
    if values.empty:
        return 1
    if not bin_size:
        return len(values)
    return int((values // bin_size).value_counts().max())


def _compact_values(values: pd.Series, unit: str) -> list[str]:
    decimals = _COMPACT_DECIMALS.get(unit, 1)
    return [compact_text(v, unit, decimals=decimals) for v in values]


def _max_stack(frame: pd.DataFrame) -> float:
    """Largest absolute height of a stacked bar (positives and negatives stack apart)."""
    if frame.empty:
        return 0.0
    positive = frame.clip(lower=0).sum(axis=1).max()
    negative = -frame.clip(upper=0).sum(axis=1).min()
    return float(max(positive, negative))


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
    """Thin grid, subtle but visible zero line, ticks 11 px and axis titles 12 px."""
    common = {
        "gridcolor": _GRID,
        "gridwidth": 1,
        "linecolor": _GRID,
        "zerolinecolor": "#5c5c57",
        "zerolinewidth": 1,
        "tickfont": {"size": 11},
        "title_font": {"size": 12},
    }
    fig.update_xaxes(**common)
    fig.update_yaxes(automargin=True, **common)
    # Subplot titles: small, dim and left-aligned, like card sub-headers.
    fig.update_annotations(font={"size": 12, "color": "#a3a29a"}, xanchor="left", x=0)
