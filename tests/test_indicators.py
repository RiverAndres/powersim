"""Run indicators (powersim.runs.indicators) on tiny synthetic runs with hand-computed values."""

import numpy as np
import pandas as pd
import pytest

from powersim.runs import indicators as ind
from powersim.runs._series import battery_ratings, period_hours

BATTERY = {"capacity": 2.0, "max_power_output": 1.0, "rte": 0.8, "max_cycles_day": 1.5}


def hours(n: int, start="2025-01-01") -> pd.DatetimeIndex:
    return pd.date_range(start, periods=n, freq="h", tz="UTC")


def arbitrage_data() -> pd.DataFrame:
    """2 days, hourly. Each day: 2 h at 10 €/MWh (hours 0-1), 2 h at the top price (hours 2-3),
    the rest at 50. Top price: 100 on day 1, 200 on day 2. The battery (2 MWh / 1 MW) charges
    at 10 and discharges at 100 on day 1 and stays idle on day 2."""
    index = hours(48)
    price = np.full(48, 50.0)
    price[[0, 1, 24, 25]] = 10.0
    price[[2, 3]] = 100.0
    price[[26, 27]] = 200.0
    charge = np.zeros(48)
    charge[[0, 1]] = -1.0
    discharge = np.zeros(48)
    discharge[[2, 3]] = 1.0
    return pd.DataFrame(
        {
            "P_storage_charge": charge,
            "P_storage_discharge": discharge,
            "p_DayAhead": price,
            "E_sell_DayAhead": discharge,
            "B_benefit_DayAhead": price * (discharge + charge),
        },
        index=index,
    )


def test_period_hours_follow_the_index():
    index = pd.DatetimeIndex(["2025-01-01 00:00", "2025-01-01 00:15", "2025-01-01 01:15"])
    assert list(period_hours(index)) == [0.25, 1.0, 1.0]


def test_battery_ratings():
    ratings = battery_ratings(
        {"batteries": [BATTERY, {"capacity": 2.0, "c_rate": 0.5, "rte": 0.9}]}
    )
    assert ratings["power"] == 2.0 and ratings["capacity"] == 4.0
    assert ratings["rte"] == pytest.approx(0.85) and ratings["max_cycles_day"] == 1.5
    assert ratings["soc_min"] == 0.0 and ratings["soc_max"] == 1.0


def test_energy_price_is_the_first_energy_market():
    data = arbitrage_data().assign(p_AFRR=1.0, B_benefit_AFRR=0.0)
    assert ind.energy_price(data)[0] == "DayAhead"
    both = data.assign(p_IntraDay01=1.0, E_sell_IntraDay01=0.0, B_benefit_IntraDay01=0.0)
    assert ind.energy_markets(both) == ["DayAhead", "IntraDay01"]
    spread = ind.spread_capture({"batteries": [BATTERY]}, both)
    assert spread.kpis["other_energy_markets"] == "IntraDay01"
    assert ind.spread_capture({"batteries": [BATTERY]}, data).kpis["other_energy_markets"] is None
    assert ind.energy_price(data.drop(columns="E_sell_DayAhead"))[0] is None


def test_spread_capture_and_realized_spread():
    result = ind.spread_capture({"batteries": [BATTERY]}, arbitrage_data())
    k = result.kpis
    assert k["tbn_hours"] == 2
    # TB2 spreads: 100 − 10 and 200 − 10. Theoretical: 2 × (0.8 × 100 − 10) + 2 × (0.8 × 200 − 10).
    assert k["tbn_spread_mean"] == pytest.approx((90 + 190) / 2)
    assert k["theoretical_value"] == pytest.approx(140 + 300)
    assert k["battery_value"] == pytest.approx(2 * 100 - 2 * 10)
    assert k["tbn_capture"] == pytest.approx(180 / 440)
    assert k["tbn_cycles_factor"] == 1.5  # min(1.5, 24 / (2 × 2))
    assert k["tbn_capture_cycle_limited"] == pytest.approx(180 / (440 * 1.5))
    assert k["avg_discharge_price"] == pytest.approx(100)
    assert k["avg_charge_price"] == pytest.approx(10)
    assert k["realized_spread"] == pytest.approx(90)
    assert k["breakeven_spread"] == pytest.approx(10 * (1 / 0.8 - 1))
    daily = result.tables["daily"]
    assert list(daily["realized_spread"].round(6).fillna(-1)) == [90, -1]  # idle day 2: NaN


