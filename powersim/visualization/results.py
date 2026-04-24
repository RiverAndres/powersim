import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import pyomo.environ as pyo

from ..models.modules import System, Battery, Photovoltaic
from ..markets.base import Market

class SimulationResult:
    """
    Container of simulations results.
    """

    def __init__(self, optimizer_name: str, markets: list[Market], system: System, simulation: pyo.ConcreteModel):
        self.optimizer_name = optimizer_name
        self.markets = markets
        self.system = system
        self.simulation = simulation

        self.operation_storage_list = [b.results(self.simulation) for b in self.system.batteries]
        self.operation_generation_list = [g.results() for g in self.system.generators]
        self.operation_system = self.system.results(self.simulation)

        # self.operation_system: df that contains timeseries of the operation of the system.
        system_output = self.operation_system["P_grid_export"] - self.operation_system["P_grid_import"]
        self.operation_system["P_grid_import"] = system_output.clip(upper = 0)
        self.operation_system["P_grid_export"] = system_output.clip(lower = 0) * self.system.efficiency
        self.operation_system["E_grid_buy"] = self.operation_system["P_grid_import"] * self.operation_system["dt"]
        self.operation_system["E_grid_sell"] = self.operation_system["P_grid_export"] * self.operation_system["dt"]
        self.operation_system["P_excess"] = self.operation_system["P_excess"]

        # self.operation_storage: df that contains timeseries of the aggregated operation of all the storage assets within the sistem.
        self.operation_storage = pd.DataFrame(index = self.operation_system.index)
        self.operation_storage[["P_charge", "P_discharge", "E_charge", "E_discharge"]] = 0

        for storage in self.operation_storage_list:
            storage_p_output = storage["P_discharge"] - storage["P_charge"]
            storage_e_output = storage["E_discharge"] - storage["E_charge"]
            storage["P_charge"] = - storage["P_charge"]
            storage["E_charge"] = - storage["E_charge"]
            storage_name = storage["name"].iloc[0]
            self.operation_storage["P_charge"] += storage_p_output.clip(upper = 0)
            self.operation_storage["P_discharge"] += storage_p_output.clip(lower = 0)
            self.operation_storage["E_charge"] += storage_e_output.clip(upper = 0)
            self.operation_storage["E_discharge"] += storage_e_output.clip(lower = 0)
            self.operation_storage[f"SOC_{storage_name}"] = storage["SOC"]
            self.operation_storage[f"charge_{storage_name}"] = storage["charge"]
            self.operation_storage[f"discharge_{storage_name}"] = storage["discharge"]
            self.operation_storage[f"rest_{storage_name}"] = storage["rest"]
            self.operation_storage[f"RSOC_{storage_name}"] = storage["RSOC"]

        # self.operation_generation: df that contains timeseries of the aggregated operation of all the generation assets within the sistem.
        self.operation_generation = pd.DataFrame(index = self.operation_system.index)
        self.operation_generation["P_gen"] = 0

        for generator in self.operation_generation_list:
            self.operation_generation["P_gen"] += generator["P_gen"]

        # self.operation_comercialization: df that contains timeseries of the comercialization of the energy of the system.
        self.operation_market = pd.DataFrame(index = self.operation_system.index)

        for market in self.markets:
            name = market.__class__.__name__
            operation_single_market = market.results(self.simulation)

            if name == "AFRR":
                self.operation_market[f"p_up_{name}"] = operation_single_market[f"p_up_{name}"]
                self.operation_market[f"p_down_{name}"] = operation_single_market[f"p_down_{name}"]
                self.operation_market[f"p_act_up_{name}"] = operation_single_market[f"p_act_up_{name}"]
                self.operation_market[f"p_act_down_{name}"] = operation_single_market[f"p_act_down_{name}"]
                self.operation_market[f"Band_up_{name}"] = operation_single_market[f"Band_up_{name}"]
                self.operation_market[f"Band_down_{name}"] = operation_single_market[f"Band_down_{name}"]
                self.operation_market[f"P_up_{name}"] = operation_single_market[f"P_up_{name}"]
                self.operation_market[f"P_down_{name}"] = - operation_single_market[f"P_down_{name}"]
                self.operation_market[f"E_up_{name}"] = self.operation_market[f"P_up_{name}"]  * self.operation_system["dt"]
                self.operation_market[f"E_down_{name}"] = self.operation_market[f"P_down_{name}"]  * self.operation_system["dt"]
                self.operation_market[f"B_band_up_{name}"] = self.operation_market[f"Band_up_{name}"] * self.operation_market[f"p_up_{name}"]
                self.operation_market[f"B_band_down_{name}"] = self.operation_market[f"Band_down_{name}"] * self.operation_market[f"p_down_{name}"]
                self.operation_market[f"B_act_up_{name}"] = self.operation_market[f"E_up_{name}"] * self.operation_market[f"p_act_up_{name}"]
                self.operation_market[f"B_act_down_{name}"] = self.operation_market[f"E_down_{name}"] * self.operation_market[f"p_act_down_{name}"]
                self.operation_market[f"B_benefit_{name}"] = self.operation_market[f"B_band_up_{name}"] + self.operation_market[f"B_band_down_{name}"] + self.operation_market[f"B_act_up_{name}"] + self.operation_market[f"B_act_down_{name}"]
            else:
                self.operation_market[f"p_{name}"] = operation_single_market[f"p_{name}"]
                self.operation_market[f"P_sell_{name}"] = operation_single_market[f"P_sell_{name}"]
                self.operation_market[f"P_buy_{name}"] = - operation_single_market[f"P_buy_{name}"]
                self.operation_market[f"E_sell_{name}"] = self.operation_market[f"P_sell_{name}"] * self.operation_system["dt"]
                self.operation_market[f"E_buy_{name}"] = self.operation_market[f"P_buy_{name}"] * self.operation_system["dt"]
                self.operation_market[f"B_sell_{name}"] = self.operation_market[f"E_sell_{name}"] * self.operation_market[f"p_{name}"]
                self.operation_market[f"B_buy_{name}"] = self.operation_market[f"E_buy_{name}"] * self.operation_market[f"p_{name}"]
                self.operation_market[f"B_benefit_{name}"] = self.operation_market[f"B_sell_{name}"] + self.operation_market[f"B_buy_{name}"]

        # self.operation_timeseries: df that contains timeseries information to use to plot, or export data.
        self.operation_timeseries = pd.DataFrame(index = self.operation_system.index)
        self.operation_timeseries["P_system_import"] = self.operation_system["P_grid_import"]
        self.operation_timeseries["P_system_export"] = self.operation_system["P_grid_export"]
        self.operation_timeseries["P_generation"] = self.operation_generation["P_gen"]
        self.operation_timeseries["P_excess"] = self.operation_system["P_excess"]
        self.operation_timeseries["P_storage_charge"] = self.operation_storage["P_charge"]
        self.operation_timeseries["P_storage_discharge"] = self.operation_storage["P_discharge"]

        self.operation_timeseries["P_system_sell_generation"] = pd.Series(self.operation_generation["P_gen"].clip(upper = 0) + self.operation_generation["P_gen"].clip(lower = 0) * self.system.efficiency + self.operation_storage["P_charge"] + self.operation_system["P_grid_import"] - self.operation_system["P_excess"]).clip(lower = 0)
        self.operation_timeseries["P_system_sell_storage"] = pd.Series(self.operation_storage["P_discharge"] * self.system.efficiency + self.operation_generation["P_gen"].clip(upper = 0)).clip(lower = 0)

        self.operation_timeseries["P_storage_charge_generation"] = pd.Series(- self.operation_generation["P_gen"].clip(lower = 0) + self.operation_system["P_excess"] + self.operation_system["P_grid_export"] / self.system.efficiency).clip(upper = 0)
        self.operation_timeseries["P_storage_charge_grid"] = self.operation_system["P_grid_import"] * self.system.efficiency - self.operation_generation["P_gen"].clip(upper = 0)

        self.operation_timeseries["E_system_sell_generation"] = self.operation_timeseries["P_system_sell_generation"] * self.operation_system["dt"]
        self.operation_timeseries["E_system_sell_storage"] = self.operation_timeseries["P_system_sell_storage"] * self.operation_system["dt"]

        self.operation_timeseries["E_storage_charge_generation"] = self.operation_timeseries["P_storage_charge_generation"] * self.operation_system["dt"]
        self.operation_timeseries["E_storage_charge_grid"] = self.operation_timeseries["P_storage_charge_grid"] * self.operation_system["dt"]
        
        # self.operation_timeseries["B_system_sell_generation_DA"] = self.operation_timeseries[f"p_DayAhead"] * (self.operation_timeseries["E_system_sell_generation"])
        # self.operation_timeseries["B_system_sell_storage_DA"] = self.operation_timeseries[f"p_DayAhead"] * (self.operation_timeseries["E_system_sell_storage"] - self.operation_timeseries["E_system_sell_generation"]).clip(lower = 0)

        for storage in self.operation_storage_list:
            storage_name = storage["name"].iloc[0]
            self.operation_timeseries[f"SOC_{storage_name}"] = self.operation_storage[f"SOC_{storage_name}"]
            self.operation_timeseries[f"charge_{storage_name}"] = self.operation_storage[f"charge_{storage_name}"]
            self.operation_timeseries[f"discharge_{storage_name}"] = self.operation_storage[f"discharge_{storage_name}"]
            self.operation_timeseries[f"rest_{storage_name}"] = self.operation_storage[f"rest_{storage_name}"]
            self.operation_timeseries[f"RSOC_{storage_name}"] = self.operation_storage[f"RSOC_{storage_name}"]

        for market in self.markets:
            name = market.__class__.__name__

            if name == "AFRR":
                self.operation_timeseries[f"p_up_{name}"] = self.operation_market[f"p_up_{name}"]
                self.operation_timeseries[f"p_down_{name}"] = self.operation_market[f"p_down_{name}"]
                self.operation_timeseries[f"p_act_up_{name}"] = self.operation_market[f"p_act_up_{name}"]
                self.operation_timeseries[f"p_act_down_{name}"] = self.operation_market[f"p_act_down_{name}"]
                self.operation_timeseries[f"Band_up_{name}"] = self.operation_market[f"Band_up_{name}"]
                self.operation_timeseries[f"Band_down_{name}"] = - self.operation_market[f"Band_down_{name}"]
                self.operation_timeseries[f"P_up_{name}"] = self.operation_market[f"P_up_{name}"]
                self.operation_timeseries[f"P_down_{name}"] = self.operation_market[f"P_down_{name}"]
                self.operation_timeseries[f"E_up_{name}"] = self.operation_market[f"E_up_{name}"]
                self.operation_timeseries[f"E_down_{name}"] = self.operation_market[f"E_down_{name}"]
                self.operation_timeseries[f"B_band_up_{name}"] = self.operation_market[f"B_band_up_{name}"]
                self.operation_timeseries[f"B_band_down_{name}"] = self.operation_market[f"B_band_down_{name}"]
                self.operation_timeseries[f"B_act_up_{name}"] = self.operation_market[f"B_act_up_{name}"]
                self.operation_timeseries[f"B_act_down_{name}"] = self.operation_market[f"B_act_down_{name}"]
                self.operation_timeseries[f"B_benefit_{name}"] = self.operation_market[f"B_benefit_{name}"]
            else:
                self.operation_timeseries[f"p_{name}"] = self.operation_market[f"p_{name}"]
                self.operation_timeseries[f"P_sell_{name}"] = self.operation_market[f"P_sell_{name}"]
                self.operation_timeseries[f"P_buy_{name}"] = self.operation_market[f"P_buy_{name}"]
                self.operation_timeseries[f"E_sell_{name}"] = self.operation_market[f"E_sell_{name}"]
                self.operation_timeseries[f"E_buy_{name}"] = self.operation_market[f"E_buy_{name}"]
                self.operation_timeseries[f"B_sell_{name}"] = self.operation_market[f"B_sell_{name}"]
                self.operation_timeseries[f"B_buy_{name}"] = self.operation_market[f"B_buy_{name}"]
                self.operation_timeseries[f"B_benefit_{name}"] = self.operation_market[f"B_benefit_{name}"]

        self.operation_timeseries = self.operation_timeseries.round(decimals = 4)

        # agg_data_format = {
        #     "price":"mean",
        #     "E_buy":"sum",
        #     "E_sell":"sum",
        #     "B_buy":"sum",
        #     "B_sell":"sum",
        #     "B_benefit":"sum",
        # }
        
        # self.operation_timeseries_month = self.operation_timeseries[agg_data_format.keys()].resample("MS").agg(agg_data_format)
        # self.operation_timeseries_quarter = self.operation_timeseries[agg_data_format.keys()].resample("QS").agg(agg_data_format)
        # self.operation_timeseries_year = self.operation_timeseries[agg_data_format.keys()].resample("YS").agg(agg_data_format)

        self.operation_timeseries_year = self.operation_timeseries.resample("YS").sum()

    def plot_operation(self):
        """
        Detailed graphs that shopw the timeseries of the operation of the system and the exchanges of enrgy between modules and the grid.
        """

        styles = {
            "colors": {
                f"P_sell_DayAhead":"turquoise",
                f"P_buy_DayAhead":"turquoise",
                f"P_sell_IntraDay01":"mediumspringgreen",
                f"P_buy_IntraDay01":"mediumspringgreen",
                f"P_sell_IntraDay02":"mediumseagreen",
                f"P_buy_IntraDay02":"mediumseagreen",
                f"P_sell_IntraDay03":"forestgreen",
                f"P_buy_IntraDay03":"forestgreen",
                f"Band_up_AFRR":"lightsalmon",
                f"Band_down_AFRR":"lightsalmon",
                f"P_up_AFRR":"red",
                f"P_down_AFRR":"red",
                f"P_sell_MFRR":"gold",
                f"P_buy_MFRR":"gold",

                f"p_DayAhead":"turquoise",
                f"p_IntraDay01":"mediumspringgreen",
                f"p_IntraDay02":"mediumseagreen",
                f"p_IntraDay03":"forestgreen",
                f"p_up_AFRR":"lightsalmon",
                f"p_down_AFRR":"lightsalmon",
                f"p_act_up_AFRR":"red",
                f"p_act_down_AFRR":"red",
                f"p_MFRR":"gold",
            }
        }

        fig1, (ax_gen, ax_storage, ax_system) = plt.subplots(3, 1, sharex = True, sharey = True)
        fig2, (ax_market_prices, ax_market_operation) = plt.subplots(2, 1, sharex = True)
        fig3, (ax_excess) = plt.subplots(1, 1, sharex = True)

        ax_market_prices.set_xlabel("")
        ax_market_prices.set_title("Market Prices")

        ax_gen.set_xlabel("MW")
        ax_gen.set_title("Generation modules power production")

        ax_storage.set_xlabel("MW")
        ax_storage.set_title("Storage modules power")

        ax_system.set_xlabel("MW")
        ax_system.set_title("Power output at POI")

        ax_market_prices.set_xlabel("")
        ax_market_prices.set_title("Market prices")

        ax_market_operation.set_xlabel("MW")
        ax_market_operation.set_title("Market operation")

        ax_excess.set_xlabel("MW")
        ax_excess.set_title("Excess power")

        # self.operation_timeseries.plot(y = "price", kind = "line", ax = ax_pmd, color = "k")
        self.operation_timeseries.plot(y = ["P_system_export"], kind = "area", ax = ax_system, color = ["green"], linewidth = 0.1)
        self.operation_timeseries.plot(y = ["P_system_import"], kind = "area", ax = ax_system, color = ["red"], linewidth = 0.1) 

        self.operation_timeseries.plot(y =  "P_generation", kind = "area", ax = ax_gen, color = "yellow", linewidth = 0.1, stacked = False)
        self.operation_timeseries.plot(y = ["P_storage_charge"], kind = "area", ax = ax_storage, color = ["red"], linewidth = 0.1)
        self.operation_timeseries.plot(y = ["P_storage_discharge"], kind = "area", ax = ax_storage, color = "green", linewidth = 0.1)

        self.operation_timeseries.plot(y = ["P_excess"], kind = "area", ax = ax_excess, color = ["k"], linewidth = 0.1)
        
        stacked_area_plots = []
        colors_area_plots = []
        
        for market in self.markets:
            name = market.__class__.__name__


            if name == "AFRR":
                self.operation_timeseries.plot(y = f"p_up_{name}", kind = "line", ax = ax_market_prices, color = styles["colors"][f"p_up_{name}"])
                self.operation_timeseries.plot(y = f"p_down_{name}", kind = "line", ax = ax_market_prices, color = styles["colors"][f"p_down_{name}"])
                self.operation_timeseries.plot(y = f"p_act_up_{name}", kind = "line", ax = ax_market_prices, color = styles["colors"][f"p_act_up_{name}"])
                self.operation_timeseries.plot(y = f"p_act_down_{name}", kind = "line", ax = ax_market_prices, color = styles["colors"][f"p_act_down_{name}"])

                # self.operation_timeseries.plot(y = f"Band_up_{name}", kind = "area", ax = ax_market_operation, color = styles["colors"][f"Band_up_{name}"], linewidth = 0.1, alpha = 0.5)
                # self.operation_timeseries.plot(y = f"Band_down_{name}", kind = "area", ax = ax_market_operation, color = styles["colors"][f"Band_down_{name}"], linewidth = 0.1, alpha = 0.5)
                # self.operation_timeseries.plot(y = f"P_up_{name}", kind = "area", ax = ax_market_operation, color = styles["colors"][f"P_up_{name}"], linewidth = 0.1, stacked = True)
                # self.operation_timeseries.plot(y = f"P_down_{name}", kind = "area", ax = ax_market_operation, color = styles["colors"][f"P_down_{name}"], linewidth = 0.1, stacked = True)
                
                stacked_area_plots += [f"P_up_{name}", f"P_down_{name}", f"Band_up_{name}", f"Band_down_{name}"]
                colors_area_plots += [styles["colors"][f"P_up_{name}"], styles["colors"][f"P_down_{name}"], styles["colors"][f"Band_up_{name}"], styles["colors"][f"Band_down_{name}"]]

            else:
                self.operation_timeseries.plot(y = f"p_{name}", kind = "line", ax = ax_market_prices, color = styles["colors"][f"p_{name}"])

                # self.operation_timeseries.plot(y = f"P_sell_{name}", kind = "area", ax = ax_market_operation, color = styles["colors"][f"P_sell_{name}"], linewidth = 0.1, stacked = True)
                # self.operation_timeseries.plot(y = f"P_buy_{name}", kind = "area", ax = ax_market_operation, color = styles["colors"][f"P_sell_{name}"], linewidth = 0.1, stacked = True)
                
                stacked_area_plots += [f"P_sell_{name}", f"P_buy_{name}"]
                colors_area_plots += [styles["colors"][f"P_sell_{name}"], styles["colors"][f"P_sell_{name}"]]
                
        self.operation_timeseries.plot(y = stacked_area_plots, kind = "area", ax = ax_market_operation, color = colors_area_plots, linewidth = 0.1, stacked = True)


        plt.show()

    def plot_battery_kpis(self):
        """
        Analysis of the batteries and useful KPIs.
        """
        pass
        
    def plot_revenues(self):
        """
        Montlhy revenues of the system my module and market
        """
        pass
        
    def print(self):
        """
        Prints a summary of the results of the simulation.
        """
        print(self.operation_storage)

        print(self.operation_generation)

        print(self.operation_system)

        # print(self.operation_comercialization)

        print(self.operation_timeseries)

        # print(self.operation_timeseries_month)

        # print(self.operation_timeseries_year)

    def export(self, path):
        """
        Exports the results in a .xlsx document.
        """
        fmt = "%Y-%m-%dT%H:%M:%SZ"
        operation_timeseries = self.operation_timeseries.copy()
        # operation_timeseries_month = self.operation_timeseries_month.copy()
        # operation_timeseries_year = self.operation_timeseries_year.copy()

        operation_system = self.operation_system.copy()

        operation_timeseries.index = operation_timeseries.index.strftime(fmt)
        # operation_timeseries_month.index = operation_timeseries_month.index.strftime(fmt)
        # operation_timeseries_year.index = operation_timeseries_year.index.strftime(fmt)

        operation_system.index = operation_system.index.strftime(fmt)

        with pd.ExcelWriter(path) as writer:
            operation_timeseries.to_excel(writer, sheet_name = 'operation_timeseries')
            # operation_timeseries_month.to_excel(writer, sheet_name = 'operation_timeseries_month')
            # operation_timeseries_year.to_excel(writer, sheet_name = 'operation_timeseries_year')

            operation_system.to_excel(writer, sheet_name = 'test')

    def save(self, path = ""):
        """
        Save as pickle simulation results, by default in cache.
        """
        pass

