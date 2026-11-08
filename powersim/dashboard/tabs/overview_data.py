"""Pure computations behind the Visualization tab (no Dash): plant ratings, energy flows,
captured prices, daily cycles, sanity checks, series labels and time windows.

Inputs are a run's ``inputs`` / ``kpis`` dicts and its wide time series (one column per
variable). Series are selected by variable prefix, never by market name.
"""

from dataclasses import dataclass

import pandas as pd

from ..formatting import compact_text

REVENUE_PREFIX = "B_benefit_"
REVENUE_STREAM_PREFIX = "B_"
ENERGY_PREFIX = "E_"
PRICE_PREFIX = "p_"
SOC_PREFIX = "SOC_"
MARKET_ENERGY_PREFIXES = ("E_sell_", "E_buy_", "E_up_", "E_down_")
SYSTEM_SELL_PREFIX = "E_system_sell_"
DETAIL_DAYS = 7
SMALL_SHARE = 0.005  # bars below 0.5% of the reference are hidden (listed in a footnote)

# Energy flows between PV, battery and grid: (label, variable, color key, side). Charges are
# stored negative in the run; flows are positive energies. Side: +1 export, -1 battery charge.
FLOWS = [
    ("PV → grid", "E_system_sell_generation", "pv_to_grid", 1),
    ("Battery → grid", "E_system_sell_storage", "battery_to_grid", 1),
    ("PV → battery", "E_storage_charge_generation", "pv_to_battery", -1),
    ("Grid → battery", "E_storage_charge_grid", "grid_to_battery", -1),
]

# Human labels of operation series in the detail charts: fixed names, then "<market> <what>"
# by prefix (longest prefixes first).
SERIES_LABELS = {
    "P_generation": "PV generation",
    "P_storage_charge": "Battery charge",
    "P_storage_discharge": "Battery discharge",
    "P_system_export": "Grid export",
    "P_system_import": "Grid import",
    "P_excess": "Curtailment",
}
SERIES_PREFIX_LABELS = [
    ("p_act_up_", "activation up price"),
    ("p_act_down_", "activation down price"),
    ("p_up_", "band up price"),
    ("p_down_", "band down price"),
    ("p_", "price"),
    ("P_sell_", "sell"),
    ("P_buy_", "buy"),
    ("P_up_", "activation up"),
    ("P_down_", "activation down"),
    ("Band_up_", "band up"),
    ("Band_down_", "band down"),
]

# Checks thresholds.
BALANCE_TOLERANCE = 0.001  # largest node imbalance, share of the energy entering the system
EXPORT_TOLERANCE = 0.001  # relative difference between the two export measures
CURTAILMENT_WARNING = 0.05  # share of PV generation


# ---------- Period ----------


@dataclass(frozen=True)
class PeriodRule:
    """How to aggregate a run over time: pandas rule, noun, time format and the length of one
    period (``offset``)."""

    rule: str
    noun: str
    x_format: str
    offset: pd.DateOffset


MONTHLY = PeriodRule("MS", "month", "%b %Y", pd.DateOffset(months=1))
WEEKLY = PeriodRule("W-MON", "week", "%d %b %Y", pd.DateOffset(days=7))
DAILY = PeriodRule("D", "day", "%d %b", pd.DateOffset(days=1))


def period_rule(index: pd.DatetimeIndex) -> PeriodRule:
    """Monthly for runs longer than 90 days, weekly above 21 days, daily otherwise."""
    days = (index.max() - index.min()).days + 1 if len(index) else 0
    if days > 90:
        return MONTHLY
    if days > 21:
        return WEEKLY
    return DAILY


def aggregate(frame: pd.DataFrame, rule: PeriodRule) -> pd.DataFrame:
    """Sum of ``frame`` per period (weeks labelled by their Monday)."""
    if rule is WEEKLY:
        return frame.resample(rule.rule, label="left", closed="left").sum()
    return frame.resample(rule.rule).sum()


