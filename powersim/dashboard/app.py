"""Local Dash app to browse saved runs.

Layout: a header (title and a free information text); a left panel to pick a tab (tool); a main
area with the selected run's status and the active tab; and a right panel to pick the run, shared
by all tabs. Tabs live in ``tabs/``; styles in ``assets/style.css`` (served by Dash).

The app only reads runs saved with ``SimulationRun.save()``; it never runs simulations.

Usage::

    powersim-dashboard --runs runs        # then open http://127.0.0.1:8050
"""

import argparse
from pathlib import Path

try:
    from dash import Dash, Input, Output, State, dcc, html
except ImportError as error:  # pragma: no cover - depends on the installed extras
    raise ImportError(
        "The dashboard needs the 'dashboard' extra: pip install \"powersim[dashboard]\""
    ) from error

from ..runs import SimulationRun, list_runs
from .components import badge, format_dt, load_run, option_card, side_panel
from .tabs import TABS
from .tabs.base import register_tab

DEFAULT_INFO = (
    "Simulations of energy assets operating in electricity markets. "
    "Pick a tool on the left and a saved run on the right."
)
RUN_INPUT = Input("run-selector", "value")


def create_app(runs_dir: str | Path = "runs", info: str = DEFAULT_INFO) -> Dash:
    """Dash app over the runs saved in ``runs_dir``; ``info`` is the text shown in the header."""
    runs_dir = Path(runs_dir)
    app = Dash(__name__, title="powersim · runs")

    # Tab callbacks only compute while their tab is shown; they need a few stores in the layout.
    tab_stores = {tab.id: register_tab(app, tab, RUN_INPUT) for tab in TABS}

    app.layout = html.Div(
        [
            _header(info),
            html.Div(
                className="shell",
                children=[
                    _tabs_sidebar(),
                    html.Main(
                        className="main",
                        children=[
                            html.Div(id="run-status", className="status-row"),
                            *[
                                html.Div(
                                    [*tab.layout(), *tab_stores[tab.id]],
                                    id=f"tab-{tab.id}",
                                    className="tab-pane",
                                )
                                for tab in TABS
                            ],
                        ],
                    ),
                    _runs_sidebar(runs_dir),
                ],
            ),
        ]
    )

    # Every tab stays in the layout (so its callbacks always have their components); only the
    # selected one is displayed.
    @app.callback(
        *[Output(f"tab-{tab.id}", "style") for tab in TABS],
        Input("tab-selector", "value"),
    )
    def show_tab(selected):
        return [{"display": "flex" if tab.id == selected else "none"} for tab in TABS]

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

    @app.callback(Output("run-status", "children"), RUN_INPUT)
    def show_status(path):
        if not path:
            return html.Div(f"No saved runs in {runs_dir}", className="empty")
        return status_row(load_run(path))

    return app


# ---------- Layout pieces ----------


def _header(info: str):
    return html.Header(
        className="header",
        children=[
            html.Div(
                className="brand",
                children=[
                    html.Div("⚡", className="brand-icon"),
                    html.Div(
                        [
                            html.Div("Simulation runs", className="eyebrow"),
                            html.H3("powersim", className="title"),
                        ]
                    ),
                ],
            ),
            html.Div(info, id="header-info", className="header-info"),
        ],
    )


def _tabs_sidebar():
    options = [{"label": option_card(tab.label, tab.description), "value": tab.id} for tab in TABS]
    selector = dcc.RadioItems(
        id="tab-selector", options=options, value=TABS[0].id, className="option-list"
    )
    return side_panel("Tools", [selector], class_name="sidebar-left")


def _runs_sidebar(runs_dir: Path):
    return side_panel(
        "Simulations",
        [
            html.Div(str(runs_dir.resolve()), className="sidebar-path"),
            dcc.RadioItems(id="run-selector", options=[], value=None, className="option-list"),
        ],
        actions=html.Button("Refresh", id="refresh", className="button"),
        class_name="sidebar-right",
    )


def _run_option_label(row):
    created = (row["created_at"] or "")[:16].replace("T", " ")
    markets = ", ".join(row["markets"]) if row["markets"] else "-"
    return option_card(row["label"] or row["id"], f"{created}  ·  {markets}")


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
        *[badge(market) for market in markets],
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Browse saved powersim runs in a local dashboard.")
    parser.add_argument("--runs", default="runs", help="folder with the saved runs (default: runs)")
    parser.add_argument("--info", default=DEFAULT_INFO, help="information text for the header")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8050)
    parser.add_argument("--debug", action="store_true", help="Dash debug mode (auto-reload)")
    args = parser.parse_args()

    create_app(args.runs, info=args.info).run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
