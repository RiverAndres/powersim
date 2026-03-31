from abc import ABC, abstractmethod
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from scipy.optimize import curve_fit

from powersim import System, Battery, Photovoltaic

class Visualizer():
    """
    Recives the ``result`` of the simulation.

    ``result`` Properties:
        * self.optimizer_name
        * self.market_name = DayAhead
        * self.market = instance of DayAhead
        * self.system = instance of System
        * self.simulation = instance of the simulation that contains a feasible solution.

    Useful information
        self.system.batteries : list[Battery]
            .results(self.simulation) : list[pd.DataFrame] ; datetimeIndex, columns = ["P_charge", "P_discharge", "SOC", "dt", "E_charge", "E_discharge"]
        self.system.generators : list[GenerationModule]
            .results() : list[pd.DataFrame] ; datetimeIndex, columns = ["P_gen"]
        self.system : System()
            .results(self.simulation) : pd.DataFrame ; datetimeIndex, columns = ["P_grid_buy", "P_grid_sell", "P_excess"]
    """

    def __init__(self, result):
        self.system: System = result.system
        self.simulation = result.simulation
        self.market = result.market

        self.operation_storage_list = [b.results(self.simulation) for b in self.system.batteries]
        self.operation_generation_list = [g.results() for g in self.system.generators]

        # self.operation_system: df that contains timeseries of the operation of the system.
        self.operation_system = self.system.results(self.simulation)
        self.operation_system["P_grid_buy"] = - self.operation_system["P_grid_buy"]
        self.operation_system["P_grid_sell"] = self.operation_system["P_grid_sell"] * self.system.efficiency
        self.operation_system["E_grid_buy"] = self.operation_system["P_grid_buy"] * self.operation_system["dt"]
        self.operation_system["E_grid_sell"] = self.operation_system["P_grid_sell"] * self.operation_system["dt"]

        if len(self.system.generators) == 0:
            system_power = sum([battery.max_power_output for battery in self.system.batteries])
            energy_produced = 1
        else:
            # print(self.system.generators[0].production)
            system_power = sum([generator.peak_power for generator in self.system.generators])
            energy_produced = sum([sum(generator.production["power"] * self.operation_system["dt"]) for generator in self.system.generators])

        if len(self.system.batteries) == 0:
            system_capacity = 1
        else:
            system_capacity = sum([battery.capacity for battery in self.system.batteries])

        # self.operation_storage: df that contains timeseries of the aggregated operation of all the storage assets within the sistem.
        self.operation_storage = pd.DataFrame(index = self.operation_system.index)
        self.operation_storage[["P_charge", "P_discharge", "E_charge", "E_discharge"]] = 0

        for storage in self.operation_storage_list:
            storage["P_charge"] = - storage["P_charge"]
            storage["E_charge"] = - storage["E_charge"]
            storage_name = storage["name"].iloc[0]
            self.operation_storage["P_charge"] += storage["P_charge"]
            self.operation_storage["P_discharge"] += storage["P_discharge"]
            self.operation_storage["E_charge"] += storage["E_charge"]
            self.operation_storage["E_discharge"] += storage["E_discharge"]
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
        self.operation_comercialization = pd.DataFrame(index = self.operation_system.index)
        self.operation_comercialization["price"] = self.market.datasets["p_pmd"]["value"]
        self.operation_comercialization[["E_buy","E_sell"]] = self.operation_system[["E_grid_buy", "E_grid_sell"]]
        self.operation_comercialization["B_buy"] = self.operation_comercialization["E_buy"] * self.operation_comercialization["price"]
        self.operation_comercialization["B_sell"] = self.operation_comercialization["E_sell"] * self.operation_comercialization["price"]
        self.operation_comercialization["B_benefit"] = self.operation_comercialization["B_buy"] + self.operation_comercialization["B_sell"]

        # self.operation_timeseries: df that contains timeseries information to use to plot, or export data.
        self.operation_timeseries = pd.DataFrame(index = self.operation_system.index)
        self.operation_timeseries["price"] = self.operation_comercialization["price"]
        self.operation_timeseries["P_system_sell_storage"] = self.operation_storage["P_discharge"] * self.system.efficiency 
        self.operation_timeseries["P_system_sell_generation"] = pd.Series(self.operation_generation["P_gen"] * self.system.efficiency + self.operation_storage["P_charge"] + self.operation_system["P_grid_buy"]).clip(lower = 0)
        self.operation_timeseries["P_system_buy"] = self.operation_system["P_grid_buy"]
        self.operation_timeseries["P_generation"] = self.operation_generation["P_gen"]
        self.operation_timeseries["P_excess"] = self.operation_system["P_excess"]
        self.operation_timeseries["P_storage_charge_generation"] = pd.Series(- self.operation_generation["P_gen"] + self.operation_system["P_excess"] + self.operation_system["P_grid_sell"] / self.system.efficiency).clip(upper = 0)
        self.operation_timeseries["P_storage_charge_grid"] = self.operation_system["P_grid_buy"] * self.system.efficiency
        self.operation_timeseries["P_storage_discharge"] = self.operation_storage["P_discharge"]

        self.operation_timeseries["E_buy"] = self.operation_comercialization["E_buy"]
        self.operation_timeseries["E_sell"] = self.operation_comercialization["E_sell"]
        self.operation_timeseries["B_buy"] = self.operation_comercialization["B_buy"]
        self.operation_timeseries["B_sell"] = self.operation_comercialization["B_sell"]
        self.operation_timeseries["B_benefit"] = self.operation_comercialization["B_benefit"]
        self.operation_timeseries["B_benefit_MW"] = self.operation_comercialization["B_benefit"] / system_power
        self.operation_timeseries["B_benefit_MWh_storage"] = self.operation_comercialization["B_benefit"] / system_capacity
        self.operation_timeseries["B_benefit_MWh_produced"] = self.operation_comercialization["B_benefit"] / energy_produced

        self.operation_timeseries = self.operation_timeseries.round(decimals = 4)

        for storage in self.operation_storage_list:
            storage_name = storage["name"].iloc[0]
            self.operation_timeseries[f"SOC_{storage_name}"] = self.operation_storage[f"SOC_{storage_name}"]
            self.operation_timeseries[f"charge_{storage_name}"] = self.operation_storage[f"charge_{storage_name}"]
            self.operation_timeseries[f"discharge_{storage_name}"] = self.operation_storage[f"discharge_{storage_name}"]
            self.operation_timeseries[f"rest_{storage_name}"] = self.operation_storage[f"rest_{storage_name}"]
            self.operation_timeseries[f"RSOC_{storage_name}"] = self.operation_storage[f"RSOC_{storage_name}"]

        agg_data_format = {
            "price":"mean",
            "E_buy":"sum",
            "E_sell":"sum",
            "B_buy":"sum",
            "B_sell":"sum",
            "B_benefit":"sum",
            "B_benefit_MW":"sum",
            "B_benefit_MWh_storage":"sum",
            "B_benefit_MWh_produced":"sum",
        }
        
        self.operation_timeseries_month = self.operation_timeseries[agg_data_format.keys()].resample("MS").agg(agg_data_format)
        self.operation_timeseries_year = self.operation_timeseries[agg_data_format.keys()].resample("YS").agg(agg_data_format)

    def plot_results(self):
        fig1, (ax_pmd, ax_power) = plt.subplots(2, 1, sharex = True)
        fig2, (ax_gen, ax_storage) = plt.subplots(2, 1, sharex = True, sharey = True)

        ax_pmd.set_xlabel("€/MWh")
        ax_pmd.set_title("Spanish Day-Ahead market price")

        ax_power.set_xlabel("MW")
        ax_power.set_title("Power output at POI")

        ax_gen.set_xlabel("MW")
        ax_gen.set_title("Generation modules power production")

        ax_storage.set_xlabel("MW")
        ax_storage.set_title("Storage modules power")

        self.operation_timeseries.plot(y = "price", kind = "line", ax = ax_pmd, color = "k")
        self.operation_timeseries.plot(y = ["P_system_sell_generation", "P_system_sell_storage"], kind = "area", ax = ax_power, color = ["green", "blue"], linewidth = 0.1)
        self.operation_timeseries.plot(y = "P_system_buy", kind = "area", ax = ax_power, color = "red", linewidth = 0.1) 

        self.operation_timeseries.plot(y =  "P_generation", kind = "area", ax = ax_gen, color = "yellow", linewidth = 0.1)
        self.operation_timeseries.plot(y = ["P_storage_charge_generation", "P_storage_charge_grid"], kind = "area", ax = ax_storage, color = ["orange","red"], linewidth = 0.1)
        self.operation_timeseries.plot(y = "P_storage_discharge", kind = "area", ax = ax_storage, color = "green", linewidth = 0.1)

        plt.show()

    def print_tables(self):
        print(self.operation_storage)

        print(self.operation_generation)

        print(self.operation_system)

        print(self.operation_comercialization)

        print(self.operation_timeseries)

        print(self.operation_timeseries_month)

        print(self.operation_timeseries_year)    

    def export_data(self, path):
        fmt = "%Y-%m-%dT%H:%M:%SZ"
        operation_timeseries = self.operation_timeseries.copy()
        operation_timeseries_month = self.operation_timeseries_month.copy()
        operation_timeseries_year = self.operation_timeseries_year.copy()

        operation_system = self.operation_system.copy()

        operation_timeseries.index = operation_timeseries.index.strftime(fmt)
        operation_timeseries_month.index = operation_timeseries_month.index.strftime(fmt)
        operation_timeseries_year.index = operation_timeseries_year.index.strftime(fmt)

        operation_system.index = operation_system.index.strftime(fmt)

        with pd.ExcelWriter(path) as writer:
            operation_timeseries.to_excel(writer, sheet_name = 'operation_timeseries')
            operation_timeseries_month.to_excel(writer, sheet_name = 'operation_timeseries_month')
            operation_timeseries_year.to_excel(writer, sheet_name = 'operation_timeseries_year')

            operation_system.to_excel(writer, sheet_name = 'test')