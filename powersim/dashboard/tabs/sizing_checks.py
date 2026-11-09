"""Sizing checks: questions that confirm the plant is well sized for its grid access.

The grid access (export / import capacity) is a given condition, not a lever: the questions
size the PV (MWp), the battery power (MW) and its hours (MWh) against it. Computation: the
``sizing`` indicator of ``powersim.runs.indicators``; this module turns it into verdicts
(heuristic thresholds below) and the two charts behind them. Shown in the Checks section of
the Visualization tab; notes in ``.claude/dashboard/visualization.md``.
"""

import pandas as pd
import plotly.graph_objects as go

from ...runs.indicators import Indicator
from ...visualization.styles import NODE_COLORS, STATUS_COLORS
from ..components import chart_card, check_list, columns, note
from ..figures import apply_theme, line_figure
from ..formatting import compact_text

CHART_HEIGHT = 340

# Heuristic thresholds of the sizing questions (fractions). The grid access (export / import
# capacity) is a given condition, not a design choice: the questions size the PV (MWp), the
# battery power (MW) and its hours (MWh) against it.
ACCESS_MATCH = 0.95  # battery power at least this share of the access: matched
ACCESS_MARGIN = 1.01  # battery power above the access by more than this: above access
PV_SPILL_SHARE = 0.02  # PV sold at price ≤ 0 or curtailed with the battery full, of PV energy
LOW_CLIPPING_SHARE = 0.01  # PV above the access below this share of PV energy: room for PV
FULL_RANGE_DAYS = 0.50  # days using ≥ 95 % of the usable SOC range
LOW_DOD = 0.50  # mean daily SOC range below this share of the usable range: too long
LAST_HOUR_SHARE = 0.30  # last installed hour earns less than this share of the average: too long
CYCLE_LIMIT_DAYS = 0.10  # days at the daily cycle limit
CYCLE_BUDGET_SHARE = 0.98  # share of the yearly cycle budget used
MARGINAL_SHARE = 0.50  # one more MW / hour earns at least this share of an installed one
BAND_CAP_TIME = 0.50  # time with the reserve band at its market cap
MIN_MONTH_COVERAGE = 0.25  # months with less data are left out of the monthly chart
SIZING_NAMES = {
    "warn": ("to review", "to review"),
    "ok": ("coherent", "coherent"),
    "info": ("note", "notes"),
}
LIMIT_LABELS = {
    "export_limit": "At export limit",
    "import_limit": "At import limit",
    "battery_power": "Battery at full power",
    "full_range_days": "Days using the full SOC range",
    "band_cap": "Reserve band at its cap",
}
LIMIT_COLORS = {
    "export_limit": NODE_COLORS["grid"],
    "import_limit": "#a5d8ff",
    "battery_power": NODE_COLORS["battery"],
    "full_range_days": "#2f9e44",
    "band_cap": STATUS_COLORS["warn"],
}


def sizing_body(results: dict[str, Indicator], prefix: str) -> list:
    """Sizing questions (check list) and the two charts behind them; chart ids start
    with ``prefix`` (the tab id)."""
    sizing = results["sizing"]
    if not sizing.available:
        return [note(sizing.reason)]
    body = [
        check_list(
            sizing_checks(results),
            columns=2,
            warn_first=False,
            summary_names=SIZING_NAMES,
        )
    ]
    charts = []
    curve = sizing.tables.get("marginal_duration")
    if curve is not None:
        charts.append(
            chart_card(
                f"{prefix}-storage-hours",
                "Value of each storage hour",
                "€ per MW of battery per year · energy arbitrage, one cycle a day",
                CHART_HEIGHT,
                figure=storage_hours_figure(curve, sizing.kpis.get("duration_hours")),
                footnote="Bar k: what the k-th hour of storage earns (RTE × k-th highest − "
                "k-th lowest hourly price of each day). Bars after the installed duration: "
                "value of one more MWh per MW. Reserves and other markets not included.",
            )
        )
    monthly = sizing.tables.get("monthly")
    if monthly is not None:
        charts.append(
            chart_card(
                f"{prefix}-limits-monthly",
                "When does each limit bind?",
                "share of time (of days for the SOC range) per month",
                CHART_HEIGHT,
                figure=monthly_limits_figure(monthly),
            )
        )
    if charts:
        body.append(columns(charts))
    return body