def test_revenue_per_cycle():
    result = ind.revenue_per_cycle({"batteries": [BATTERY]}, {}, arbitrage_data())
    # 2 MWh discharged = 1 equivalent cycle of 2 MWh.
    assert result.kpis["value_per_cycle"] == pytest.approx(180)
    assert result.kpis["value_per_mwh_discharged"] == pytest.approx(90)


def test_pv_capture():
    data = arbitrage_data()
    data["P_generation"] = 0.0
    data.loc[data.index[[2, 3]], "P_generation"] = 1.0  # PV only in the 100 €/MWh hours
    data["P_system_export"] = data["P_generation"]
    result = ind.pv_capture({"generators": [{}]}, data)
    average = data["p_DayAhead"].mean()
    assert result.kpis["pv_capture_rate"] == pytest.approx(100 / average)
    assert result.kpis["export_uplift"] == pytest.approx(0.0)
    assert not ind.pv_capture({}, arbitrage_data()).available


def test_revenue_concentration():
    revenue = np.zeros(48)
    revenue[5], revenue[30] = 30.0, -10.0
    data = pd.DataFrame({"B_benefit_X": revenue}, index=hours(48))
    k = ind.revenue_concentration(data).kpis
    assert k["top10_days_share"] == pytest.approx(30 / 20)  # 1 best day of 2, total 20
    assert k["top5_hours_share"] == pytest.approx(30 / 20)  # 3 best hours: 30 + 0 + 0
    assert k["negative_days"] == 1


def test_temporal_stability():
    index = pd.date_range("2023-01-01", "2025-06-30", freq="D", tz="UTC")
    data = pd.DataFrame({"B_benefit_X": 1.0}, index=index)  # 1 € per day
    result = ind.temporal_stability(data)
    yearly = result.tables["yearly"]
    assert list(yearly["revenue"]) == [365, 366, 181]
    assert list(yearly["complete"]) == [True, True, False]
    assert yearly["annualised"].iloc[-1] == pytest.approx(365)
    assert result.kpis["yoy_change"] == pytest.approx(366 / 365 - 1)
    monthly = data["B_benefit_X"].resample("MS").sum()
    assert result.kpis["monthly_cv"] == pytest.approx(monthly.std() / monthly.mean())


def test_grid_use():
    data = pd.DataFrame(
        {"P_system_export": [10.0, 5.0, 0.0, 0.0], "P_system_import": [0.0, 0.0, -5.0, 0.0]},
        index=hours(4),
    )
    result = ind.grid_use({"system": {"capacity_sell": 10, "capacity_buy": 5}}, data)
    k = result.kpis
    assert k["export_limit_share"] == 0.25 and k["import_limit_share"] == 0.25
    assert k["capacity_factor"] == pytest.approx(15 / (10 * 4))
    # The idle hour (net 0) is left out of the bins and counted apart.
    assert result.tables["bins"]["hours"].to_dict() == {-100.0: 1.0, 50.0: 1.0, 95.0: 1.0}
    assert k["idle_share"] == 0.25
    assert result.tables["duration"]["net_percent"].iloc[0] == pytest.approx(100)


def test_grid_export_limit_includes_efficiency():
    """Export is measured after the system efficiency: 4.9 MW is the limit of 5 MW × 0.98."""
    data = pd.DataFrame(
        {"P_system_export": [4.9, 2.45, 0.0, 0.0], "P_system_import": [0.0, 0.0, 0.0, -5.0]},
        index=hours(4),
    )
    system = {"capacity_sell": 5, "capacity_buy": 5, "efficiency": 0.98}
    result = ind.grid_use({"system": system}, data)
    k = result.kpis
    assert k["export_limit"] == pytest.approx(4.9)
    assert k["export_limit_share"] == 0.25 and k["import_limit_share"] == 0.25
    assert k["capacity_factor"] == pytest.approx((4.9 + 2.45) / (4.9 * 4))
    assert result.tables["bins"]["hours"].to_dict() == {-100.0: 1.0, 50.0: 1.0, 95.0: 1.0}


