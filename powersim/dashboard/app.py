"""Local Dash app to browse saved runs: side panel to pick a run, main area with its charts.

The app only reads runs saved with ``SimulationRun.save()``; it never runs simulations.

Usage::

    powersim-dashboard --runs runs        # then open http://127.0.0.1:8050
"""

import argparse
from functools import lru_cache
from pathlib import Path

try:
    from dash import Dash, Input, Output, State, dcc, html
except ImportError as error:  # pragma: no cover - depends on the installed extras
    raise ImportError(
        "The dashboard needs the 'dashboard' extra: pip install \"powersim[dashboard]\""
    ) from error

import plotly.graph_objects as go

from ..runs import SimulationRun, list_runs
from .figures import assets_figure, excess_figure, markets_figure

SIDEBAR_STYLE = {
    "width": "320px",
    "flexShrink": 0,
    "padding": "16px",
    "borderRight": "1px solid #ddd",
    "height": "100vh",
    "overflowY": "auto",
    "boxSizing": "border-box",
    "fontFamily": "sans-serif",
    "fontSize": "14px",
}
MAIN_STYLE = {"flexGrow": 1, "padding": "16px", "overflowY": "auto", "height": "100vh"}


def create_app(runs_dir: str | Path = "runs") -> Dash:
    runs_dir = Path(runs_dir)
    app = Dash(__name__, title="powersim runs")

    app.layout = html.Div(
        style={"display": "flex"},
        children=[
            html.Div(
                style=SIDEBAR_STYLE,
                children=[
                    html.H3("Simulations", style={"marginTop": 0}),
                    html.Div(str(runs_dir.resolve()), style={"color": "#888", "fontSize": "12px"}),
                    html.Button("Refresh", id="refresh", style={"margin": "8px 0"}),
                    dcc.RadioItems(
                        id="run-selector",
                        options=[],
                        value=None,
                        labelStyle={"display": "block", "marginBottom": "8px"},
                    ),
                    html.Hr(),
                    html.Div(id="run-kpis"),
                ],
            ),
            html.Div(
                style=MAIN_STYLE,
                children=[
                    html.H2(id="run-title", style={"fontFamily": "sans-serif", "marginTop": 0}),
                    dcc.Graph(id="assets-graph"),
                    dcc.Graph(id="markets-graph"),
                    dcc.Graph(id="excess-graph"),
                ],
            ),
        ],
    )

    @app.callback(
        Output("run-selector", "options"),
        Output("run-selector", "value"),
        Input("refresh", "n_clicks"),
        State("run-selector", "value"),
    )
    def refresh_runs(_n_clicks, current):
        catalog = list_runs(runs_dir)
        options = [
            {"label": _run_option_label(row), "value": row["path"]} for _, row in catalog.iterrows()
        ]
        paths = [option["value"] for option in options]
        value = current if current in paths else (paths[0] if paths else None)
        return options, value

    @app.callback(
        Output("run-title", "children"),
        Output("run-kpis", "children"),
        Output("assets-graph", "figure"),
        Output("markets-graph", "figure"),
        Output("excess-graph", "figure"),
        Input("run-selector", "value"),
    )
    def show_run(path):
        if not path:
            empty = go.Figure()
            return f"No saved runs in {runs_dir}", "", empty, empty, empty
        run = _load_run(path)
        title = run.label or run.id
        return title, _kpis_panel(run), assets_figure(run), markets_figure(run), excess_figure(run)

    return app


@lru_cache(maxsize=16)
def _load_run(path: str) -> SimulationRun:
    return SimulationRun.load(path)


def _run_option_label(row) -> str:
    created = (row["created_at"] or "")[:16].replace("T", " ")
    markets = ", ".join(row["markets"]) if row["markets"] else "-"
    return f"{row['label'] or row['id']}  ·  {created}  ·  {markets}"


def _kpis_panel(run: SimulationRun):
    kpis = run.kpis
    period = run.inputs.get("period", {})

    def fmt(value, unit, decimals=1):
        return "-" if value is None else f"{value:,.{decimals}f} {unit}"

    rows = [("Total revenue", fmt(kpis.get("revenue_total"), "EUR", 0))]
    rows += [
        (f"  {market}", fmt(value, "EUR", 0))
        for market, value in kpis.get("revenue_by_market", {}).items()
    ]
    rows += [
        ("Exported", fmt(kpis.get("energy_exported_MWh"), "MWh")),
        ("Imported", fmt(kpis.get("energy_imported_MWh"), "MWh")),
        ("Charged", fmt(kpis.get("energy_charged_MWh"), "MWh")),
        ("Discharged", fmt(kpis.get("energy_discharged_MWh"), "MWh")),
        ("Equivalent cycles", fmt(kpis.get("equivalent_cycles"), "", 2)),
        ("Excess", fmt(kpis.get("excess_energy_MWh"), "MWh")),
        ("Period", f"{period.get('start', '')[:10]} → {period.get('end', '')[:10]}"),
        ("Optimizer", run.manifest.get("optimizer", "-")),
    ]
    return html.Table(
        [
            html.Tr([html.Td(name), html.Td(value, style={"textAlign": "right"})])
            for name, value in rows
        ],
        style={"width": "100%"},
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Browse saved powersim runs in a local dashboard.")
    parser.add_argument("--runs", default="runs", help="folder with the saved runs (default: runs)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8050)
    parser.add_argument("--debug", action="store_true", help="Dash debug mode (auto-reload)")
    args = parser.parse_args()

    create_app(args.runs).run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