def sizing_checks(results: dict[str, Indicator]) -> list[dict]:
    """Sizing questions as ``check_list`` rows, the grid access first as a given condition
    (no status): battery power against the access and against the PV, PV peak against the
    access, battery hours. Status warn = to review, ok = coherent, info = note (room to grow,
    above the access...); then informative rows (status None) with figures shown elsewhere.
    Only the questions the run can answer."""

    def kpis(name):
        result = results.get(name)
        return result.kpis if result is not None and result.available else {}

    s, grid, usage = kpis("sizing"), kpis("grid"), kpis("battery_usage")
    afrr, pv = kpis("afrr"), kpis("pv_capture")
    has_battery, has_pv = "battery_power" in s, bool(s.get("pv_energy_mwh"))
    checks = []
    if grid:
        checks.append(_access_row(grid))
    if has_battery and grid.get("capacity_sell"):
        checks.append(_battery_vs_access(s, grid["capacity_sell"], has_pv))
    if has_battery and has_pv:
        checks.append(_battery_vs_pv(s))
    if has_pv and grid.get("capacity_sell"):
        checks.append(_pv_vs_access(s, grid["capacity_sell"]))
    if has_battery and "full_range_days_share" in s:
        checks.append(_battery_hours(s, usage))

    # Informative rows (figures also shown elsewhere in the tab)
    if usage:
        cycles = s.get("mean_cycles_day")
        checks.append(
            _check(
                "Battery use",
                f"{cycles:.2f} cycles/day" if cycles is not None else "-",
                None,
                f"idle {_share(usage.get('idle_share'))} of the time · mean daily SOC range "
                f"{_share(usage.get('mean_daily_dod'))}",
            )
        )
    if "band_cap_share" in s and afrr:
        checks.append(_band_row(s, afrr))
    if pv.get("pv_capture_rate") is not None:
        checks.append(
            _check(
                "PV value",
                f"capture rate {_share(pv['pv_capture_rate'])}",
                None,
                "PV-weighted price / mean price",
            )
        )
    return checks


def _access_row(grid: dict) -> dict:
    """The grid access: a given condition the plant is sized against (no status)."""
    value = f"export {grid['capacity_sell']:g} MW"
    if grid.get("capacity_buy") is not None:  # 0 MW is a condition too (no grid charging)
        value += f" · import {grid['capacity_buy']:g} MW"
    detail = (
        f"given condition · capacity factor {_share(grid.get('capacity_factor'))} · "
        f"export at limit {_share(grid.get('export_limit_share'))} of time"
    )
    return _check("Grid access", value, None, detail)


def _battery_vs_access(s: dict, access: float, has_pv: bool) -> dict:
    """Battery power against the export access: above it, the extra MW cannot reach the grid
    (only charge from PV); below it, the access is unused while the battery discharges, worth
    filling when one more MW earns at least ``MARGINAL_SHARE`` of an installed MW."""
    power = s["battery_power"]
    ratio = power / access
    extra = s.get("extra_power_value")
    marginal = _ratio_or_none(extra, s.get("average_power_value"))
    detail = [f"{power:g} MW battery on {access:g} MW access"]
    label = "Is the battery power coherent with the grid access?"
    if ratio > ACCESS_MARGIN:
        detail.append("extra MW only charge from PV" if has_pv else "extra MW never reach grid")
        return _check(label, f"Above access · {ratio:.0%}", "info", " · ".join(detail))
    if ratio >= ACCESS_MATCH:
        detail.append("more MW could not reach the grid")
        return _check(label, f"Matched · {ratio:.0%} of access", "ok", " · ".join(detail))
    # Below the access: is it worth filling? (arbitrage marginal value)
    if extra is not None:
        detail.append(f"+1 MW ≈ {_money(extra)}/yr, {_share(marginal)} of an installed MW")
    if marginal is None or marginal >= MARGINAL_SHARE:
        verdict = f"Below access · {ratio:.0%}, +1 MW adds {_share(marginal)}"
        return _check(label, verdict, "warn", " · ".join(detail))
    verdict = f"Below access · +1 MW adds only {_share(marginal)}"
    return _check(label, verdict, "ok", " · ".join(detail))