def partial_periods(index: pd.DatetimeIndex, rule: PeriodRule) -> pd.Series:
    """Per aggregated period, a note for periods the run does not fully cover (usually the
    first and last), e.g. "partial · 1 of 30 days"; "" for complete periods."""
    if len(index) == 0:
        return pd.Series(dtype=str)
    covered = aggregate(period_hours(index).to_frame("hours"), rule)["hours"]
    notes = {}
    for start, hours in covered.items():
        length = ((start + rule.offset) - start).total_seconds() / 3600
        if hours >= length - 0.5:
            notes[start] = ""
        elif rule is DAILY:
            notes[start] = f"partial · {hours:.0f} of {length:.0f} h"
        else:
            notes[start] = f"partial · {hours / 24:.0f} of {length / 24:.0f} days"
    return pd.Series(notes, dtype=str)


def period_hours(index: pd.DatetimeIndex) -> pd.Series:
    """Length of each period in hours (the last one repeats the previous)."""
    if len(index) < 2:
        return pd.Series(1.0, index=index)
    hours = pd.Series(index, index=index).diff().shift(-1).dt.total_seconds() / 3600
    return hours.fillna(hours.iloc[-2])


def period_days(period: dict) -> float | None:
    """Length of the simulated period in days (from ``run.inputs['period']``)."""
    dt_hours = period.get("dt_hours") or []
    n_periods = period.get("n_periods")
    if len(dt_hours) == 1 and n_periods:
        return n_periods * dt_hours[0] / 24
    if period.get("start") and period.get("end"):
        span = pd.Timestamp(period["end"]) - pd.Timestamp(period["start"])
        return span.total_seconds() / 86400 + (min(dt_hours) / 24 if dt_hours else 0)
    return None


# ---------- Plant ----------


def plant_ratings(inputs: dict) -> dict:
    """Rated PV peak power (MW), battery power (MW) and capacity (MWh); None when unknown."""
    batteries = inputs.get("batteries", [])
    return {
        "pv_peak": _sum_known(g.get("peak_power") for g in inputs.get("generators", [])),
        "battery_power": _sum_known(_battery_power(b) for b in batteries),
        "battery_capacity": _sum_known(b.get("capacity") for b in batteries),
    }


def has_pv(inputs: dict, data: pd.DataFrame) -> bool:
    """The run has generation: a generator in the inputs or any non-zero ``P_generation``."""
    generating = "P_generation" in data and bool((data["P_generation"].abs() > 1e-9).any())
    return bool(inputs.get("generators")) or generating


def has_battery(inputs: dict) -> bool:
    return bool(inputs.get("batteries"))


def energy(data: pd.DataFrame, variable: str) -> float:
    """Absolute energy (MWh) of a power variable over the run (power × period length)."""
    if variable not in data:
        return 0.0
    return abs(float((data[variable] * period_hours(data.index)).sum()))


# ---------- Prices and revenues ----------


def markets(data: pd.DataFrame) -> list[str]:
    """Markets of the run (suffixes of the ``B_benefit_*`` columns)."""
    return [c.removeprefix(REVENUE_PREFIX) for c in data.columns if c.startswith(REVENUE_PREFIX)]


def by_market(data: pd.DataFrame, prefix: str) -> pd.DataFrame:
    """Columns starting with ``prefix``, renamed to their market."""
    selected = [c for c in data.columns if c.startswith(prefix)]
    return data[selected].rename(columns=lambda c: c.removeprefix(prefix))


def captured_prices(data: pd.DataFrame) -> list[dict]:
    """Average captured price per market and direction: ``B_<dir>_<m>`` / ``E_<dir>_<m>``.

    Pairs with (almost) no energy are skipped. ``market_avg`` is the time-average market price
    ``p_<m>`` (None if missing). Items: ``market, direction, price, market_avg`` (€/MWh).
    """
    prices = []
    for market in markets(data):
        for column in data.columns:
            if not (column.startswith(ENERGY_PREFIX) and column.endswith(f"_{market}")):
                continue
            direction = column.removeprefix(ENERGY_PREFIX).removesuffix(f"_{market}")
            revenue_column = f"{REVENUE_STREAM_PREFIX}{direction}_{market}"
            total_energy = float(data[column].sum())
            if revenue_column not in data or abs(total_energy) < 1e-6:
                continue
            market_price = f"{PRICE_PREFIX}{market}"
            prices.append(
                {
                    "market": market,
                    "direction": direction,
                    "price": float(data[revenue_column].sum()) / total_energy,
                    "market_avg": float(data[market_price].mean())
                    if market_price in data
                    else None,
                }
            )
    return prices


