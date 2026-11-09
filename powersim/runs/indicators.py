"""Derived indicators of a saved run: how well the plant captured the value available.

Pure pandas/numpy (no plotting), so they can be computed after solving and stored with the run.
Every indicator takes the run ``inputs`` (dict) and/or ``kpis`` (dict) and ``data`` (the wide
time series, ``run.timeseries_wide()``) and returns an :class:`Indicator`:

- ``kpis``: JSON-serialisable scalars: float/int/None, plus a few str labels (market names).
  Units and formulas are in each function docstring.
- ``tables``: small DataFrames (per day, per year, histogram bins...) for charts.
- ``available``: False (with a ``reason``) when the run lacks what the indicator needs (no
  battery, no PV, no aFRR...).

Conventions:

- Period length ``dt`` (h) comes from the time index (runs may mix 15 min and 1 h periods).
  "% of periods" are time-weighted (share of hours).
- Days and years are calendar days/years of the index time zone (UTC for current runs).
- Signs in the run: ``P_storage_charge`` and ``P_system_import`` are ≤ 0; magnitudes are used.
- **Energy price** (:func:`energy_price`): the price ``p_<m>`` of the first market (in run
  order, from the ``B_benefit_<m>`` columns) that trades energy (has ``E_sell_<m>`` or
  ``E_buy_<m>``), e.g. ``p_DayAhead``. Battery energy is valued at that price.

Entry point: :func:`all_indicators`.
"""

import calendar
import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ._series import battery_ratings, energy, period_hours

REVENUE_PREFIX = "B_benefit_"
LIMIT_SHARE = 0.99  # grid limit reached at ≥ 99 % of the connection capacity
EPS = 1e-6


@dataclass
class Indicator:
    """Result of one indicator: scalar KPIs and small tables for charts."""

    kpis: dict = field(default_factory=dict)
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    available: bool = True
    reason: str | None = None


def unavailable(reason: str) -> Indicator:
    """Result of an indicator that does not apply to the run (``reason`` says why)."""
    return Indicator(available=False, reason=reason)


def all_indicators(
    inputs: dict, kpis: dict, data: pd.DataFrame, market_data: pd.DataFrame | None = None
) -> dict[str, Indicator]:
    """Every indicator of a run, by name. ``market_data`` is accepted for future use."""
    return {
        "spread": spread_capture(inputs, data),
        "per_cycle": revenue_per_cycle(inputs, kpis, data),
        "pv_capture": pv_capture(inputs, data),
        "concentration": revenue_concentration(data),
        "stability": temporal_stability(data),
        "grid": grid_use(inputs, data),
        "negative_prices": negative_prices(data),
        "battery_usage": battery_usage(inputs, data),
        "afrr": afrr_commitment(inputs, data),
        "sizing": sizing(inputs, data),
    }


# ---------- Shared ----------


def markets(data: pd.DataFrame) -> list[str]:
    """Markets of the run, in order (suffixes of the ``B_benefit_*`` columns)."""
    return [c.removeprefix(REVENUE_PREFIX) for c in data.columns if c.startswith(REVENUE_PREFIX)]


def energy_markets(data: pd.DataFrame) -> list[str]:
    """Markets that trade energy (``E_sell_<m>`` or ``E_buy_<m>``) and have a price."""
    return [
        m
        for m in markets(data)
        if (f"E_sell_{m}" in data or f"E_buy_{m}" in data) and f"p_{m}" in data
    ]


def energy_price(data: pd.DataFrame) -> tuple[str | None, pd.Series | None]:
    """Market and price series used to value energy (see the module docstring)."""
    found = energy_markets(data)
    return (found[0], data[f"p_{found[0]}"]) if found else (None, None)


def battery_value(data: pd.DataFrame, price: pd.Series) -> pd.Series:
    """Value of the battery flows at market price per period (€):
    price × (|discharge| − |charge|) × dt.
    """
    dt = period_hours(data.index)
    return (
        price
        * (_magnitude(data, "P_storage_discharge") - _magnitude(data, "P_storage_charge"))
        * dt
    )


def _magnitude(data: pd.DataFrame, variable: str) -> pd.Series:
    if variable not in data:
        return pd.Series(0.0, index=data.index)
    return data[variable].abs()


def _time_share(mask: pd.Series, dt: pd.Series) -> float | None:
    total = float(dt.sum())
    return float(dt[mask].sum()) / total if total else None


def _ratio(numerator, denominator):
    if numerator is None or denominator is None or abs(denominator) < EPS:
        return None
    return float(numerator) / float(denominator)


# ---------- 1 + 2. TBn spread capture and realized spread ----------