def _battery_vs_pv(s: dict) -> dict:
    """Battery power against the PV: it must absorb the PV above the access (clipping); PV
    lost with the battery full points to too little storage."""
    power, excess = s["battery_power"], s.get("pv_excess_mw") or 0.0
    lost = (s.get("pv_spilled_battery_full_mwh") or 0.0) / s["pv_energy_mwh"]
    detail = [f"{power / s['pv_peak']:.2f} MW per MWp"]
    detail.append(f"PV peaks {excess:.1f} MW above access")
    if s.get("battery_charge_from_pv_share") is not None:
        detail.append(f"{_share(s['battery_charge_from_pv_share'])} of charge from PV")
    detail = " · ".join(detail)
    label = "Is the battery power coherent with the PV?"
    if power < excess:
        verdict = f"Too small · PV exceeds access by {excess:.1f} MW"
        return _check(label, verdict, "warn", detail)
    if lost >= PV_SPILL_SHARE:
        return _check(label, f"PV lost · {lost:.1%} with battery full", "warn", detail)
    return _check(label, f"Covers the PV excess · {lost:.1%} lost", "ok", detail)


def _pv_vs_access(s: dict, access: float) -> dict:
    """PV peak against the export access: too much when PV is lost; room for more when the
    PV never reaches the access, or barely exceeds it (< ``LOW_CLIPPING_SHARE`` of its energy)
    and the battery has the MW to absorb that excess (a higher DC/AC ratio would be stored)."""
    lost = (s.get("pv_spilled_battery_full_mwh") or 0.0) / s["pv_energy_mwh"]
    clipping = (s.get("pv_above_connection_mwh") or 0.0) / s["pv_energy_mwh"]
    access_full = s.get("pv_hours_export_limit_share")
    excess = s.get("pv_excess_mw") or 0.0
    detail = [f"{s['pv_peak']:g} MWp peaks at {s['pv_max_mw']:.1f} MW"]
    detail.append(f"{clipping:.1%} of PV above access")
    if access_full is not None:
        detail.append(f"access full {_share(access_full)} of PV hours")
    detail = " · ".join(detail)
    label = "Is the PV peak coherent with the grid access?"
    dc_ac = f"DC/AC {s['dc_ac_ratio']:.2f}" if s.get("dc_ac_ratio") else "PV"
    if lost >= PV_SPILL_SHARE:
        return _check(label, f"Too much PV · {lost:.1%} lost", "warn", detail)
    if s["pv_max_mw"] < ACCESS_MATCH * access:
        return _check(label, f"Room for more PV · {dc_ac}", "info", detail)
    if clipping < LOW_CLIPPING_SHARE and (s.get("battery_power") or 0.0) >= excess:
        return _check(label, f"Room for more PV · {dc_ac}", "info", detail)
    return _check(label, f"Coherent · {dc_ac}", "ok", detail)


def _battery_hours(s: dict, usage: dict) -> dict:
    """Battery hours (MWh / MW): short when most days use the full SOC range and one more
    hour earns at least ``MARGINAL_SHARE`` of an installed hour, or when the cycle limit
    binds (more MWh, fewer cycles for the same energy); long when the last installed hour
    earns little or the SOC range is barely used."""
    hours, power = s["duration_hours"], s["battery_power"]
    full_days = s["full_range_days_share"] or 0.0
    next_value, average = s.get("next_hour_value"), s.get("average_energy_value")
    next_share = _ratio_or_none(next_value, average)
    last_share = _ratio_or_none(s.get("last_hour_value"), average)
    usable = (usage.get("soc_max") or 1.0) - (usage.get("soc_min") or 0.0)
    dod = usage.get("mean_daily_dod")
    budget, limit_days = s.get("yearly_budget_used"), s.get("days_at_cycle_limit_share")
    cycles_bind = (budget or 0) >= CYCLE_BUDGET_SHARE or (limit_days or 0) >= CYCLE_LIMIT_DAYS
    detail = [f"{hours:.1f} h", f"{_share(full_days)} of days use the full range"]
    if next_value is not None:
        detail.append(f"+1 h (+{power:g} MWh) ≈ {_money(next_value * power)}/yr")
    if cycles_bind and budget is not None:
        detail.append(f"cycle budget {_share(budget)} used")
    detail = " · ".join(detail)
    label = "Do the battery hours make sense?"
    if full_days >= FULL_RANGE_DAYS and (next_share is None or next_share >= MARGINAL_SHARE):
        return _check(label, f"Short · +1 h adds {_share(next_share)}", "warn", detail)
    if cycles_bind:
        return _check(label, "Short · the cycle limit binds", "warn", detail)
    if last_share is not None and last_share < LAST_HOUR_SHARE:
        return _check(label, f"Long · last hour adds {_share(last_share)}", "info", detail)
    if dod is not None and usable and dod < LOW_DOD * usable:
        return _check(label, f"Long · SOC range {_share(dod)}", "info", detail)
    value = f"Coherent · +1 h adds {_share(next_share)}" if next_share is not None else "Coherent"
    return _check(label, value, "ok", detail)


