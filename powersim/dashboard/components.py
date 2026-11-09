"""Generic UI components shared by the dashboard shell and tabs, plus run loading and formatting.

Components receive plain data (labels, numbers, units, Dash children) and know nothing about
runs, markets or batteries; turning run data into their inputs is the job of the tabs. Styles
live in ``assets/style.css``.
"""

import math
from functools import lru_cache

from dash import dcc, html

from ..runs import SimulationRun
from .figures import fit_height
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
    figure=None,
    footnote: str | None = None,
):
    """Card with a title, a short hint (what it shows, units) and a graph ``height`` px tall.

    ``footnote_id`` adds an empty footnote below the graph, to be filled by a callback.
    ``dynamic_head=True`` gives the title and hint the ids ``<graph_id>-title`` and
    ``<graph_id>-hint`` so callbacks can change them. ``figure`` / ``footnote`` fill the card
    directly, for cards built inside a callback; the figure height is set to ``height``.
    """
    if figure is not None and getattr(figure, "layout", None) is not None:
        if figure.layout.height != height:  # the svg must match the container height
            fit_height(figure, height)
    graph = dcc.Graph(
        id=graph_id,
        config=GRAPH_CONFIG,
        style={"height": f"{height}px"},
        **({"figure": figure} if figure is not None else {}),
    )
    footnote = (
        [html.Div(footnote, className="card-footnote", **_id(footnote_id))]
        if footnote_id or footnote
        else []
    )
    ids = {"title_id": f"{graph_id}-title", "hint_id": f"{graph_id}-hint"} if dynamic_head else {}
    return card(title, hint, [graph, *footnote], **ids)


def section(title: str, children, hint: str | None = None, id: str | None = None):
    """Heading (and optional hint) followed by its cards, to group related content. With an
    ``id`` the section can be the target of a ``link_tile``."""
    content = children if isinstance(children, list) else [children]
    head = html.Div(
        className="section-head",
        children=[
            html.H3(title, className="section-title"),
            html.Span(hint, className="section-hint") if hint else None,
        ],
    )
    return html.Div(className="section", children=[head, *content], **_id(id))


def stack(children: list | None = None, id: str | None = None):
    """Vertical stack of blocks with the standard gap."""
    return html.Div(children or [], className="stack", **_id(id))


def columns(
    children: list,
    widths: list[float] | None = None,
    id: str | None = None,
    align_start: bool = False,
):
    """Side-by-side columns (relative ``widths``, equal by default); one column on narrow screens.

    By default every column stretches to the tallest one (charts in a row line up);
    ``align_start=True`` keeps each column at its natural height, so a short card is not
    stretched into a half-empty box. Like every container with an ``id``, callbacks can hide
    it with its ``hidden`` property.
    """
    widths = widths or [1] * len(children)
    template = " ".join(f"minmax(0, {width}fr)" for width in widths)
    class_name = "columns columns-start" if align_start else "columns"
    return html.Div(children, className=class_name, style={"--columns": template}, **_id(id))


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
            [text, html.Span(unit, className="kpi-unit") if unit and value is not None else None],
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


# ---------- Compact data blocks ----------

STATUSES = ("ok", "warn", "info")


def format_value(value, unit: str = "", decimals: int = 1, compact: bool = False) -> tuple:
    """(text, unit, full text) of a value: ``compact`` shortens large values (see
    ``format_compact``), the full text is meant for tooltips. Strings pass through unchanged
    and ``None`` gives '-'."""
    if isinstance(value, str):
        return value, unit, f"{value} {unit}".strip()
    full_text, _ = _format_full(value, unit, decimals)
    text, shown_unit = format_compact(value, unit, decimals) if compact else (full_text, unit)
    if value is None:
        shown_unit = ""
    return text, shown_unit, f"{full_text} {unit}".strip() if value is not None else "-"


def hero_strip(items: list[dict], id: str | None = None):
    """One card with 2-4 big numbers inline, separated by thin vertical dividers.

    Each item: ``label``, ``value``, ``unit`` and optionally ``decimals`` (1), ``compact``
    (False), ``sub`` (dim line below) and ``primary`` (accent colour).
    """
    children = []
    for item in items:
        text, unit, full = format_value(
            item.get("value"), item.get("unit", ""), item.get("decimals", 1), item.get("compact")
        )
        sub = item.get("sub")
        children.append(
            html.Div(
                [
                    html.Div(item["label"], className="hero-label", title=item["label"]),
                    html.Div(
                        [text, html.Span(unit, className="hero-unit") if unit else None],
                        className="hero-value",
                        title=full,
                    ),
                    html.Div(sub, className="hero-sub", title=sub) if sub else None,
                ],
                className="hero-item hero-primary" if item.get("primary") else "hero-item",
            )
        )
    return html.Section(children, className="card hero-strip", **_id(id))