def test_negative_prices():
    data = pd.DataFrame(
        {
            "p_X": [-10.0, 0.0, 20.0, 30.0],
            "E_sell_X": [1.0, 2.0, 3.0, 0.0],
            "B_benefit_X": 0.0,
            "P_system_export": [1.0, 2.0, 3.0, 0.0],
            "P_system_import": [-4.0, 0.0, 0.0, -1.0],
        },
        index=hours(4),
    )
    k = ind.negative_prices(data).kpis
    assert k["export_at_nonpositive_mwh"] == 3.0
    assert k["import_at_negative_mwh"] == 4.0 and k["paid_to_import"] == 40.0
    assert k["nonpositive_time_share"] == 0.5


def test_battery_usage():
    data = pd.DataFrame(
        {
            "P_storage_charge": [0.0, -0.5, -1.0, 0.0],
            "P_storage_discharge": 0.0,
            "SOC_b": [0.0, 0.5, 1.0, 1.0],
        },
        index=hours(4),
    )
    result = ind.battery_usage({"batteries": [BATTERY]}, data)
    k = result.kpis
    assert k["idle_share"] == 0.5
    assert k["power_limit_share"] == 0.25  # only the -1.0 MW hour reaches the 1 MW rating
    assert k["soc_min_share"] == 0.25 and k["soc_max_share"] == 0.5
    assert k["mean_daily_dod"] == 1.0
    # SOC bins: 0 % → bin 0, 50 % → bin 50, 100 % (twice) → last bin 95.
    assert result.tables["soc_bins"]["hours"].to_dict() == {0.0: 1.0, 50.0: 1.0, 95.0: 2.0}
    assert not ind.battery_usage({}, data).available


def test_afrr_commitment():
    data = pd.DataFrame(
        {
            "Band_up_A": [2.0, 0.0, 4.0, 2.0],
            "Band_down_A": [-1.0, -1.0, 0.0, 0.0],
            "B_act_up_A": [1.0, 0.0, 0.0, 0.0],
            "B_benefit_A": 1.0,
        },
        index=hours(4),
    )
    result = ind.afrr_commitment({"batteries": [{"capacity": 4.0, "max_power_output": 2.0}]}, data)
    k = result.kpis
    assert k["band_up_mean"] == 2.0 and k["band_up_share_of_power"] == 1.0
    assert k["band_down_mean"] == 0.5 and k["band_down_share_of_power"] == 0.25
    assert k["band_time_share"] == 1.0
    assert k["max_band_over_power"] == 2.0  # 4 MW band on a 2 MW battery
    assert k["activation_revenue_share"] == 0.25
    assert result.tables["bins"]["up"].to_dict() == {0.0: 1.0, 50.0: 0.0, 100.0: 2.0, 200.0: 1.0}
    assert not ind.afrr_commitment({}, data.drop(columns=["Band_up_A", "Band_down_A"])).available


def test_all_indicators_without_battery():
    data = arbitrage_data()
    results = ind.all_indicators({"system": {"capacity_sell": 1}}, {}, data)
    assert not results["spread"].available and results["spread"].reason
    assert results["concentration"].available
    for result in results.values():  # JSON-serialisable scalars
        assert all(v is None or isinstance(v, (int, float, str)) for v in result.kpis.values())


def sizing_data() -> pd.DataFrame:
    """``arbitrage_data`` with grid flows, SOC (full range on day 1 only) and a reserve band
    always at its 0.5 MW cap."""
    data = arbitrage_data()
    soc = np.zeros(48)
    soc[[0, 1, 2]] = [0.5, 1.0, 0.5]
    return data.assign(
        P_system_export=data["P_storage_discharge"],
        P_system_import=data["P_storage_charge"],
        SOC_b=soc,
        Band_up_AFRR=0.5,
    )


SIZING_INPUTS = {
    "system": {"capacity_sell": 1.0, "capacity_buy": 1.0, "efficiency": 1.0},
    "batteries": [{**BATTERY, "max_cycles_day_yearly_avg": 1 / 365}],
    "markets": [{"type": "AFRR", "params": {"max_up": 0.5, "max_down": 0.5}}],
}


def test_marginal_duration():
    # Day 1: 2 h at 10, 2 h at 100; day 2: 2 h at 10, 2 h at 200; the rest at 50; RTE 0.8.
    curve = ind.marginal_duration(arbitrage_data()["p_DayAhead"], rte=0.8)
    assert list(curve.index) == list(range(1, 13))
    # Hours 1-2: mean(0.8 × 100 − 10, 0.8 × 200 − 10) = 110 €/MW per day, × 365.
    assert curve["value"].loc[1] == pytest.approx(110 * 365)
    assert curve["value"].loc[2] == pytest.approx(110 * 365)
    assert curve["value"].loc[3] == 0.0 and curve["positive_days"].loc[3] == 0.0
    assert curve["positive_days"].loc[1] == 1.0
    assert ind.marginal_duration(arbitrage_data()["p_DayAhead"].iloc[:4], 0.8).empty