def revenue_streams(data: pd.DataFrame) -> tuple[pd.Series, dict[str, str]]:
    """Total per revenue component ``B_<component>_<market>`` (except ``B_benefit_*``),
    labelled "<market> · <component>", and the market of each label."""
    market_list = markets(data)
    totals, market_of = {}, {}
    for column in data.columns:
        if not column.startswith(REVENUE_STREAM_PREFIX) or column.startswith(REVENUE_PREFIX):
            continue
        market = next((m for m in market_list if column.endswith(f"_{m}")), None)
        if market is None:
            continue
        component = column.removeprefix(REVENUE_STREAM_PREFIX).removesuffix(f"_{market}")
        label = f"{market} · {component.replace('_', ' ')}"
        totals[label] = float(data[column].sum())
        market_of[label] = market
    return pd.Series(totals, dtype=float), market_of


def market_energy(data: pd.DataFrame) -> tuple[pd.Series, dict[str, str]]:
    """Total energy per market and direction (``E_sell_/E_buy_/E_up_/E_down_``), signed,
    labelled "<market> · <direction>", and the market of each label."""
    totals, market_of = {}, {}
    for column in data.columns:
        prefix = next((p for p in MARKET_ENERGY_PREFIXES if column.startswith(p)), None)
        if prefix is None:
            continue
        market = column.removeprefix(prefix)
        label = f"{market} · {prefix.removeprefix(ENERGY_PREFIX).rstrip('_')}"
        totals[label] = float(data[column].sum())
        market_of[label] = market
    return pd.Series(totals, dtype=float), market_of


def hide_small(values: pd.Series, reference: float, what: str) -> tuple[pd.Series, str]:
    """Drop entries below ``SMALL_SHARE`` of ``reference``; footnote listing them."""
    if not reference:
        return values, ""
    small = values.abs() < SMALL_SHARE * reference
    if not small.any():
        return values, ""
    hidden = ", ".join(values.index[small])
    return values[~small], f"Hidden (<{SMALL_SHARE:.1%} {what}): {hidden}"


# ---------- Energy flows ----------


def flows_frame(data: pd.DataFrame) -> pd.DataFrame:
    """The PV/battery/grid flows per period (MWh): exports positive, battery charges negative."""
    present = [flow for flow in FLOWS if flow[1] in data]
    return pd.DataFrame(
        {label: side * data[variable].abs() for label, variable, _, side in present},
        index=data.index,
    )


def sankey_links(data: pd.DataFrame) -> tuple[list[tuple[str, str, float]], float]:
    """Energy flows (source, target, MWh) and the PV generation (MWh).

    Battery losses are what enters the battery and is not discharged. System losses are the
    residual between what PV generates / the battery discharges and what reaches the grid or
    the battery (system efficiency). Zero flows are kept (the figure drops them).
    """
    flow = {label: _abs_total(data, variable) for label, variable, *_ in FLOWS}
    pv = energy(data, "P_generation")
    curtailment = energy(data, "P_excess")
    discharged = energy(data, "P_storage_discharge")
    battery_in = flow["PV → battery"] + flow["Grid → battery"]
    battery_losses = max(battery_in - discharged, 0.0)
    system_from_pv = max(pv - flow["PV → grid"] - flow["PV → battery"] - curtailment, 0.0)
    system_from_battery = max(battery_in - battery_losses - flow["Battery → grid"], 0.0)
    links = [
        ("PV", "Grid export", flow["PV → grid"]),
        ("PV", "Battery", flow["PV → battery"]),
        ("Grid import", "Battery", flow["Grid → battery"]),
        ("Battery", "Grid export", flow["Battery → grid"]),
        ("PV", "Curtailment", curtailment),
        ("PV", "System losses", _negligible(system_from_pv, pv)),
        ("Battery", "System losses", _negligible(system_from_battery, battery_in)),
        ("Battery", "Battery losses", battery_losses),
    ]
    return links, pv


# ---------- Battery ----------