def stat_row(
    label: str,
    value,
    unit: str = "",
    decimals: int = 1,
    compact: bool = False,
    sub: str | None = None,
    status: str | None = None,
    primary: bool = False,
    title: str | None = None,
) -> dict:
    """One row of a ``stat_list`` (a plain dict, so tabs can build and test rows without Dash).

    ``sub``: dim line under the label; ``status`` (ok / warn / info): coloured dot before the
    label (warn also colours the value); ``primary``: value in the accent colour; ``title``:
    tooltip of the row (e.g. a formula).
    """
    return {
        "label": label,
        "value": value,
        "unit": unit,
        "decimals": decimals,
        "compact": compact,
        "sub": sub,
        "status": status,
        "primary": primary,
        "title": title,
    }


def stat_list(
    title: str | None,
    rows: list[dict],
    hint: str = "",
    columns: int = 1,
    footnote: str | None = None,
    id: str | None = None,
):
    """Card with compact rows "label ...... value unit" (value right-aligned, mono).

    ``rows`` are ``stat_row`` dicts. ``columns`` > 1 fills the rows column by column (top to
    bottom, then the next column; ceil(n / columns) rows per column), one column on narrow
    screens. ``footnote`` adds a dim line at the bottom.
    """
    extra = [html.Div(footnote, className="card-footnote")] if footnote else []
    return card(title, hint, [_stat_body(rows, columns), *extra], id=id)


def _stat_body(rows: list[dict], columns: int = 1):
    columns = max(1, columns)
    per_column = max(1, math.ceil(len(rows) / columns))
    return html.Div(
        [_stat_row(row) for row in rows],
        className="stat-list stat-list-flow" if columns > 1 else "stat-list",
        style={"--stat-columns": columns, "--stat-rows": per_column},
    )


def _stat_row(row: dict):
    text, unit, full = format_value(row["value"], row["unit"], row["decimals"], row["compact"])
    status = row.get("status")
    classes = ["stat-row"]
    if status in STATUSES:
        classes.append(f"stat-{status}")
    if row.get("primary"):
        classes.append("stat-primary")
    sub = row.get("sub")
    return html.Div(
        [
            html.Span(className="stat-dot") if status in STATUSES else None,
            html.Div(
                [
                    html.Div(row["label"], className="stat-label"),
                    html.Div(sub, className="stat-sub") if sub else None,
                ],
                className="stat-text",
            ),
            html.Div(
                [text, html.Span(unit, className="stat-unit") if unit else None],
                className="stat-value",
                title=full,
            ),
        ],
        className=" ".join(classes),
        title=row.get("title") or " · ".join(p for p in (row["label"], sub) if p),
    )


STATUS_NAMES = {"warn": ("warning", "warnings"), "ok": ("ok", "ok"), "info": ("info", "info")}


def status_summary(statuses: list[str], names: dict[str, tuple[str, str]] | None = None):
    """One line counting statuses, e.g. "1 warning · 4 ok · 2 info" (only non-zero counts,
    warnings first and in the warning colour). ``names`` overrides the (singular, plural)
    words per status, e.g. ``{"warn": ("limiting", "limiting")}``."""
    names = STATUS_NAMES | (names or {})
    parts = []
    for status in ("warn", "ok", "info"):
        count = sum(1 for s in statuses if s == status)
        if not count:
            continue
        if parts:
            parts.append(html.Span(" · ", className="status-sep"))
        word = names[status][0] if count == 1 else names[status][1]
        parts.append(html.Span(f"{count} {word}", className=f"status-count status-{status}"))
    return html.Div(parts, className="status-summary")


def check_list(
    checks: list[dict],
    columns: int = 2,
    warn_first: bool = True,
    summary: bool = True,
    id=None,
    summary_names: dict[str, tuple[str, str]] | None = None,
):
    """One card of checks, each a compact row: status dot · label · value (warn coloured) and
    the detail as a dim line. ``checks`` take the ``check_tile`` arguments (label, value,
    status, detail; ``status=None`` gives a row without dot, left out of the summary); with
    ``warn_first`` the warnings come first (order kept otherwise); ``summary`` adds a
    ``status_summary`` line on top (``summary_names``: its words per status)."""
    ordered = sorted(checks, key=lambda c: c.get("status") != "warn") if warn_first else checks
    rows = [
        stat_row(
            check["label"],
            "-" if check.get("value") is None else str(check["value"]),
            sub=check.get("detail"),
            status=check.get("status", "info"),
        )
        for check in ordered
    ]
    head = [status_summary([row["status"] for row in rows], summary_names)] if summary else []
    return card(None, "", [*head, _stat_body(rows, columns)], id=id)


