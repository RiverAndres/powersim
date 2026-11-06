"""Building blocks shared by the dashboard tabs: run loading, cards and formatting."""

from functools import lru_cache

from dash import dcc, html

from ..runs import SimulationRun

# "responsive" makes the figure follow its container (width when a hidden tab is shown, window
# resizes). The container must have an explicit height, or the graph collapses: chart_card sets it.
GRAPH_CONFIG = {"displaylogo": False, "responsive": True}
EMPTY_FIGURE = {"layout": {"paper_bgcolor": "rgba(0,0,0,0)", "plot_bgcolor": "rgba(0,0,0,0)"}}


@lru_cache(maxsize=16)
def load_run(path: str) -> SimulationRun:
    return SimulationRun.load(path)


def chart_card(graph_id: str, title: str, hint: str = "", height: int = 400):
    """Card with a title, a short hint (what it shows, units) and a graph ``height`` px tall."""
    return html.Section(
        className="card",
        children=[
            html.Div(
                className="card-head",
                children=[
                    html.H4(title, className="card-title"),
                    html.Span(hint, className="card-hint"),
                ],
            ),
            dcc.Graph(id=graph_id, config=GRAPH_CONFIG, style={"height": f"{height}px"}),
        ],
    )


def kpi(label: str, value, unit: str, decimals: int = 1, primary=False, sub=None):
    """KPI card: label, value with its unit and an optional sub-line."""
    text = "-" if value is None else f"{value:,.{decimals}f}"
    children = [
        html.Div(label, className="kpi-label"),
        html.Div(
            [text, html.Span(unit, className="kpi-unit") if unit else None],
            className="kpi-value",
        ),
    ]
    if sub:
        children.append(html.Div(sub, className="kpi-sub"))
    return html.Div(children, className="kpi kpi-primary" if primary else "kpi")


def status_row(run: SimulationRun) -> list:
    """Run name, period, resolution, optimizer and one badge per market."""
    period = run.inputs.get("period", {})
    markets = [market["type"] for market in run.inputs.get("markets", [])]
    meta = (
        f"{period.get('start', '')[:10]} → {period.get('end', '')[:10]}"
        f"  ·  {period.get('n_periods', '-')} periods of {format_dt(period.get('dt_hours'))}"
        f"  ·  {run.manifest.get('optimizer', '-')}"
    )
    return [
        html.Span(className="pulse"),
        html.H2(run.label or run.id, className="run-title"),
        html.Span(meta, className="status-meta"),
        *[html.Span(market, className="badge") for market in markets],
    ]


def format_dt(dt_hours) -> str:
    """Period length(s) in hours (a list in the run inputs) as text, e.g. '15 min' or '1 h'."""
    if not dt_hours:
        return "-"

    def one(hours: float) -> str:
        return f"{hours:g} h" if hours >= 1 else f"{hours * 60:g} min"

    return " / ".join(one(hours) for hours in dt_hours)