def spread_capture(inputs: dict, data: pd.DataFrame) -> Indicator:
    """Indicators 1 (TBn spread capture) and 2 (realized spread) of the battery.

    1. n = battery duration in hours (capacity / power, rounded, ≥ 1). Per calendar day, from
       hourly mean prices: TBn spread = mean of the n highest − mean of the n lowest (€/MWh).
       Theoretical value of one full cycle = capacity × (RTE × top_n − bottom_n), floored at 0
       (€; days with fewer than 2n hourly prices are skipped). Battery value = Σ price ×
       (|discharge| − |charge|) × dt (€). Capture = battery value / Σ theoretical. The model
       may cycle more than once per day, so capture can exceed 100 %; with ``max_cycles_day``
       set, the theoretical value is also scaled by min(limit, 24 / (2n)) ("cycle-limited").
    2. Average discharge price = Σ price × |discharge| × dt / Σ |discharge| × dt (€/MWh), the
       charge price likewise; realized spread = their difference; break-even spread = charge
       price × (1/RTE − 1), the spread that only pays the round-trip losses.

    KPIs: ``price_market`` (str), ``other_energy_markets`` (str or None, energy markets not
    used for valuation), ``tbn_hours`` (h), ``tbn_spread_mean`` (€/MWh), ``theoretical_value``
    (€), ``battery_value`` (€), ``tbn_capture`` (fraction), ``tbn_cycles_factor`` (cycles/day
    or None), ``tbn_capture_cycle_limited`` (fraction or None), ``avg_discharge_price``,
    ``avg_charge_price``, ``realized_spread``, ``breakeven_spread`` (€/MWh).

    Table ``daily`` (one row per day): tbn_spread and realized_spread (€/MWh), theoretical and
    battery_value (€), discharge/charge energy (MWh) and value (€), so charts can aggregate
    per period.
    """
    ratings = battery_ratings(inputs)
    power, capacity, rte = ratings["power"], ratings["capacity"], ratings["rte"]
    if not (power and capacity):
        return unavailable("No battery in this run.")
    market, price = energy_price(data)
    if price is None:
        return unavailable("No energy market price in this run.")
    rte = rte or 1.0
    n = max(1, round(capacity / power))

    hourly = price.resample("1h").mean().dropna()
    by_day = hourly.groupby(hourly.index.normalize())

    def top_bottom(values: pd.Series):
        ordered = np.sort(values.to_numpy())
        if len(ordered) < 2 * n:
            return pd.Series({"top": np.nan, "bottom": np.nan})
        return pd.Series({"top": ordered[-n:].mean(), "bottom": ordered[:n].mean()})

    daily = by_day.apply(top_bottom).unstack() if len(hourly) else pd.DataFrame()
    if daily.empty:
        return unavailable("Not enough price data.")
    daily["tbn_spread"] = daily["top"] - daily["bottom"]
    daily["theoretical"] = (capacity * (rte * daily["top"] - daily["bottom"])).clip(lower=0)

    dt = period_hours(data.index)
    discharge_energy = _magnitude(data, "P_storage_discharge") * dt
    charge_energy = _magnitude(data, "P_storage_charge") * dt
    flows = pd.DataFrame(
        {
            "discharge_energy": discharge_energy,
            "discharge_value": discharge_energy * price,
            "charge_energy": charge_energy,
            "charge_value": charge_energy * price,
        }
    )
    flows = flows.groupby(flows.index.normalize()).sum()
    daily = daily.join(flows, how="outer")
    daily["battery_value"] = daily["discharge_value"] - daily["charge_value"]
    daily["realized_spread"] = _safe_div(
        daily["discharge_value"], daily["discharge_energy"]
    ) - _safe_div(daily["charge_value"], daily["charge_energy"])

    value = float(daily["battery_value"].sum())
    theoretical = float(daily["theoretical"].sum())
    limit = ratings["max_cycles_day"]
    cycles_factor = min(limit, 24 / (2 * n)) if limit else None
    discharge_price = _ratio(daily["discharge_value"].sum(), daily["discharge_energy"].sum())
    charge_price = _ratio(daily["charge_value"].sum(), daily["charge_energy"].sum())
    realized = (
        discharge_price - charge_price
        if discharge_price is not None and charge_price is not None
        else None
    )
    kpis = {
        "price_market": market,
        "other_energy_markets": ", ".join(m for m in energy_markets(data) if m != market) or None,
        "tbn_hours": n,
        "tbn_spread_mean": _float(daily["tbn_spread"].mean()),
        "theoretical_value": theoretical,
        "battery_value": value,
        "tbn_capture": _ratio(value, theoretical),
        "tbn_cycles_factor": cycles_factor,
        "tbn_capture_cycle_limited": _ratio(value, theoretical * cycles_factor)
        if cycles_factor
        else None,
        "avg_discharge_price": discharge_price,
        "avg_charge_price": charge_price,
        "realized_spread": realized,
        "breakeven_spread": charge_price * (1 / rte - 1) if charge_price is not None else None,
    }
    columns = [
        "tbn_spread",
        "theoretical",
        "battery_value",
        "realized_spread",
        "discharge_energy",
        "discharge_value",
        "charge_energy",
        "charge_value",
    ]
    return Indicator(kpis=kpis, tables={"daily": daily[columns]})