def _band_row(s: dict, afrr: dict) -> dict:
    """Informative: whether the reserve band is limited by its market cap (``max_up`` /
    ``max_down`` inputs) rather than by the battery."""
    cap_time = s["band_cap_share"] or 0.0
    cap, power = s["band_cap"], s.get("battery_power")
    detail = f"cap {cap:g} MW"
    if power:
        detail += (
            f" of {power:g} MW battery · avg band up "
            f"{_share(afrr.get('band_up_share_of_power'))} / down "
            f"{_share(afrr.get('band_down_share_of_power'))} of battery power"
        )
    label = f"{afrr.get('market') or 'Reserve'} band"
    if cap_time >= BAND_CAP_TIME:
        return _check(label, f"at market cap {_share(cap_time)} of time", None, detail)
    return _check(label, f"below the cap {_share(1 - cap_time)} of time", None, detail)


def storage_hours_figure(curve: pd.DataFrame, duration: float | None) -> go.Figure:
    """Bars of the marginal value of each storage hour; installed hours solid, the rest
    translucent, dashed line at the installed duration."""
    installed = max(1, round(duration)) if duration else 0
    solid, faded = NODE_COLORS["battery"], "rgba(105, 219, 124, 0.35)"
    fig = go.Figure(
        go.Bar(
            x=list(curve.index),
            y=curve["value"],
            marker={"color": [solid if k <= installed else faded for k in curve.index]},
            customdata=curve["positive_days"],
            hovertemplate="Hour %{x}: %{y:,.0f} €/MW·yr<br>earns on %{customdata:.0%} of days"
            "<extra></extra>",
        )
    )
    fig.update_xaxes(title_text="Storage hour", dtick=1)
    fig.update_yaxes(title_text="€/MW·year")
    apply_theme(fig, CHART_HEIGHT)
    if installed:
        fig.add_vline(
            x=installed + 0.5,
            line={"color": STATUS_COLORS["info"], "width": 1, "dash": "dash"},
            annotation_text=f"installed {duration:.1f} h",
            annotation_position="top right",
            annotation_font_color=STATUS_COLORS["info"],
        )
    return fig


def monthly_limits_figure(monthly: pd.DataFrame) -> go.Figure:
    """One line per limit: share of time (of days for the SOC range) per month; months with
    less than ``MIN_MONTH_COVERAGE`` of their hours are left out."""
    month_hours = pd.Series(monthly.index.days_in_month * 24, index=monthly.index)
    kept = monthly[monthly["hours"] >= MIN_MONTH_COVERAGE * month_hours]
    return line_figure(
        kept.drop(columns="hours"),
        colors=LIMIT_COLORS,
        labels=LIMIT_LABELS,
        unit="%",
        height=CHART_HEIGHT,
    )


def _check(label: str, value: str, status: str | None, detail: str | None) -> dict:
    return {"label": label, "value": value, "status": status, "detail": detail}


def _ratio_or_none(numerator, denominator):
    if numerator is None or not denominator:
        return None
    return numerator / denominator


def _share(value) -> str:
    return "-" if value is None else f"{value:.0%}"


def _money(value, unit: str = "€") -> str:
    return compact_text(value, unit)
