"""Developer tab: checks of the simulation itself, for the user only while debugging or testing
(energy balance, model limits, simultaneous charge and discharge...). They validate the
optimizer, so they are kept out of the analysis tabs. Notes: ``.claude/dashboard/developer.md``.
"""

import pandas as pd
from dash import Output

from ...runs._series import period_hours, plant_ratings
from ...runs.indicators import all_indicators
from ..components import check_list, load_run, load_timeseries, note, section, stack
from ..formatting import compact_text
from . import overview_data as od
from .base import Tab

TOLERANCE_MW = 1e-6


def layout() -> list:
    return [
        note(
            "Internal checks of the simulation: whether the optimizer result respects the "
            "model (balance, limits). For debugging and testing, not for analysis."
        ),
        section(
            "Simulation checks",
            stack(id="developer-checks"),
            hint="Does the simulation respect the model?",
        ),
    ]


def register(app, run_input) -> None:
    @app.callback(Output("developer-checks", "children"), run_input)
    def show_checks(path):
        return checks_outputs(path)


def checks_outputs(path) -> list:
    """All simulation checks in one card, warnings first, in two columns."""
    if not path:
        return []
    run = load_run(path)
    data = load_timeseries(path)
    checks = simulation_checks(run, data)
    return [check_list(checks, columns=2)] if checks else []


def simulation_checks(run, data: pd.DataFrame) -> list[dict]:
    """Checks of the run against the model inputs, of the reserve band against the assets and
    the indicator-based ones (exports at price ≤ 0)."""
    results = all_indicators(run.inputs, run.kpis, data, run.market_data)
    prices = results["negative_prices"]
    battery_power = plant_ratings(run.inputs)["battery_power"] or 0.0
    checks = od.run_checks(run.inputs, run.kpis, data)
    checks += [
        check
        for check in (band_backing_check(data, battery_power), activation_check(data))
        if check is not None
    ]
    return checks + od.indicator_checks(
        prices.kpis if prices.available else None, run.kpis.get("energy_exported_MWh")
    )


def band_backing_check(data: pd.DataFrame, battery_power: float) -> dict | None:
    """Reserve band (up or down, all markets) above what the assets could deliver if fully
    activated: battery power + PV output of the period. The model does not limit it yet
    (``.claude/TODO.md``), so a plant without assets can still sell band. None without bands."""
    up, down = _total(data, "Band_up_"), _total(data, "Band_down_")
    if up is None and down is None:
        return None
    band = pd.concat([b for b in (up, down) if b is not None], axis=1).max(axis=1)
    offered = band > TOLERANCE_MW
    if not offered.any():
        return None
    backing = battery_power + (data["P_generation"] if "P_generation" in data else 0.0)
    excess = (band - backing).where(offered, 0.0)
    above = excess > TOLERANCE_MW
    label = "Reserve band backed by the assets"
    detail = (
        f"band ≤ battery {battery_power:g} MW + PV output · {offered.mean():.0%} of time with band"
    )
    if not above.any():
        return {"label": label, "value": "always backed", "status": "ok", "detail": detail}
    value = f"{above.sum() / offered.sum():.0%} of band periods above"
    detail = f"largest excess {excess.max():.2f} MW · " + detail
    return {"label": label, "value": value, "status": "warn", "detail": detail}


def activation_check(data: pd.DataFrame) -> dict | None:
    """Reserve activations (``P_up_*`` / ``P_down_*``) within the band offered in the same
    direction and market. None without bands."""
    markets = [c.removeprefix("Band_up_") for c in data.columns if c.startswith("Band_up_")]
    if not markets:
        return None
    dt = period_hours(data.index)
    parts, energy = [], 0.0
    for direction in ("up", "down"):
        periods = 0
        for market in markets:
            activation = data.get(f"P_{direction}_{market}")
            band = data.get(f"Band_{direction}_{market}")
            if activation is None or band is None:
                continue
            over = (activation.abs() - band.abs()).clip(lower=0.0)  # down is stored < 0
            periods += int((over > TOLERANCE_MW).sum())
            energy += float((over * dt).sum())
        if periods:
            parts.append(f"{direction} {periods} periods")
    label = "Reserve activation within the offered band"
    if not parts:
        return {"label": label, "value": "always within", "status": "ok", "detail": None}
    detail = f"{compact_text(energy, 'MWh')} activated above the band · " + " · ".join(parts)
    return {"label": label, "value": "activation above band", "status": "warn", "detail": detail}


def _total(data: pd.DataFrame, prefix: str) -> pd.Series | None:
    columns = [c for c in data.columns if c.startswith(prefix)]
    return data[columns].abs().sum(axis=1) if columns else None  # down bands are stored < 0


TAB = Tab(
    id="developer",
    label="Developer",
    description="Simulation checks for debugging",
    layout=layout,
    register=register,
)
