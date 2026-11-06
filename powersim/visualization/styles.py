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


def color_for(variable: str) -> str:
    """Color of a series; variables without a fixed color get a stable color from a palette."""
    if variable in MARKET_COLORS:
        return MARKET_COLORS[variable]
    if variable in ASSET_COLORS:
        return ASSET_COLORS[variable]
    return _FALLBACK_PALETTE[zlib.crc32(variable.encode()) % len(_FALLBACK_PALETTE)]