def _safe_div(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    return numerator / denominator.where(denominator.abs() > EPS)


def _float(value) -> float | None:
    return (
        None if value is None or (isinstance(value, float) and math.isnan(value)) else float(value)
    )


# ---------- 3. Revenue per cycle ----------


def revenue_per_cycle(inputs: dict, kpis: dict, data: pd.DataFrame) -> Indicator:
    """Indicator 3: battery value at market price per equivalent cycle and
    per MWh discharged.

    Battery value as in :func:`battery_value` (€). Equivalent cycles = the run KPI
    ``equivalent_cycles``, else discharged energy / capacity.

    KPIs: ``battery_value`` (€), ``value_per_cycle`` (€/cycle), ``value_per_mwh_discharged``
    (€/MWh).
    """
    ratings = battery_ratings(inputs)
    if not (ratings["power"] and ratings["capacity"]):
        return unavailable("No battery in this run.")
    _, price = energy_price(data)
    if price is None:
        return unavailable("No energy market price in this run.")
    value = float(battery_value(data, price).sum())
    discharged = energy(data, "P_storage_discharge")
    cycles = kpis.get("equivalent_cycles")
    if cycles is None and ratings["capacity"]:
        cycles = discharged / ratings["capacity"]
    return Indicator(
        kpis={
            "battery_value": value,
            "value_per_cycle": _ratio(value, cycles),
            "value_per_mwh_discharged": _ratio(value, discharged),
        }
    )


# ---------- 4. PV capture rate ----------


def pv_capture(inputs: dict, data: pd.DataFrame) -> Indicator:
    """Indicator 4: PV capture rate.

    PV-weighted price = Σ P_generation × price × dt / Σ P_generation × dt (€/MWh); export-
    weighted price likewise with ``P_system_export``; capture rate = weighted price /
    time-average price; uplift = export − PV capture rate (what storage and the export
    strategy add on top of the PV profile).

    KPIs: ``average_price``, ``pv_weighted_price``, ``export_weighted_price`` (€/MWh),
    ``pv_capture_rate``, ``export_capture_rate`` (fraction), ``export_uplift`` (fraction
    points).
    """
    generating = "P_generation" in data and bool((data["P_generation"].abs() > EPS).any())
    if not (inputs.get("generators") or generating) or "P_generation" not in data:
        return unavailable("No PV in this run.")
    _, price = energy_price(data)
    if price is None:
        return unavailable("No energy market price in this run.")
    dt = period_hours(data.index)
    average = _ratio((price * dt).sum(), dt.sum())

    def weighted(variable):
        power = _magnitude(data, variable)
        return _ratio((power * price * dt).sum(), (power * dt).sum())

    pv_price, export_price = weighted("P_generation"), weighted("P_system_export")
    pv_rate, export_rate = _ratio(pv_price, average), _ratio(export_price, average)
    return Indicator(
        kpis={
            "average_price": average,
            "pv_weighted_price": pv_price,
            "export_weighted_price": export_price,
            "pv_capture_rate": pv_rate,
            "export_capture_rate": export_rate,
            "export_uplift": export_rate - pv_rate
            if pv_rate is not None and export_rate is not None
            else None,
        }
    )


# ---------- 5. Revenue concentration ----------


def revenue_concentration(data: pd.DataFrame) -> Indicator:
    """Indicator 5: how concentrated the revenue is.

    Revenue = Σ ``B_benefit_*`` (€), summed per calendar day and per hour. Top-10 %-days share
    = revenue of the best ceil(10 % of days) days / total revenue; top-5 %-hours share likewise
    with hours. Both are 10 % / 5 % when revenue is evenly spread, and can exceed 100 % when
    some periods have negative revenue (charging).

    KPIs: ``days`` (count), ``top10_days_share``, ``top5_hours_share`` (fraction),
    ``negative_days`` (count), ``best_day``, ``median_day`` (€). Table ``daily``: revenue
    (€/day).
    """
    revenue_columns = [c for c in data.columns if c.startswith(REVENUE_PREFIX)]
    if not revenue_columns:
        return unavailable("No market revenue in this run.")
    revenue = data[revenue_columns].sum(axis=1)
    daily = revenue.groupby(revenue.index.normalize()).sum()
    hourly = revenue.resample("1h").sum()
    total = float(revenue.sum())
    return Indicator(
        kpis={
            "days": len(daily),
            "top10_days_share": _ratio(_top_sum(daily, 0.10), total),
            "top5_hours_share": _ratio(_top_sum(hourly, 0.05), total),
            "negative_days": int((daily < 0).sum()),
            "best_day": _float(daily.max()) if len(daily) else None,
            "median_day": _float(daily.median()) if len(daily) else None,
        },
        tables={"daily": daily.to_frame("revenue")},
    )


def _top_sum(values: pd.Series, share: float) -> float:
    """Sum of the largest ``share`` of the values (at least one)."""
    count = max(1, math.ceil(share * len(values)))
    return float(values.nlargest(count).sum())


# ---------- 6. Temporal stability ----------


def temporal_stability(data: pd.DataFrame) -> Indicator:
    """Indicator 6: revenue stability over time.

    Revenue per calendar year (€), days covered (from the period lengths) and annualised
    revenue = revenue × days in year / days covered. Coefficient of variation of the monthly
    revenue = sample std / mean over complete months only. Year-on-year change = (last / previous
    complete year − 1), when there are at least two complete years.

    KPIs: ``years`` (count of calendar years touched), ``complete_months`` (count),
    ``monthly_cv`` (fraction or None), ``yoy_change`` (fraction or None). Table ``yearly``:
    revenue (€), days_covered, days_in_year (days), annualised (€), complete (bool).
    """
    revenue_columns = [c for c in data.columns if c.startswith(REVENUE_PREFIX)]
    if not revenue_columns:
        return unavailable("No market revenue in this run.")
    frame = pd.DataFrame(
        {"revenue": data[revenue_columns].sum(axis=1), "hours": period_hours(data.index)}
    )

    yearly = frame.resample("YS").sum()
    yearly["days_covered"] = yearly["hours"] / 24
    yearly["days_in_year"] = [
        ((start + pd.DateOffset(years=1)) - start).total_seconds() / 86400 for start in yearly.index
    ]
    yearly["complete"] = yearly["days_covered"] >= yearly["days_in_year"] - 0.5 / 24
    yearly["annualised"] = _safe_div(
        yearly["revenue"] * yearly["days_in_year"], yearly["days_covered"]
    )

    monthly = frame.resample("MS").sum()
    lengths = [((s + pd.DateOffset(months=1)) - s).total_seconds() / 3600 for s in monthly.index]
    complete_months = monthly.loc[monthly["hours"] >= np.array(lengths) - 0.5, "revenue"]
    cv = (
        float(complete_months.std() / complete_months.mean())
        if len(complete_months) >= 2 and abs(complete_months.mean()) > EPS
        else None
    )
    complete_years = yearly.loc[yearly["complete"], "revenue"]
    yoy = (
        _ratio(complete_years.iloc[-1] - complete_years.iloc[-2], complete_years.iloc[-2])
        if len(complete_years) >= 2
        else None
    )
    return Indicator(
        kpis={
            "years": len(yearly),
            "complete_months": len(complete_months),
            "monthly_cv": cv,
            "yoy_change": yoy,
        },
        tables={
            "yearly": yearly[["revenue", "days_covered", "days_in_year", "annualised", "complete"]]
        },
    )


# ---------- 7. Grid connection use ----------


def grid_use(inputs: dict, data: pd.DataFrame, bin_size: float = 5.0) -> Indicator:
    """Indicator 7: use of the grid connection.

    Export is measured after the system ``efficiency``, so the effective export limit is
    capacity_sell × efficiency (MW); the import limit is capacity_buy (MW). Net POI power =
    export − import, as % of the export limit when exporting and of the import limit when
    importing (negative). Time at a limit = share of time with export (import) ≥ 99 % of its
    limit; idle = |net| < 1 % of its limit; POI capacity factor = exported energy / (export
    limit × hours).

    KPIs: ``export_limit_share``, ``import_limit_share`` (or None), ``idle_share``,
    ``capacity_factor`` (fractions of time / of the maximum), ``capacity_sell``,
    ``export_limit``, ``capacity_buy`` (MW), ``efficiency`` (fraction). Tables: ``bins`` (hours
    per ``bin_size`` % bin, left edge, clipped to [−100, 100 − bin_size], idle periods left
    out) and ``duration`` (net % sorted from highest, 201 points over the share of time, %).
    """
    system = inputs.get("system", {})
    capacity_sell, capacity_buy = system.get("capacity_sell"), system.get("capacity_buy")
    if not capacity_sell or "P_system_export" not in data:
        return unavailable("No grid export capacity in this run.")
    efficiency = system.get("efficiency") or 1.0
    export_limit = capacity_sell * efficiency
    dt = period_hours(data.index)
    export = _magnitude(data, "P_system_export")
    imported = _magnitude(data, "P_system_import")
    net = export - imported
    percent = (net / export_limit * 100).where(net >= 0)
    if capacity_buy:
        percent = percent.fillna(net / capacity_buy * 100)
    percent = percent.fillna(0.0)
    idle = percent.abs() < 1.0

    bins = (np.floor(percent / bin_size) * bin_size).clip(-100, 100 - bin_size)
    hours = dt[~idle].groupby(bins[~idle]).sum().rename("hours")
    hours.index.name = "bin"
    order = np.argsort(-percent.to_numpy())
    cumulative = np.cumsum(dt.to_numpy()[order]) / dt.sum()
    points = np.linspace(0, 1, 201)
    duration = pd.DataFrame(
        {"net_percent": np.interp(points, cumulative, percent.to_numpy()[order])},
        index=pd.Index(points * 100, name="time_share"),
    )
    total_hours = float(dt.sum())
    return Indicator(
        kpis={
            "export_limit_share": _time_share(export >= LIMIT_SHARE * export_limit, dt),
            "import_limit_share": _time_share(imported >= LIMIT_SHARE * capacity_buy, dt)
            if capacity_buy
            else None,
            "idle_share": _time_share(idle, dt),
            "capacity_factor": _ratio(float((export * dt).sum()), export_limit * total_hours),
            "capacity_sell": float(capacity_sell),
            "efficiency": float(efficiency),
            "export_limit": float(export_limit),
            "capacity_buy": float(capacity_buy) if capacity_buy is not None else None,
        },
        tables={"bins": hours.to_frame(), "duration": duration},
    )


# ---------- 8. Exposure to prices ≤ 0 ----------


def negative_prices(data: pd.DataFrame) -> Indicator:
    """Indicator 8: exposure to zero and negative energy prices.

    With the energy price p: exported energy where p ≤ 0 and imported energy where p < 0
    (MWh, power × dt), money received for importing at negative prices = Σ |import| × dt × (−p)
    where p < 0 (€), and share of time with p ≤ 0.

    KPIs: ``price_market`` (str), ``export_at_nonpositive_mwh``, ``import_at_negative_mwh``
    (MWh), ``paid_to_import`` (€), ``nonpositive_time_share`` (fraction).
    """
    market, price = energy_price(data)
    if price is None:
        return unavailable("No energy market price in this run.")
    dt = period_hours(data.index)
    export = _magnitude(data, "P_system_export") * dt
    imported = _magnitude(data, "P_system_import") * dt
    non_positive, negative = price <= 0, price < 0
    return Indicator(
        kpis={
            "price_market": market,
            "export_at_nonpositive_mwh": float(export[non_positive].sum()),
            "import_at_negative_mwh": float(imported[negative].sum()),
            "paid_to_import": float((imported * -price)[negative].sum()),
            "nonpositive_time_share": _time_share(non_positive, dt),
        }
    )


# ---------- 9. Battery usage profile ----------


def battery_usage(inputs: dict, data: pd.DataFrame, bin_size: float = 5.0) -> Indicator:
    """Indicator 9: battery usage profile.

    SOC = mean of the ``SOC_*`` columns (fractions of each battery's capacity, not weighted).
    Idle = |charge| and |discharge| < 1e-6 MW. At minimum (maximum) SOC = SOC within 1 % of
    soc_min = 1 − DoD (of soc_max). Daily depth of discharge = daily max − min SOC. At power
    limit = |charge| or |discharge| ≥ 99 % of the total battery power (MW).

    KPIs: ``idle_share``, ``power_limit_share`` (None without a power rating),
    ``soc_min_share``, ``soc_max_share`` (fractions of time),
    ``mean_daily_dod`` (fraction of capacity), ``soc_min``, ``soc_max`` (fractions). Table
    ``soc_bins``: hours per ``bin_size`` % SOC bin (left edge, 0 to 100 − bin_size).
    """
    ratings = battery_ratings(inputs)
    if not ratings["capacity"]:
        return unavailable("No battery in this run.")
    dt = period_hours(data.index)
    charge = _magnitude(data, "P_storage_charge")
    discharge = _magnitude(data, "P_storage_discharge")
    idle = (charge < EPS) & (discharge < EPS)
    power = ratings["power"]
    soc_columns = [c for c in data.columns if c.startswith("SOC_")]
    kpis = {
        "idle_share": _time_share(idle, dt),
        "power_limit_share": _time_share(
            (charge >= LIMIT_SHARE * power) | (discharge >= LIMIT_SHARE * power), dt
        )
        if power
        else None,
    }
    tables = {}
    if soc_columns:
        soc = data[soc_columns].mean(axis=1)
        soc_min, soc_max = ratings["soc_min"] or 0.0, ratings["soc_max"] or 1.0
        by_day = soc.groupby(soc.index.normalize())
        dod = by_day.max() - by_day.min()
        kpis |= {
            "soc_min": float(soc_min),
            "soc_max": float(soc_max),
            "soc_min_share": _time_share(soc <= soc_min + 0.01, dt),
            "soc_max_share": _time_share(soc >= soc_max - 0.01, dt),
            "mean_daily_dod": _float(dod.mean()),
        }
        bins = (np.floor(soc * 100 / bin_size) * bin_size).clip(0, 100 - bin_size)
        soc_hours = dt.groupby(bins).sum().rename("hours")
        soc_hours.index.name = "bin"
        tables["soc_bins"] = soc_hours.to_frame()
    return Indicator(kpis=kpis, tables=tables)


# ---------- 10. aFRR commitment ----------


def afrr_commitment(inputs: dict, data: pd.DataFrame, bin_size: float = 10.0) -> Indicator:
    """Indicator 10: reserve bands offered (first market with ``Band_up_*`` /
    ``Band_down_*`` columns, e.g. AFRR).

    Average band = time-weighted mean of |Band| (MW) and as a share of battery power; time with
    a band = share of time with up or down > 0; largest band / battery power (> 1 flags bands
    above the battery power, which the model does not limit yet); activation revenue share =
    Σ ``B_act_*_<m>`` / Σ ``B_benefit_<m>``.

    KPIs: ``market`` (str), ``band_up_mean``, ``band_down_mean`` (MW),
    ``band_up_share_of_power``, ``band_down_share_of_power``, ``band_time_share``,
    ``max_band_over_power``, ``activation_revenue_share`` (fractions). Table ``bins``: hours
    per ``bin_size`` % of battery power (left edge), columns up and down.
    """
    band_markets = [
        c.removeprefix("Band_up_") for c in data.columns if c.startswith("Band_up_")
    ] + [c.removeprefix("Band_down_") for c in data.columns if c.startswith("Band_down_")]
    if not band_markets:
        return unavailable("No reserve bands (aFRR) in this run.")
    market = band_markets[0]
    power = battery_ratings(inputs)["power"]
    dt = period_hours(data.index)
    up = _magnitude(data, f"Band_up_{market}")
    down = _magnitude(data, f"Band_down_{market}")

    def mean(series):
        return _ratio((series * dt).sum(), dt.sum())

    activation = sum(
        float(data[c].sum()) for c in data.columns if c.startswith("B_act_") and c.endswith(market)
    )
    benefit = (
        float(data[f"{REVENUE_PREFIX}{market}"].sum())
        if f"{REVENUE_PREFIX}{market}" in data
        else None
    )
    largest = max(float(up.max()), float(down.max()))
    kpis = {
        "market": market,
        "band_up_mean": mean(up),
        "band_down_mean": mean(down),
        "band_up_share_of_power": _ratio(mean(up), power),
        "band_down_share_of_power": _ratio(mean(down), power),
        "band_time_share": _time_share((up > EPS) | (down > EPS), dt),
        "max_band_over_power": _ratio(largest, power),
        "activation_revenue_share": _ratio(activation, benefit),
    }
    tables = {}
    if power:
        bins = pd.DataFrame(
            {
                name: dt.groupby(np.floor(series / power * 100 / bin_size) * bin_size).sum()
                for name, series in (("up", up), ("down", down))
            }
        ).fillna(0.0)
        bins.index.name = "bin"
        tables["bins"] = bins.sort_index()
    return Indicator(kpis=kpis, tables=tables)


# ---------- 11. Sizing signals ----------

MAX_DURATION_HOURS = 12  # storage hours evaluated by the marginal duration curve


def sizing(inputs: dict, data: pd.DataFrame) -> Indicator:
    """Indicator 11: signals that a component of the plant limits (or is underused by) the
    operation, to answer "is the plant well sized?" without re-simulating. Each signal is
    computed only when the run has what it needs; missing ones are absent or None.

    Grid connection (export limit = capacity_sell × efficiency, as in :func:`grid_use`):

    - ``export_p99``: 99th percentile (time-weighted) of export / export limit (fraction);
      well below 1 means the connection is never close to full.
    - ``limit_price_premium``: mean energy price while exporting at ≥ 99 % of the limit minus
      the mean price while exporting (€/MWh); > 0 means the limit binds in valuable hours.
    - ``curtailed_mwh``: Σ ``P_excess`` × dt (PV above the connection that was neither stored
      nor exported) and ``curtailed_value``: that energy at max(price, 0) (€).
    - ``export_limit`` (MW) against ``plant_max_export`` = (battery power + PV peak) ×
      efficiency (MW), ``import_limit`` = capacity_buy against ``plant_max_import`` = battery
      power (MW): the connection can only be the bottleneck where the plant can exceed it.

    Battery power (MW):

    - ``throughput_at_power_limit``: share of the battery throughput (|charge| + |discharge|
      energy) moved at ≥ 99 % of the battery power (fraction).
    - ``battery_power_p99``: 99th percentile of max(|charge|, |discharge|) / power (fraction).
    - ``battery_power`` (MW) and ``duration_hours`` (h, see below).

    Battery energy (MWh), with usable range = soc_max − soc_min and
    duration = capacity × usable range / power (h):

    - ``full_range_days_share``: share of days whose SOC range (max − min) reaches ≥ 95 % of the
      usable range (fraction).
    - Marginal duration curve (table ``marginal_duration``): per day, from hourly mean prices
      sorted, the k-th storage hour earns max(0, RTE × k-th highest − k-th lowest) (€ per MW of
      battery power, one cycle per day). ``value`` = mean over days × 365 (€/MW·year, which is
      also € per extra MWh of capacity per year), ``positive_days`` = share of days where it
      earns something. ``last_hour_value`` / ``next_hour_value``: the curve at the current
      duration n (rounded, ≥ 1) and one hour more; ``next_hour_value`` is the value of one
      more MWh at the same power (€/MWh·year). With value(P, E) ≈ P × Σ_{k ≤ E/P} m_k,
      ``extra_power_value`` = Σ_{k ≤ n} m_k − n × m_n is the value of one more MW at the same
      MWh (€/MW·year, the battery gets shorter). For comparison, the value of the installed
      plant per unit: ``average_power_value`` = Σ_{k ≤ n} m_k (€/MW·year) and
      ``average_energy_value`` = that / n (€/MWh·year): a marginal value close to the average
      means growing that component pays about as well as what is installed. Energy arbitrage
      only (first energy market, one cycle per day): reserves and other energy markets are not
      included.

    Cycle limit: ``mean_cycles_day`` (discharged energy / capacity per day),
    ``max_cycles_day`` and ``days_at_cycle_limit_share`` (days at ≥ 98 % of that limit),
    ``yearly_avg_limit`` (strictest ``max_cycles_day_yearly_avg``) and
    ``yearly_budget_used``: as in the model, the budget of a calendar year is limit × days of
    that year (whatever the run covers) and cycles are Σ |ΔSOC| / 2; largest share of the
    budget used over the calendar years of the run (fraction).

    PV: ``pv_peak`` (MWp), ``pv_max_mw`` (largest generation, MW), ``dc_ac_ratio`` = PV peak /
    capacity_sell, ``pv_excess_mw`` = max(0, largest generation − capacity_sell) (MW the
    battery must absorb to avoid clipping), ``pv_above_connection_mwh`` = Σ max(0,
    generation − capacity_sell) × dt (must be stored or curtailed),
    ``pv_hours_export_limit_share`` = share of the producing time (generation > 1 % of the
    peak) with the export at its limit, ``battery_charge_from_pv_share`` = battery charge from
    PV / total charge, ``pv_spilled_battery_full_mwh`` = PV exported at price ≤ 0 or curtailed
    while the battery was full (SOC within 1 % of its maximum).

    Reserve band: ``band_cap_share`` = share of time the band (up or down) is at ≥ 99 % of the
    market's ``max_up`` / ``max_down`` input; ``band_cap`` = the larger cap (MW).

    Table ``monthly`` (index: month start): share of time at the export limit
    (``export_limit``), at the import limit (``import_limit``), at battery power
    (``battery_power``), with the band at its cap (``band_cap``) and share of full-range days
    (``full_range_days``), only the columns that apply, plus ``hours`` (hours of data in the
    month, to spot partial months).
    """
    dt = period_hours(data.index)
    if not float(dt.sum()):
        return unavailable("Empty run.")
    _, price = energy_price(data)
    system = inputs.get("system", {})
    ratings = battery_ratings(inputs)
    kpis: dict = {}
    tables: dict[str, pd.DataFrame] = {}
    time_masks: dict[str, pd.Series] = {}  # per period, for the monthly table
    full_days: pd.Series | None = None

    # Grid connection
    capacity_sell = system.get("capacity_sell")
    export = _magnitude(data, "P_system_export")
    efficiency = system.get("efficiency") or 1.0
    peak = sum(g.get("peak_power") or 0 for g in inputs.get("generators", []))
    if capacity_sell and "P_system_export" in data:
        limit = capacity_sell * efficiency
        kpis["export_limit"] = float(limit)
        kpis["plant_max_export"] = float(((ratings["power"] or 0) + peak) * efficiency)
        if system.get("capacity_buy"):
            kpis["import_limit"] = float(system["capacity_buy"])
            kpis["plant_max_import"] = float(ratings["power"] or 0)
        kpis["export_p99"] = _weighted_quantile(export / limit, dt, 0.99)
        at_limit = export >= LIMIT_SHARE * limit
        time_masks["export_limit"] = at_limit
        if system.get("capacity_buy"):
            imported = _magnitude(data, "P_system_import")
            time_masks["import_limit"] = imported >= LIMIT_SHARE * system["capacity_buy"]
        if price is not None:
            kpis["limit_price_premium"] = (
                _float(price[at_limit].mean() - price[export > EPS].mean())
                if at_limit.any()
                else None
            )
    excess = _magnitude(data, "P_excess") * dt
    kpis["curtailed_mwh"] = float(excess.sum())
    kpis["curtailed_value"] = (
        float((excess * price.clip(lower=0)).sum()) if price is not None else None
    )

    # Battery
    power, capacity = ratings["power"], ratings["capacity"]
    if power and capacity:
        charge = _magnitude(data, "P_storage_charge")
        discharge = _magnitude(data, "P_storage_discharge")
        throughput = (charge + discharge) * dt
        full_power = (charge >= LIMIT_SHARE * power) | (discharge >= LIMIT_SHARE * power)
        time_masks["battery_power"] = full_power
        kpis["throughput_at_power_limit"] = _ratio(throughput[full_power].sum(), throughput.sum())
        kpis["battery_power_p99"] = _weighted_quantile(
            np.maximum(charge, discharge) / power, dt, 0.99
        )
        soc_min, soc_max = ratings["soc_min"] or 0.0, ratings["soc_max"] or 1.0
        usable = soc_max - soc_min
        duration = capacity * usable / power
        kpis["duration_hours"] = float(duration)
        kpis["battery_power"] = float(power)
        soc_columns = [c for c in data.columns if c.startswith("SOC_")]
        if soc_columns and usable > EPS:
            soc = data[soc_columns].mean(axis=1)
            by_day = soc.groupby(soc.index.normalize())
            full_days = (by_day.max() - by_day.min()) >= 0.95 * usable
            kpis["full_range_days_share"] = _float(full_days.mean())
        cycles = (discharge * dt).groupby(data.index.normalize()).sum() / capacity
        limit_day = ratings["max_cycles_day"]
        kpis["mean_cycles_day"] = _float(cycles.mean())
        kpis["max_cycles_day"] = limit_day
        kpis["days_at_cycle_limit_share"] = (
            _float((cycles >= 0.98 * limit_day).mean()) if limit_day else None
        )
        yearly = [
            b["max_cycles_day_yearly_avg"]
            for b in inputs.get("batteries", [])
            if b.get("max_cycles_day_yearly_avg")
        ]
        kpis["yearly_avg_limit"] = min(yearly) if yearly else None
        if yearly and soc_columns:
            soc_cycles = data[soc_columns].diff().abs().sum(axis=1) / 2 / len(soc_columns)
            per_year = soc_cycles.groupby(data.index.year).sum()
            budget = [min(yearly) * (366 if calendar.isleap(y) else 365) for y in per_year.index]
            kpis["yearly_budget_used"] = _float((per_year / budget).max())
        if price is not None:
            curve = marginal_duration(price, ratings["rte"] or 1.0)
            if not curve.empty:
                tables["marginal_duration"] = curve
                n = max(1, round(duration))
                kpis["last_hour_value"] = _float(curve["value"].get(n))
                kpis["next_hour_value"] = _float(curve["value"].get(n + 1))
                values = curve["value"]
                kpis["extra_power_value"] = (
                    _float(values.loc[:n].sum() - n * values[n]) if n in values.index else None
                )
                kpis["average_power_value"] = _float(values.loc[:n].sum())
                kpis["average_energy_value"] = _float(values.loc[:n].sum() / n)

    # PV
    if peak and "P_generation" in data:
        generation = data["P_generation"].abs()
        kpis["pv_energy_mwh"] = float((generation * dt).sum())
        kpis["pv_peak"] = float(peak)
        kpis["pv_max_mw"] = float(generation.max())
        kpis["dc_ac_ratio"] = _ratio(peak, capacity_sell)
        if capacity_sell:
            kpis["pv_above_connection_mwh"] = float(
                ((generation - capacity_sell).clip(lower=0) * dt).sum()
            )
            kpis["pv_excess_mw"] = max(0.0, float(generation.max()) - capacity_sell)
            producing = generation > 0.01 * peak
            if "export_limit" in kpis and producing.any():
                at_limit = export >= LIMIT_SHARE * kpis["export_limit"]
                kpis["pv_hours_export_limit_share"] = _ratio(
                    dt[producing & at_limit].sum(), dt[producing].sum()
                )
        from_pv = _magnitude(data, "P_storage_charge_generation")
        from_grid = _magnitude(data, "P_storage_charge_grid")
        kpis["battery_charge_from_pv_share"] = _ratio(
            (from_pv * dt).sum(), ((from_pv + from_grid) * dt).sum()
        )
        soc_columns = [c for c in data.columns if c.startswith("SOC_")]
        if soc_columns and price is not None:
            full = data[soc_columns].mean(axis=1) >= (ratings["soc_max"] or 1.0) - 0.01
            sold = _magnitude(data, "P_system_sell_generation") * dt
            spilled = sold.where(price <= 0, 0.0) + excess
            kpis["pv_spilled_battery_full_mwh"] = float(spilled[full].sum())

    # Reserve band cap (market input)
    for market in inputs.get("markets", []):
        params = market.get("params") or {}
        caps = {"up": params.get("max_up"), "down": params.get("max_down")}
        columns = {d: f"Band_{d}_{market.get('type')}" for d in caps}
        if not any(caps.values()) or not any(c in data for c in columns.values()):
            continue
        at_cap = pd.Series(False, index=data.index)
        for direction, cap in caps.items():
            if cap and columns[direction] in data:
                at_cap |= _magnitude(data, columns[direction]) >= LIMIT_SHARE * cap
        kpis["band_cap_share"] = _time_share(at_cap, dt)
        kpis["band_cap"] = float(max(c for c in caps.values() if c))
        time_masks["band_cap"] = at_cap
        break

    month = _month_start(data.index)
    monthly = pd.DataFrame(
        {
            name: (dt * mask).groupby(month).sum() / dt.groupby(month).sum()
            for name, mask in time_masks.items()
        }
    )
    if full_days is not None:
        monthly["full_range_days"] = full_days.groupby(_month_start(full_days.index)).mean()
    if not monthly.empty:
        monthly["hours"] = dt.groupby(month).sum()
        monthly.index.name = "month"
        tables["monthly"] = monthly
    return Indicator(kpis=kpis, tables=tables)


def marginal_duration(
    price: pd.Series, rte: float, max_hours: int = MAX_DURATION_HOURS
) -> pd.DataFrame:
    """Value of the k-th storage hour (k = 1..max_hours, at most 12), see :func:`sizing`.
    Index ``hour``; columns ``value`` (€/MW·year) and ``positive_days`` (fraction). Days with
    fewer than 24 hourly prices are skipped; on longer days (DST) the 12 lowest and 12
    highest prices are used."""
    hourly = price.resample("1h").mean().dropna()
    days = [np.sort(d.to_numpy()) for _, d in hourly.groupby(hourly.index.normalize())]
    days = [d for d in days if len(d) >= 24]
    if not days:
        return pd.DataFrame(columns=["value", "positive_days"])
    ordered = np.vstack([np.concatenate([d[:12], d[-12:]]) for d in days])
    k = np.arange(1, min(max_hours, 12) + 1)
    gain = np.clip(rte * ordered[:, -k] - ordered[:, k - 1], 0, None)
    return pd.DataFrame(
        {"value": gain.mean(axis=0) * 365, "positive_days": (gain > 0).mean(axis=0)},
        index=pd.Index(k, name="hour"),
    )


def _month_start(index: pd.DatetimeIndex) -> pd.Index:
    """First day of the month of each timestamp (naive, for grouping)."""
    naive = index.tz_localize(None) if index.tz is not None else index
    return pd.Index(naive.to_period("M").start_time, name="month")


def _weighted_quantile(values: pd.Series, weights: pd.Series, q: float) -> float | None:
    """Time-weighted quantile of ``values`` (weights = period hours)."""
    if values.empty:
        return None
    order = np.argsort(values.to_numpy())
    cumulative = np.cumsum(weights.to_numpy()[order])
    position = int(np.searchsorted(cumulative, q * cumulative[-1]))
    return float(values.to_numpy()[order][min(position, len(order) - 1)])