def data_table(
    columns: list[str],
    rows: list[dict],
    title: str | None = None,
    hint: str = "",
    id: str | None = None,
):
    """Compact table in a card: dim header row, thin row separators, row label column on the
    left (optional colour swatch), other columns right-aligned in mono.

    ``columns``: header texts, the first one for the label column. ``rows``: dicts with
    ``label``, optional ``color`` (swatch) and ``cells`` (one per remaining column). A cell is
    a value (str / number / None → '-') or a dict with ``value`` and optional ``sub`` (dim
    small text below), ``status`` (ok / warn / info: colours the sub) and ``title``
    (tooltip).
    """
    head = html.Thead(
        html.Tr(
            [
                html.Th(text, className="table-label" if i == 0 else "table-num")
                for i, text in enumerate(columns)
            ]
        )
    )
    body = html.Tbody([_table_row(row) for row in rows])
    table = html.Table([head, body], className="data-table")
    return card(title, hint, html.Div(table, className="table-scroll"), id=id)


def _table_row(row: dict):
    swatch = (
        html.Span(className="table-swatch", style={"background": row["color"]})
        if row.get("color")
        else None
    )
    label = html.Td([swatch, html.Span(row["label"])], className="table-label")
    return html.Tr([label, *[_table_cell(cell) for cell in row.get("cells", [])]])


def _table_cell(cell):
    cell = cell if isinstance(cell, dict) else {"value": cell}
    value = cell.get("value")
    text = "-" if value is None or value == "" else str(value)
    status = cell.get("status")
    sub = cell.get("sub")
    return html.Td(
        [
            html.Div(text, className="table-value"),
            html.Div(
                sub,
                className=f"table-sub table-{status}" if status in STATUSES else "table-sub",
            )
            if sub
            else None,
        ],
        className="table-num",
        title=cell.get("title"),
    )


def spec_card(groups: list[dict], id: str | None = None):
    """One card of specification groups side by side (thin dividers between them; they wrap
    to a new line on narrow screens).

    Each group: ``title``, optional ``color`` (swatch), optional ``subtitle`` (dim, e.g. a
    name) and ``rows``: ``stat_row`` dicts shown as compact "label  value" lines (``value``,
    ``unit``, ``decimals``, ``compact`` and ``title`` (tooltip) are used; ``sub`` is not
    shown), plus optional per-row ``color`` (swatch before the label) and ``indent`` (dim,
    indented secondary line, e.g. a detail of the row above).
    """
    return html.Section(
        [_spec_group(group) for group in groups], className="card spec-card", **_id(id)
    )


def _spec_group(group: dict):
    swatch = (
        html.Span(className="spec-swatch", style={"background": group["color"]})
        if group.get("color")
        else None
    )
    subtitle = group.get("subtitle")
    head = html.Div(
        [
            swatch,
            html.Span(group["title"], className="spec-title"),
            html.Span(subtitle, className="spec-subtitle", title=subtitle) if subtitle else None,
        ],
        className="spec-head",
    )
    rows = []
    for row in group.get("rows", []):
        text, unit, full = format_value(
            row.get("value"), row.get("unit", ""), row.get("decimals", 1), row.get("compact")
        )
        value = f"{text} {unit}".strip()
        rows.append(
            html.Div(
                [
                    html.Span(
                        [
                            html.Span(className="spec-swatch", style={"background": row["color"]})
                            if row.get("color")
                            else None,
                            row["label"],
                        ],
                        className="spec-label",
                    ),
                    html.Span(value, className="spec-value"),
                ],
                className="spec-row spec-row-indent" if row.get("indent") else "spec-row",
                title=row.get("title") or f"{row['label']}: {full}",
            )
        )
    return html.Div([head, *rows], className="spec-group")


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


def link_tile(tile, target_id: str):
    """Make a tile (KPI, check...) a link to the element ``target_id`` on the same page."""
    return html.A(tile, href=f"#{target_id}", className="tile-link")


def footnote(text: str):
    """Small dim footnote line (e.g. under a group of tiles)."""
    return html.Div(text, className="card-footnote")


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
