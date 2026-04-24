# Use case where a set of system configurations are studied to determine the optimal one.
# The data is exported to the specified address in Excel format, by default in downloads.
import pandas as pd
from . import recipe
from ..models.modules import System, Battery, Photovoltaic
from ..markets.markets import DayAhead, AFRR
from ..optimizers.perfect_optimizer import PerfectOptimizer

class Reports:
    @staticmethod
    def trese_like_study(path:str, ESIOS_API_KEY:str, start_year = 2028, end_year = 2058):
        """
        Hybrid PV with BESS power plant. Scope of 30 years. Needs price furves for DayAhead and aFRR markets.
        """
        start_date = "2025/01/01T00:00:00Z"
        end_date = "2025/12/31T23:59:00Z"
        filename = "treseLike_results_5MW_2h5MWgridch"

        req_year = 2025
        base_offset = start_year - req_year - 1
        production_one_year_dafne = pd.read_excel(io = "C:/Users/AndrésRivera/Downloads/20230630_QA_PVSYST_EPV-0016.xlsx", header = 12, index_col = 0, usecols = "A:E")
        production_one_year_dafne.index = production_one_year_dafne.index.tz_localize(None).tz_localize("Etc/GMT+1")
        production_one_year_dafne.rename(columns = {"Unnamed: 4": "power"}, inplace = True)
        production_one_year_dafne = production_one_year_dafne[["power"]]

        da2026_2055 = pd.read_csv(filepath_or_buffer = "C:/Users/AndrésRivera/Downloads/da_prices_2026_2055.csv", sep = ",", index_col = 0)
        band_afrr_up_2026_2055 = pd.read_csv(filepath_or_buffer = "C:/Users/AndrésRivera/Downloads/res_afrr_up_prices_2026_2055.csv", sep = ",", index_col = 0)
        band_afrr_down_2026_2055 = pd.read_csv(filepath_or_buffer = "C:/Users/AndrésRivera/Downloads/res_afrr_down_prices_2026_2055.csv", sep = ",", index_col = 0)

        da2026_2055.index = pd.to_datetime(da2026_2055.index)
        band_afrr_up_2026_2055.index = pd.to_datetime(band_afrr_up_2026_2055.index)
        band_afrr_down_2026_2055.index = pd.to_datetime(band_afrr_down_2026_2055.index)

        da2026_2055 = da2026_2055.resample("15min").ffill()
        band_afrr_up_2026_2055 = band_afrr_up_2026_2055.resample("15min").ffill() / 4
        band_afrr_down_2026_2055 = band_afrr_down_2026_2055.resample("15min").ffill() / 4

        years = range(start_year, end_year)
        output:pd.DataFrame = pd.DataFrame(index = years)
        da = DayAhead().get_info(esios_token = ESIOS_API_KEY, start_date = start_date, end_date = end_date, use_cache =  True)
        da.datasets["e_pmd"] = da.datasets["e_pmd"].set_index(da.datasets["e_pmd"].index + pd.DateOffset(years = base_offset))

        afrr = AFRR(act = "bin_prop").get_info(esios_token = ESIOS_API_KEY, start_date = start_date, end_date = end_date, use_cache =  True)
        afrr.datasets["p_afrr_act_up"] = afrr.datasets["p_afrr_act_up"].set_index(afrr.datasets["p_afrr_act_up"].index + pd.DateOffset(years = base_offset))
        afrr.datasets["p_afrr_act_down"] = afrr.datasets["p_afrr_act_down"].set_index(afrr.datasets["p_afrr_act_down"].index + pd.DateOffset(years = base_offset))
        afrr.datasets["band_afrr_up"] = afrr.datasets["band_afrr_up"].set_index(afrr.datasets["band_afrr_up"].index + pd.DateOffset(years = base_offset))
        afrr.datasets["band_afrr_down"] = afrr.datasets["band_afrr_down"].set_index(afrr.datasets["band_afrr_down"].index + pd.DateOffset(years = base_offset))
        afrr.datasets["e_afrr_act_up"] = afrr.datasets["e_afrr_act_up"].set_index(afrr.datasets["e_afrr_act_up"].index + pd.DateOffset(years = base_offset))
        afrr.datasets["e_afrr_act_down"] = afrr.datasets["e_afrr_act_down"].set_index(afrr.datasets["e_afrr_act_down"].index + pd.DateOffset(years = base_offset))

        # photovoltaic = Photovoltaic(name = "epv_dafne_test").set_production(production_one_year = production_one_year_dafne, start_date = start_date, end_date = end_date)
        # photovoltaic.production = photovoltaic.production.set_index(photovoltaic.production.index + pd.DateOffset(years = base_offset))

        print("datasets obtained, starting simulation")

        for year in years:
            yyyy = year
            offset = 1

            if year> 2055:
                yyyy = 2055
                offset = 0

            pv_offset = yyyy - req_year


            battery = Battery(
                capacity = 10,
                rte = 0.906531,
                c_rate = 0.5,
                max_cycles_day = 2.5,
                max_cycles_day_yearly_avg = 1.5,
                name = "bess_dafne",
            )
            photovoltaic = Photovoltaic(name = "epv_dafne_test").set_production(production_one_year = production_one_year_dafne, start_date = start_date, end_date = end_date)
            photovoltaic.production = photovoltaic.production.set_index(photovoltaic.production.index + pd.DateOffset(years = pv_offset))
            print(photovoltaic.production)
            system = System(capacity_buy = 5, capacity_sell = 5, efficiency = 0.98)
            system.add_module(battery)
            system.add_module(photovoltaic)

            da.datasets["p_pmd"] = da2026_2055[da2026_2055.index.year == yyyy]
            da.datasets["e_pmd"] = da.datasets["e_pmd"].set_index(da.datasets["e_pmd"].index + pd.DateOffset(years = offset))

            afrr.datasets["p_afrr_up"] = band_afrr_up_2026_2055[band_afrr_up_2026_2055.index.year == yyyy]
            afrr.datasets["p_afrr_down"] = band_afrr_down_2026_2055[band_afrr_down_2026_2055.index.year == yyyy]
            afrr.datasets["p_afrr_act_up"] = afrr.datasets["p_afrr_act_up"].set_index(afrr.datasets["p_afrr_act_up"].index + pd.DateOffset(years = offset))
            afrr.datasets["p_afrr_act_down"] = afrr.datasets["p_afrr_act_down"].set_index(afrr.datasets["p_afrr_act_down"].index + pd.DateOffset(years = offset))
            afrr.datasets["band_afrr_up"] = afrr.datasets["band_afrr_up"].set_index(afrr.datasets["band_afrr_up"].index + pd.DateOffset(years = offset))
            afrr.datasets["band_afrr_down"] = afrr.datasets["band_afrr_down"].set_index(afrr.datasets["band_afrr_down"].index + pd.DateOffset(years = offset))
            afrr.datasets["e_afrr_act_up"] = afrr.datasets["e_afrr_act_up"].set_index(afrr.datasets["e_afrr_act_up"].index + pd.DateOffset(years = offset))
            afrr.datasets["e_afrr_act_down"] = afrr.datasets["e_afrr_act_down"].set_index(afrr.datasets["e_afrr_act_down"].index + pd.DateOffset(years = offset))

            markets = [
                da,
                afrr
                ]

            # print(da.datasets)
            # print(afrr.datasets)
            # print(photovoltaic.production)

            # print(system)

            optimizer = PerfectOptimizer(system = system, markets = markets, precision = 2).solve()
            # optimizer.results.plot_operation()
            results = optimizer.results.operation_timeseries.copy()
            # results["DA_BESS_Revenue"] = results[f"p_DayAhead"] * 0
            # results["DA_PV_Revenue"] = results[f"p_DayAhead"] * 0
            # results["BESS_Charge_Cost"] = results[f"p_DayAhead"] * 0
            results_year = optimizer.results.operation_timeseries_year.copy()

            output.loc[year, "DA_BESS_Revenue"] = 0 # results["DA_BESS_Revenue"].resample("YS").sum()
            output.loc[year, "DA_PV_Revenue"] = 0 # results["DA_PV_Revenue"].resample("YS").sum()
            output.loc[year, "aFRR_Reserve_Up_Revenue"] = results_year["B_band_up_AFRR"].iloc[0]
            output.loc[year, "aFRR_Reserve_Down_Revenue"] = results_year["B_band_down_AFRR"].iloc[0]
            output.loc[year, "aFRR_Energy_Up_Revenue"] = results_year["B_act_up_AFRR"].iloc[0]
            output.loc[year, "aFRR_Energy_Down_Revenue"] = results_year["B_act_down_AFRR"].iloc[0]
            output.loc[year, "BESS_Charge_Cost"] = 0 # results["BESS_Charge_Cost"].resample("YS").sum()
            output.loc[year, "BESS_Consumed_Energy_Taxes_Cost"] = 0
            output.loc[year, "Total_Revenue"] = results_year["B_benefit_DayAhead"].iloc[0] + results_year["B_benefit_AFRR"].iloc[0]
            output.loc[year, "BESS_sell"] = results_year["E_system_sell_storage"].iloc[0]
            output.loc[year, "BESS_buy"] = results_year["E_storage_charge_grid"].iloc[0]
            output.loc[year, "PV_DA"] = 0
            output.loc[year, "PV_to_BESS"] = results_year["E_storage_charge_generation"].iloc[0]
            output.loc[year, "aFRR_P_Up"] = results_year["P_up_AFRR"].iloc[0]
            output.loc[year, "aFRR_P_Down"] = results_year["P_down_AFRR"].iloc[0]
            output.loc[year, "aFRR_E_Up"] = results_year["E_up_AFRR"].iloc[0]
            output.loc[year, "aFRR_E_Down"] = results_year["E_down_AFRR"].iloc[0]
            output.loc[year, "SoH_end"] = 1
            print(f"Year {year} processed.")

        output.to_excel(excel_writer = path)