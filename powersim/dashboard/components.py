"""Generic UI components shared by the dashboard shell and tabs, plus run loading and formatting.

Components receive plain data (labels, numbers, units, Dash children) and know nothing about
runs, markets or batteries; turning run data into their inputs is the job of the tabs. Styles
live in ``assets/style.css``.
"""

from functools import lru_cache

from dash import dcc, html

from ..runs import SimulationRun
from .formatting import format_compact

# "responsive" makes the figure follow its container (width when a hidden tab is shown, window
# resizes). The container must have an explicit height, or the graph collapses: chart_card sets it.
# The toolbar only shows while hovering a graph: done in style.css, because dcc.Graph turns
# the "hover" value of displayModeBar into "always".
GRAPH_CONFIG = {"displaylogo": False, "responsive": True}
EMPTY_FIGURE = {"layout": {"paper_bgcolor": "rgba(0,0,0,0)", "plot_bgcolor": "rgba(0,0,0,0)"}}


@lru_cache(maxsize=16)
def load_run(path: str) -> SimulationRun:
    return SimulationRun.load(path)


@lru_cache(maxsize=4)
def load_timeseries(path: str):
    """Wide time series of a saved run (cached; do not modify the returned DataFrame)."""
    return load_run(path).timeseries_wide()


# ---------- Cards and grouping ----------


def card(
    title: str | None = None,
    hint: str = "",
    children=None,
    id: str | None = None,
    title_id: str | None = None,
    hint_id: str | None = None,
):
    """Card (panel with border) with an optional head (title and short hint) and any content.

    ``title_id`` / ``hint_id`` give the title and hint ids, so callbacks can change them.
    """
    head = (
        html.Div(
            className="card-head",
            children=[
                html.H4(title, className="card-title", **_id(title_id)),
                html.Span(hint, className="card-hint", title=hint or None, **_id(hint_id)),
            ],
        )
        if title is not None
        else None
    )
    content = children if isinstance(children, list) else ([] if children is None else [children])
    return html.Section(className="card", children=[head, *content] if head else content, **_id(id))


def chart_card(
    graph_id: str,
    title: str,
    hint: str = "",
    height: int = 400,
    footnote_id: str | None = None,
    dynamic_head: bool = False,
):
    """Card with a title, a short hint (what it shows, units) and a graph ``height`` px tall.

    ``footnote_id`` adds an empty footnote below the graph, to be filled by a callback.
    ``dynamic_head=True`` gives the title and hint the ids ``<graph_id>-title`` and
    ``<graph_id>-hint`` so callbacks can change them.
    """
    graph = dcc.Graph(id=graph_id, config=GRAPH_CONFIG, style={"height": f"{height}px"})
    footnote = [html.Div(id=footnote_id, className="card-footnote")] if footnote_id else []
    ids = {"title_id": f"{graph_id}-title", "hint_id": f"{graph_id}-hint"} if dynamic_head else {}
    return card(title, hint, [graph, *footnote], **ids)


def section(title: str, children, hint: str | None = None):
    """Heading (and optional hint) followed by its cards, to group related content."""
    content = children if isinstance(children, list) else [children]
    head = html.Div(
        className="section-head",
        children=[
            html.H3(title, className="section-title"),
            html.Span(hint, className="section-hint") if hint else None,
        ],
    )
    return html.Div(className="section", children=[head, *content])


def stack(children: list | None = None, id: str | None = None):
    """Vertical stack of blocks with the standard gap."""
    return html.Div(children or [], className="stack", **_id(id))


def columns(children: list, widths: list[float] | None = None, id: str | None = None):
    """Side-by-side columns (relative ``widths``, equal by default); one column on narrow screens.

    Like every container with an ``id``, callbacks can hide it with its ``hidden`` property.
    """
    widths = widths or [1] * len(children)
    template = " ".join(f"minmax(0, {width}fr)" for width in widths)
    return html.Div(children, className="columns", style={"--columns": template}, **_id(id))


# ---------- KPIs ----------


