"""Colors shared by the matplotlib plots (SimulationResult) and the Dash dashboard."""

import zlib

# Market series. Keys are the column names of SimulationResult.operation_timeseries.
MARKET_COLORS = {
    "P_sell_DayAhead": "turquoise",
    "P_buy_DayAhead": "turquoise",
    "P_sell_IntraDay01": "mediumspringgreen",
    "P_buy_IntraDay01": "mediumspringgreen",
    "P_sell_IntraDay02": "mediumseagreen",
    "P_buy_IntraDay02": "mediumseagreen",
    "P_sell_IntraDay03": "forestgreen",
    "P_buy_IntraDay03": "forestgreen",
    "Band_up_AFRR": "lightsalmon",
    "Band_down_AFRR": "lightsalmon",
    "P_up_AFRR": "red",
    "P_down_AFRR": "red",
    "P_sell_MFRR": "gold",
    "P_buy_MFRR": "gold",
    "p_DayAhead": "turquoise",
    "p_IntraDay01": "mediumspringgreen",
    "p_IntraDay02": "mediumseagreen",
    "p_IntraDay03": "forestgreen",
    "p_up_AFRR": "lightsalmon",
    "p_down_AFRR": "lightsalmon",
    "p_act_up_AFRR": "red",
    "p_act_down_AFRR": "red",
    "p_MFRR": "gold",
}

# System and asset series.
ASSET_COLORS = {
    "P_generation": "gold",
    "P_storage_charge": "red",
    "P_storage_discharge": "green",
    "P_system_export": "green",
    "P_system_import": "red",
    "P_excess": "black",
}

# Base color of each market, used by any series of that market without a fixed color
# (variables ending in "_<market>", e.g. B_benefit_AFRR, E_up_AFRR) and by per-market aggregates.
MARKET_BASE_COLORS = {
    "DayAhead": "turquoise",
    "IntraDay01": "mediumspringgreen",
    "IntraDay02": "mediumseagreen",
    "IntraDay03": "forestgreen",
    "AFRR": "lightsalmon",
    "MFRR": "gold",
}

# Energy flows between PV, battery and grid, and the nodes of a flow diagram (hex, so that
# translucent variants can be derived).
FLOW_COLORS = {
    "pv_to_grid": "#fcc419",
    "pv_to_battery": "#ff922b",
    "grid_to_battery": "#ff6b6b",
    "battery_to_grid": "#69db7c",
    "curtailment": "#868e96",
    "losses": "#5c5f66",
}
NODE_COLORS = {
    "pv": "#fcc419",
    "grid": "#4dabf7",
    "battery": "#69db7c",
    "curtailment": "#868e96",
    "losses": "#5c5f66",
}

# Status of a check (ok / warn / info); same values as --positive / --warn / --accent in the
# dashboard CSS.
STATUS_COLORS = {"ok": "#69db7c", "warn": "#ffa94d", "info": "#4dabf7"}

_FALLBACK_PALETTE = (
    "steelblue",
    "darkorange",
    "purple",
    "saddlebrown",
    "hotpink",
    "olive",
    "teal",
    "slategray",
)


def market_color(market: str) -> str:
    """Base color of a market (stable palette color for unknown markets)."""
    return color_for(market)


def color_for(variable: str) -> str:
    """Color of a series or market name.

    Fixed colors first, then the market base color for variables ending in ``_<market>``; any
    other variable gets a stable color from a palette.
    """
    if variable in MARKET_COLORS:
        return MARKET_COLORS[variable]
    if variable in ASSET_COLORS:
        return ASSET_COLORS[variable]
    if variable in MARKET_BASE_COLORS:
        return MARKET_BASE_COLORS[variable]
    market = variable.rsplit("_", 1)[-1]
    if "_" in variable and market in MARKET_BASE_COLORS:
        return MARKET_BASE_COLORS[market]
    return _FALLBACK_PALETTE[zlib.crc32(variable.encode()) % len(_FALLBACK_PALETTE)]