def test_sizing_battery_grid_and_band():
    result = ind.sizing(SIZING_INPUTS, sizing_data())
    k = result.kpis
    # Grid: limit 1 MW, the 1 MW battery cannot exceed it on either side.
    assert k["export_limit"] == 1.0 and k["plant_max_export"] == 1.0
    assert k["import_limit"] == 1.0 and k["plant_max_import"] == 1.0
    assert k["limit_price_premium"] == 0.0  # it only exports at the limit
    assert k["curtailed_mwh"] == 0.0
    # Battery power: every MWh moved at full power.
    assert k["throughput_at_power_limit"] == 1.0 and k["battery_power"] == 1.0
    # Battery energy: 2 h; full range on 1 of 2 days; hours 1-2 earn 110 €/day, hour 3 nothing.
    assert k["duration_hours"] == 2.0 and k["full_range_days_share"] == 0.5
    assert k["last_hour_value"] == pytest.approx(110 * 365) and k["next_hour_value"] == 0.0
    assert k["extra_power_value"] == pytest.approx(0.0)
    assert k["average_power_value"] == pytest.approx(220 * 365)
    assert k["average_energy_value"] == pytest.approx(110 * 365)
    # Cycles: 2 MWh discharged on day 1 → mean 0.5/day; Σ|ΔSOC|/2 = 0.75 of a 1-cycle budget.
    assert k["mean_cycles_day"] == 0.5 and k["days_at_cycle_limit_share"] == 0.0
    assert k["yearly_budget_used"] == pytest.approx(0.75)
    # Band always at its cap.
    assert k["band_cap_share"] == 1.0 and k["band_cap"] == 0.5
    monthly = result.tables["monthly"]
    assert monthly["export_limit"].iloc[0] == pytest.approx(2 / 48)
    assert monthly["battery_power"].iloc[0] == pytest.approx(4 / 48)
    assert monthly["full_range_days"].iloc[0] == 0.5 and monthly["hours"].iloc[0] == 48
    assert all(v is None or isinstance(v, (int, float, str)) for v in k.values())


def test_sizing_pv():
    data = pd.DataFrame(
        {
            "P_generation": [0.0, 1.5, 2.0, 0.5],
            "P_excess": [0.0, 0.0, 0.5, 0.0],
            "P_system_sell_generation": [0.0, 1.0, 1.0, 0.5],
            "P_system_export": [0.0, 1.0, 1.0, 0.5],
            "p_DayAhead": [10.0, -5.0, 20.0, 0.0],
            "E_sell_DayAhead": 0.0,
            "B_benefit_DayAhead": 0.0,
            "SOC_b": [0.2, 1.0, 1.0, 1.0],
        },
        index=hours(4),
    )
    inputs = {
        "system": {"capacity_sell": 1.0, "efficiency": 1.0},
        "batteries": [BATTERY],
        "generators": [{"peak_power": 2.0}],
    }
    k = ind.sizing(inputs, data).kpis
    assert k["pv_energy_mwh"] == 4.0 and k["dc_ac_ratio"] == 2.0
    assert k["pv_above_connection_mwh"] == 1.5  # 0.5 + 1.0 MWh above 1 MW
    assert k["curtailed_mwh"] == 0.5 and k["curtailed_value"] == 10.0
    # Battery full in hours 1-3: sold at ≤ 0 in hours 1 (1 MWh) and 3 (0.5) + curtailed 0.5.
    assert k["pv_spilled_battery_full_mwh"] == 2.0
    assert k["plant_max_export"] == 3.0  # (1 MW battery + 2 MW PV) × efficiency
    assert k["pv_peak"] == 2.0 and k["pv_max_mw"] == 2.0 and k["pv_excess_mw"] == 1.0
    # Producing hours 1-3, export at the 1 MW limit in hours 1 and 2.
    assert k["pv_hours_export_limit_share"] == pytest.approx(2 / 3)
    assert k["battery_charge_from_pv_share"] is None  # no battery charge at all
    assert "marginal_duration" not in ind.sizing(inputs, data).tables  # fewer than 24 h
