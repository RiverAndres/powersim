"""Sandbox tab: experiments to decide what the dashboard should show.

Everything here is provisional. When an experiment is approved, its figure moves to
``figures.py`` and its card to the tab where it belongs; then it is removed from here.
Notes and decisions: ``.claude/dashboard/sandbox.md``.
"""

import pandas as pd
import plotly.graph_objects as go
from dash import Output, html

from ..components import EMPTY_FIGURE, chart_card, load_run
from ..figures import apply_theme, series_color
from .base import Tab

REVENUE_PREFIX = "B_benefit_"
SOC_PREFIX = "SOC_"

# (graph id, card title, card hint, height in px)
EXPERIMENTS = [
    ("sandbox-daily-revenue", "Daily revenue by market", "Experiment · € per day, stacked", 360),
    (
        "sandbox-soc-heatmap",
        "Battery state of charge",
        "Experiment · mean SOC by day and hour",
        360,
    ),
]


def layout() -> list:
    intro = html.Div(
        "Sandbox: experimental views to decide what the dashboard should show. "
        "Approved views move to their own tab.",
        className="sandbox-note",
    )
    return [intro, *[chart_card(*card) for card in EXPERIMENTS]]


def register(app, run_input) -> None:
    @app.callback(
        *[Output(graph_id, "figure") for graph_id, *_ in EXPERIMENTS],
        run_input,
    )
    def show_run(path):
        if not path:
            return EMPTY_FIGURE, EMPTY_FIGURE
        data = load_run(path).timeseries_wide()
        return daily_revenue_figure(data), soc_heatmap_figure(data)


def daily_revenue_figure(data: pd.DataFrame) -> go.Figure:
    """Revenue per day and market (sum of B_benefit_* per day), stacked bars."""
    fig = go.Figure()
    columns = [c for c in data.columns if c.startswith(REVENUE_PREFIX)]
    daily = data[columns].resample("D").sum()
    for column in columns:
        market = column.removeprefix(REVENUE_PREFIX)
        fig.add_trace(
            go.Bar(
                x=daily.index,
                y=daily[column],
                name=market,
                marker_color=series_color(f"p_{market}"),
            )
        )
    fig.update_layout(barmode="relative")
    fig.update_yaxes(title_text="€")
    return apply_theme(fig, height=360)


def soc_heatmap_figure(data: pd.DataFrame) -> go.Figure:
    """Mean SOC of all batteries (0-1) as a heatmap: day on x, hour of day on y."""
    fig = go.Figure()
    columns = [c for c in data.columns if c.startswith(SOC_PREFIX)]
    if columns:
        soc = data[columns].mean(axis=1)
        grid = (
            soc.groupby([soc.index.normalize(), soc.index.hour])
            .mean()
            .unstack(level=0)
            .sort_index()
        )
        fig.add_trace(
            go.Heatmap(
                x=grid.columns,
                y=grid.index,
                z=grid.to_numpy(),
                zmin=0,
                zmax=1,
                colorscale="Viridis",
                colorbar={"title": "SOC"},
                hovertemplate="%{x|%Y-%m-%d} %{y}:00<br>SOC %{z:.0%}<extra></extra>",
            )
        )
    fig.update_yaxes(title_text="Hour", dtick=3)
    fig = apply_theme(fig, height=360)
    fig.update_layout(hovermode="closest")
    return fig


TAB = Tab(
    id="sandbox",
    label="Sandbox",
    description="Experiments for new views",
    layout=layout,
    register=register,
)