def daily_cycles(data: pd.DataFrame, inputs: dict) -> pd.Series:
    """Equivalent cycles per day: daily discharged energy / total battery capacity."""
    capacity = plant_ratings(inputs)["battery_capacity"]
    if not capacity or "P_storage_discharge" not in data:
        return pd.Series(dtype=float)
    discharged = data["P_storage_discharge"].abs() * period_hours(data.index)
    return discharged.resample("D").sum() / capacity


def cycle_limit(inputs: dict) -> float | None:
    """Strictest ``max_cycles_day`` of the batteries (None if none is set)."""
    limits = [b["max_cycles_day"] for b in inputs.get("batteries", []) if b.get("max_cycles_day")]
    return min(limits) if limits else None


def soc_grid(data: pd.DataFrame, by_month: bool) -> pd.DataFrame:
    """Mean SOC of all batteries (0-1): hour of day (rows) × month or day (columns)."""
    soc_columns = [c for c in data.columns if c.startswith(SOC_PREFIX)]
    if not soc_columns:
        return pd.DataFrame()
    soc = data[soc_columns].mean(axis=1)
    pattern = "%Y-%m-01" if by_month else "%Y-%m-%d"
    column = pd.DatetimeIndex(soc.index.strftime(pattern))
    return soc.groupby([column, soc.index.hour]).mean().unstack(level=0).sort_index()


# ---------- Checks ----------


def run_checks(inputs: dict, kpis: dict, data: pd.DataFrame) -> list[dict]:
    """Sanity checks of a run, as ``check_tile`` arguments (label, value, status, detail).

    Battery checks only for runs with a battery, curtailment only for runs with PV.
    """
    links, pv = sankey_links(data)
    checks = []
    if has_battery(inputs):
        checks.append(check_cycle_limit(daily_cycles(data, inputs), cycle_limit(inputs)))
        checks.append(check_simultaneous(data))
    checks.append(check_energy_balance(links, pv))
    checks.append(check_export(data, kpis.get("energy_exported_MWh")))
    if has_pv(inputs, data):
        checks.append(check_curtailment(kpis.get("excess_energy_MWh"), pv))
    for item in captured_prices(data):
        if item["direction"] == "sell" and item["market_avg"] is not None:
            checks.append(
                {
                    "label": f"{item['market']} captured vs market",
                    "value": f"{item['price'] - item['market_avg']:+,.1f} €/MWh",
                    "status": "info",
                    "detail": f"sell {item['price']:,.1f} vs avg {item['market_avg']:,.1f} €/MWh",
                }
            )
    return checks


def check_cycle_limit(cycles: pd.Series, limit: float | None) -> dict:
    """Days whose equivalent cycles exceed the battery daily limit."""
    peak = f"max {cycles.max():.2f}/day" if len(cycles) else None
    check = {"label": "Daily cycle limit", "status": "info", "detail": peak}
    if limit is None:
        return {**check, "value": "no limit set"}
    days = int((cycles > limit + 1e-9).sum())
    return {
        **check,
        "value": f"{days} days above {limit:g}/day",
        "status": "warn" if days else "ok",
        "detail": f"{peak} · daily discharged / capacity" if peak else None,
    }


def check_simultaneous(data: pd.DataFrame) -> dict:
    """Periods where the battery charges and discharges at the same time (allowed)."""
    check = {
        "label": "Simultaneous charge and discharge",
        "status": "info",
        "detail": "allowed by the model",
    }
    if "P_storage_charge" not in data or "P_storage_discharge" not in data:
        return {**check, "value": None}
    both = (data["P_storage_charge"].abs() > 1e-6) & (data["P_storage_discharge"].abs() > 1e-6)
    share = both.mean() if len(both) else 0.0
    return {**check, "value": f"{int(both.sum()):,} periods ({share:.1%})"}


def check_energy_balance(links: list[tuple[str, str, float]], pv: float) -> dict:
    """Largest imbalance of the energy flows (PV against its generation, every node with
    inflows and outflows), as a share of the energy entering the system."""
    inflow, outflow = {}, {}
    for source, target, value in links:
        if not value:
            continue
        outflow[source] = outflow.get(source, 0.0) + value
        inflow[target] = inflow.get(target, 0.0) + value
    if pv:
        inflow["PV"] = inflow.get("PV", 0.0) + pv
    imbalance = max(
        (abs(inflow[node] - outflow[node]) for node in inflow if node in outflow), default=0.0
    )
    entering = pv + outflow.get("Grid import", 0.0)
    share = imbalance / (entering or 1.0)
    return {
        "label": "Energy balance",
        "value": f"{share:.3%} max imbalance",
        "status": "ok" if share < BALANCE_TOLERANCE else "warn",
        "detail": f"largest node gap {compact_text(imbalance, 'MWh')} · share of energy in",
    }


