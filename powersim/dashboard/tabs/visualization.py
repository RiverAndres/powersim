"""Visualization tab: main KPIs and the operation charts of the selected run."""

from dash import Output, html

from ..components import EMPTY_FIGURE, chart_card, kpi, load_run
from ..figures import assets_figure, excess_figure, markets_figure
from .base import Tab

# (graph id, card title, card hint, height in px)
CHART_CARDS = [
    ("visualization-assets", "Assets", "Generation, storage and power at the POI · MW", 720),
    ("visualization-markets", "Markets", "Prices and operation per market", 620),
    ("visualization-excess", "Excess power", "Power that cannot be exported · MW", 280),
]


def layout() -> list:
    return [
        html.Div(id="visualization-kpis", className="kpi-grid"),
        *[chart_card(*card) for card in CHART_CARDS],
    ]


def register(app, run_input) -> None:
    @app.callback(
        Output("visualization-kpis", "children"),
        *[Output(graph_id, "figure") for graph_id, *_ in CHART_CARDS],
        run_input,
    )
    def show_run(path):
        if not path:
            return [], EMPTY_FIGURE, EMPTY_FIGURE, EMPTY_FIGURE
        run = load_run(path)
        return kpi_cards(run), assets_figure(run), markets_figure(run), excess_figure(run)


def kpi_cards(run) -> list:
    kpis = run.kpis
    revenue_total = kpis.get("revenue_total")
    cards = [kpi("Total revenue", revenue_total, "€", decimals=0, primary=True)]
    for market, value in kpis.get("revenue_by_market", {}).items():
        share = (
            f"{value / revenue_total:.0%} of total" if value is not None and revenue_total else None
        )
        cards.append(kpi(f"Revenue {market}", value, "€", decimals=0, sub=share))
    cards += [
        kpi("Energy exported", kpis.get("energy_exported_MWh"), "MWh"),
        kpi("Energy imported", kpis.get("energy_imported_MWh"), "MWh"),
        kpi("Energy charged", kpis.get("energy_charged_MWh"), "MWh"),
        kpi("Energy discharged", kpis.get("energy_discharged_MWh"), "MWh"),
        kpi("Equivalent cycles", kpis.get("equivalent_cycles"), "", decimals=2),
        kpi("Excess energy", kpis.get("excess_energy_MWh"), "MWh"),
    ]
    return cards


TAB = Tab(
    id="visualization",
    label="Visualization",
    description="KPIs and operation of a run",
    layout=layout,
    register=register,
)
