# Use case where a set of system configurations are studied to determine the optimal one.
# The data is exported to the specified address in Excel format, by default in downloads.
import pandas as pd
# from ..cook_book import recipe
from ..models.modules import System
from ..markets.markets import DayAhead
from ..optimizers.perfect_optimizer import PerfectOptimizer

class Sizing:
    @staticmethod
    def sizing_export_pv_bess(
            systems: list[System],
            market: DayAhead,
            path: str | None = None,
        ):
        """
        Obtains the revenues for the chosen configurations of a system with one photovoltaic object and one battery object.
        
        :var system: Description
        :vartype system: float
        :var filename: Description
        :vartype filename: float
        """

        rows = []

        for system in systems:
            print(system)
            optimizer = PerfectOptimizer(system = system, market = market).solve()
            system_revenues: dict = {"revenues": optimizer.results.operation_timeseries_year.iloc[0]["B_benefit"]}

            photovoltaic_dict: dict = {**system.generators[0].__dict__}
            battery_dict: dict = {**system.batteries[0].__dict__}
            system_dict: dict = {**system.__dict__}
            del photovoltaic_dict["production"]
            del system_dict["generators"]
            del system_dict["batteries"]

            data:dict = {**photovoltaic_dict, **battery_dict, **system_dict, **system_revenues}
            rows.append(data)

        df_export: pd.DataFrame = pd.DataFrame(rows)
        df_export.to_excel(excel_writer = path)

        return df_export