def check_export(data: pd.DataFrame, exported_kpi: float | None) -> dict:
    """Exported energy measured two ways: Σ E_system_sell_* (flows) and the run KPI."""
    flows = sum(_abs_total(data, c) for c in data.columns if c.startswith(SYSTEM_SELL_PREFIX))
    check = {"label": "Export consistency", "status": "info"}
    if not exported_kpi:
        return {**check, "value": compact_text(flows, "MWh"), "detail": "no export KPI"}
    difference = flows / exported_kpi - 1
    return {
        **check,
        "value": f"{compact_text(flows, 'MWh')} vs {compact_text(exported_kpi, 'MWh')}",
        "status": "warn" if abs(difference) > EXPORT_TOLERANCE else "ok",
        "detail": f"Δ {difference:+.2%} · Σ E_sell vs Σ P_export·dt",
    }


def check_curtailment(excess: float | None, pv: float) -> dict:
    """Curtailed energy as a share of PV generation."""
    check = {"label": "Curtailment", "status": "info"}
    if excess is None or not pv:
        return {**check, "value": compact_text(excess, "MWh") if excess is not None else None}
    share = excess / pv
    return {
        **check,
        "value": f"{share:.1%} of PV generation",
        "status": "warn" if share > CURTAILMENT_WARNING else "info",
        "detail": compact_text(excess, "MWh"),
    }


# ---------- Detail ----------


def series_labels(variables) -> dict[str, str]:
    """Human labels of operation series ("PV generation", "AFRR band up"...) by name/prefix."""
    labels = {}
    for variable in variables:
        if variable in SERIES_LABELS:
            labels[variable] = SERIES_LABELS[variable]
            continue
        for prefix, what in SERIES_PREFIX_LABELS:
            if variable.startswith(prefix):
                labels[variable] = f"{variable.removeprefix(prefix)} {what}"
                break
    return labels


def week_options(index: pd.DatetimeIndex) -> list[dict]:
    """Consecutive 7-day windows from the first period: dropdown options (value = start date)."""
    if len(index) == 0:
        return []
    starts = pd.date_range(index.min().normalize(), index.max(), freq=f"{DETAIL_DAYS}D")
    return [
        {
            "label": f"Week {i} · {start:%Y-%m-%d} → "
            f"{min(start + pd.Timedelta(days=DETAIL_DAYS - 1), index.max()):%Y-%m-%d}",
            "value": start.isoformat(),
        }
        for i, start in enumerate(starts, start=1)
    ]


def time_window(data: pd.DataFrame, start, days: int = DETAIL_DAYS) -> pd.DataFrame:
    """Rows of ``data`` in ``[start, start + days)``; from the first period if ``start`` is None."""
    if data.empty:
        return data
    begin = data.index.min() if start is None else pd.Timestamp(start)
    if begin.tzinfo is None and data.index.tz is not None:
        begin = begin.tz_localize(data.index.tz)
    window = data[(data.index >= begin) & (data.index < begin + pd.Timedelta(days=days))]
    if window.empty:  # stale value from another run
        return time_window(data, None, days)
    return window


# ---------- Helpers ----------


def _negligible(value: float, reference: float) -> float:
    """``value``, or 0 when it is a rounding residual (< 0.01% of ``reference``)."""
    return value if value > 1e-4 * max(reference, 1.0) else 0.0


def _abs_total(data: pd.DataFrame, variable: str) -> float:
    return float(data[variable].abs().sum()) if variable in data else 0.0


def _battery_power(battery: dict):
    if battery.get("max_power_output") is not None:
        return battery["max_power_output"]
    if battery.get("capacity") is not None and battery.get("c_rate") is not None:
        return battery["capacity"] * battery["c_rate"]
    return None


def _sum_known(values):
    known = [v for v in values if v is not None]
    return sum(known) if known else None