def kpi_tile(
    label: str,
    value,
    unit: str,
    decimals: int = 1,
    primary=False,
    sub=None,
    compact: bool = False,
    digits: int = 3,
):
    """KPI tile: label, value with its unit and an optional sub-line. ``None`` shows '-'.

    ``compact=True`` shortens large values (see ``format_compact``) and keeps the full value in
    the tooltip.
    """
    full = _format_full(value, unit, decimals)
    text, unit = format_compact(value, unit, decimals, digits) if compact else (full[0], unit)
    children = [
        html.Div(label, className="kpi-label", title=label),
        html.Div(
            [text, html.Span(unit, className="kpi-unit") if unit else None],
            className="kpi-value",
        ),
    ]
    if sub:
        children.append(html.Div(sub, className="kpi-sub", title=sub))
    extra = {"title": " ".join(full).strip()} if compact and value is not None else {}
    return html.Div(children, className="kpi kpi-primary" if primary else "kpi", **extra)


def kpi_grid(tiles: list | None = None, id: str | None = None, columns: int | None = None):
    """Grid of KPI tiles.

    Without ``columns`` it wraps to as many rows as needed. With ``columns`` it uses that many
    equal columns (halved on narrow screens), so a group with a multiple of ``columns`` tiles
    never leaves an orphan tile.
    """
    if columns:
        return html.Div(
            tiles or [],
            className="kpi-grid kpi-grid-fixed",
            style={"--kpi-columns": columns, "--kpi-columns-narrow": max(1, columns // 2)},
            **_id(id),
        )
    return html.Div(tiles or [], className="kpi-grid", **_id(id))


def kpi_group(label: str, tiles: list, columns: int | None = None):
    """Small group label above a KPI grid."""
    return html.Div(
        [html.Div(label, className="group-label"), kpi_grid(tiles, columns=columns)],
        className="kpi-group",
    )


def info_tile(label: str, value):
    """Compact label/value tile for descriptive facts (smaller than a KPI tile)."""
    text = "-" if value is None or value == "" else str(value)
    return html.Div(
        [
            html.Div(label, className="info-label", title=label),
            html.Div(text, className="info-value", title=text),
        ],
        className="info-tile",
    )


def info_row(tiles: list, id: str | None = None):
    """Row of info tiles that wraps when needed."""
    return html.Div(tiles, className="info-row", **_id(id))


def check_tile(label: str, value, status: str = "info", detail: str | None = None):
    """Status tile: label, value and optional detail; ``status`` (ok / warn / info) colors its
    left border and dot. Overflowing text is cut with an ellipsis (full text in the tooltip)."""
    text = "-" if value is None else str(value)
    return html.Div(
        [
            html.Div(
                [html.Span(className="check-dot"), html.Span(label)],
                className="check-label",
                title=label,
            ),
            html.Div(text, className="check-value", title=text),
            html.Div(detail, className="check-detail", title=detail) if detail else None,
        ],
        className=f"check check-{status}",
    )


# ---------- Small pieces ----------


def badge(text: str):
    """Small uppercase tag (e.g. a category name)."""
    return html.Span(text, className="badge")


def note(text: str, id: str | None = None, hidden: bool = False):
    """Dashed informative note (callbacks can toggle its ``hidden`` property)."""
    return html.Div(text, className="note", hidden=hidden, **_id(id))


def field(label: str, control):
    """Inline label followed by an input control (dropdown, date picker...)."""
    return html.Div([html.Span(label, className="field-label"), control], className="field")


def option_card(label: str, meta: str | None = None):
    """Content of a selectable card in an option list: a label and an optional dim meta line."""
    return html.Div(
        [
            html.Div(label, className="option-label"),
            html.Div(meta, className="option-meta") if meta else None,
        ]
    )


def side_panel(title: str, children, actions=None, class_name: str = "sidebar-right"):
    """Side panel with a head (title and optional action components) and its content.

    ``class_name`` places it: ``sidebar-left`` or ``sidebar-right``.
    """
    content = children if isinstance(children, list) else [children]
    actions = actions if isinstance(actions, list) else ([] if actions is None else [actions])
    head = html.Div(
        className="sidebar-head", children=[html.H4(title, className="sidebar-title"), *actions]
    )
    return html.Aside(className=f"sidebar {class_name}", children=[head, *content])


# ---------- Formatting ----------


def format_dt(dt_hours) -> str:
    """Period length(s) in hours (a list in the run inputs) as text, e.g. '15 min' or '1 h'."""
    if not dt_hours:
        return "-"

    def one(hours: float) -> str:
        return f"{hours:g} h" if hours >= 1 else f"{hours * 60:g} min"

    return " / ".join(one(hours) for hours in dt_hours)


def _format_full(value, unit: str, decimals: int) -> tuple[str, str]:
    return ("-" if value is None else f"{value:,.{decimals}f}"), unit


def _id(id: str | None) -> dict:
    return {"id": id} if id else {}
