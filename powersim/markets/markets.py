import pandas as pd
from datetime import datetime
from typing import Literal
import numpy as np
from esios_request import esios_get_indicator
from abc import ABC, abstractmethod
import copy

class Market(ABC):
    def __init__(self, datasets: dict[str, object] = None):
        self.datasets = datasets or {}
        
    @abstractmethod
    def get_info(self, esios_token:str, start_date:str, end_date:str):
        pass

    @classmethod
    def from_market(cls, other):
        new = cls.__new__(cls)                         # sin ejecutar __init__
        new.__dict__.update(copy.deepcopy(other.__dict__))   # name, datasets, etc.
        return new

class DayAhead(Market):
    """   
    Class that represents the day ahead market.
    """
    def __init__(self):
        self.parent_name = self.__class__.__name__
        self.datasets: dict[str, pd.DataFrame] = {}

    def get_info(self, esios_token:str, start_date:str, end_date:str, use_cache = False):
        """
        Gets the data for the market between ``start_date`` and ``end_date``.

        :param esios_token: Your personal token to get data from ESIOS.
        :type esios_token: str
        :param start_date: Initial date to get the data in format AAAA/MM/DDThh:mm:ssZ.
        :type start_date: str
        :param end_date: Final date to get the data in format AAAA/MM/DDThh:mm:ssZ
        :type end_date: str
        """

        self.datasets["p_pmd"] = esios_get_indicator(
            token = esios_token,
            id = "p_pmd",
            params = {"start_date" : start_date, "end_date" : end_date, "geo_ids[]": 3},
            use_cache = use_cache,
            )
        
        self.datasets["e_pmd"] = esios_get_indicator(
            token = esios_token,
            id = "e_pmd",
            params = {"start_date" : start_date, "end_date" : end_date},
            )
        
        return self
    
class IntraDay01(Market):
    """   
    Class that represents the intra day 1 market.
    """
    def __init__(self):
        self.parent_name = self.__class__.__name__
        self.datasets: dict[str, pd.DataFrame] = {}

    def get_info(self, esios_token:str, start_date:str, end_date:str, use_cache = False):

        self.datasets["p_pmi1"] = esios_get_indicator(
            token = esios_token,
            id = "p_pmi1",
            params = {"start_date" : start_date, "end_date" : end_date},
            use_cache = use_cache,
            )
        
        self.datasets["e_pmi1"] = esios_get_indicator(
            token = esios_token,
            id = "e_pmi1",
            params = {"start_date" : start_date, "end_date" : end_date},
            use_cache = use_cache,
            )
        
        return self
    
class IntraDay02(Market):
    """
    Class that represents the intra day 2 market.
    """
    def __init__(self):
        self.parent_name = self.__class__.__name__
        self.datasets: dict[str, pd.DataFrame] = {}

    def get_info(self, esios_token:str, start_date:str, end_date:str, use_cache = False):

        self.datasets["p_pmi2"] = esios_get_indicator(
            token = esios_token,
            id = "p_pmi2",
            params = {"start_date" : start_date, "end_date" : end_date},
            use_cache = use_cache
            )
        
        self.datasets["e_pmi2"] = esios_get_indicator(
            token = esios_token,
            id = "e_pmi2",
            params = {"start_date" : start_date, "end_date" : end_date},
            use_cache = use_cache,
            )
        
        return self
    
class IntraDay03(Market):
    """
    Class that represents the intra day 2 market.
    """
    def __init__(self):
        self.parent_name = self.__class__.__name__
        self.datasets: dict[str, pd.DataFrame] = {}

    def get_info(self, esios_token:str, start_date:str, end_date:str, use_cache = False):

        self.datasets["p_pmi3"] = esios_get_indicator(
            token = esios_token,
            id = "p_pmi3",
            params = {"start_date" : start_date, "end_date" : end_date},
            use_cache = use_cache
            )
        
        self.datasets["e_pmi3"] = esios_get_indicator(
            token = esios_token,
            id = "e_pmi3",
            params = {"start_date" : start_date, "end_date" : end_date},
            use_cache = use_cache,
            )
        
        return self


    
class AFRR(Market):
    """
    Class that represents the aFRR market.
    """
    def __init__(
            self,
            max_up: float | None = None,
            max_down: float | None = None,
            act:Literal["bin_prop", "bin_max", "rand"] | None = None
            ):

        self.parent_name = self.__class__.__name__
        self.datasets: dict[str, pd.DataFrame] = {}
        self._act = act
        self._max_up = max_up
        self._max_down = max_down

    def get_info(self, esios_token:str, start_date:str, end_date:str, use_cache = False):
        fmt = "%Y/%m/%dT%H:%M:%SZ"
        check_start_date = datetime.strptime(start_date, fmt)
        check_end_date = datetime.strptime(end_date, fmt)
        regulatory_change_date = datetime.strptime("2024/11/19T23:00:00Z", fmt)
        if check_start_date < regulatory_change_date and check_end_date > regulatory_change_date:

            p_afrr_up_down_before = esios_get_indicator(
                token = esios_token,
                id = "p_afrr_down",
                params = {"start_date" : start_date, "end_date" : "2024/11/19T23:00:00Z"},
                use_cache = use_cache
                )
            
            p_afrr_up_after = esios_get_indicator(
                token = esios_token,
                id = "p_afrr_up",
                params = {"start_date" : "2024/11/19T00:00:00Z", "end_date" : end_date},
            use_cache = use_cache
                )
            
            p_afrr_down_after = esios_get_indicator(
                token = esios_token,
                id = "p_afrr_down",
                params = {"start_date" : "2024/11/19T00:00:00Z", "end_date" : end_date},
            use_cache = use_cache
                )
            
            self.datasets["p_afrr_up"] = pd.concat([p_afrr_up_down_before, p_afrr_up_after])
            self.datasets["p_afrr_up"] = self.datasets["p_afrr_up"][~self.datasets["p_afrr_up"].index.duplicated(keep="first")]
            self.datasets["p_afrr_down"] = pd.concat([p_afrr_up_down_before, p_afrr_down_after])
            self.datasets["p_afrr_down"] = self.datasets["p_afrr_down"][~self.datasets["p_afrr_down"].index.duplicated(keep="first")]

        else:
            self.datasets["p_afrr_up"] = esios_get_indicator(
                token = esios_token,
                id = "p_afrr_up",
                params = {"start_date" : start_date, "end_date" : end_date},
            use_cache = use_cache
                )
            self.datasets["p_afrr_down"] = esios_get_indicator(
                token = esios_token,
                id = "p_afrr_down",
                params = {"start_date" : start_date, "end_date" : end_date},
            use_cache = use_cache
                )

        self.datasets["p_afrr_act_up"] = esios_get_indicator(
            token = esios_token,
            id = "p_afrr_act_up",
            params = {"start_date" : start_date, "end_date" : end_date},
            use_cache = use_cache
            )
        self.datasets["p_afrr_act_down"] = esios_get_indicator(
            token = esios_token,
            id = "p_afrr_act_down",
            params = {"start_date" : start_date, "end_date" : end_date},
            use_cache = use_cache
            )
        self.datasets["band_afrr_up"] = esios_get_indicator(
            token = esios_token,
            id = "band_afrr_up",
            params = {"start_date" : start_date, "end_date" : end_date},
            use_cache = use_cache
            )
        self.datasets["band_afrr_down"] = esios_get_indicator(
            token = esios_token,
            id = "band_afrr_down",
            params = {"start_date" : start_date, "end_date" : end_date},
            use_cache = use_cache
            )
        self.datasets["e_afrr_act_up"] = esios_get_indicator(
            token = esios_token,
            id = "e_afrr_act_up",
            params = {"start_date" : start_date, "end_date" : end_date},
            use_cache = use_cache,
            )
        self.datasets["e_afrr_act_down"] = esios_get_indicator(
            token = esios_token,
            id = "e_afrr_act_down",
            params = {"start_date" : start_date, "end_date" : end_date},
            use_cache = use_cache,
            )
        return self

    def _energy_activation_requirements(self) -> tuple[dict, dict]:
        """
        Provides the aFRR energy activation requirements by giving a timeseries 
        of activation percentages both aFRR activation up and down.
        """
        # TODO
        self._act

        index = self.datasets["e_afrr_act_up"].index
        _perc_affr_act_up = pd.DataFrame(
            index = index
        )
        _perc_affr_act_down = pd.DataFrame(
            index = index
        )

        df_statistics = pd.DataFrame(
            index = index
        )

        match self._act:
            case None:
                _perc_affr_act_up["value"] = 0
                _perc_affr_act_down["value"] = 0

            case "bin_prop":
                df_statistics["prob_up"] = 4 * self.datasets["e_afrr_act_up"]["value"] / self.datasets["band_afrr_up"]["value"]
                df_statistics["prob_down"] = 4 * self.datasets["e_afrr_act_down"]["value"] / self.datasets["band_afrr_down"]["value"]

                coin = np.random.rand(len(df_statistics)) < 0.5
                rand_up = np.random.rand(len(df_statistics))
                rand_down = np.random.rand(len(df_statistics))

                df_temp_up = rand_up < df_statistics["prob_up"]
                df_temp_down = rand_down < df_statistics["prob_down"]
                tie = df_temp_up & df_temp_down

                up_wins_tie = (df_statistics["prob_up"] > df_statistics["prob_down"]) | ((df_statistics["prob_up"] == df_statistics["prob_down"]) & coin)
                down_wins_tie = (df_statistics["prob_down"] > df_statistics["prob_up"]) | ((df_statistics["prob_up"] == df_statistics["prob_down"]) & ~coin)

                df_statistics["act_up"] = (df_temp_up & ~df_temp_down) | (tie & up_wins_tie)
                df_statistics["act_down"] = (df_temp_down & ~df_temp_up) | (tie & down_wins_tie)

                _perc_affr_act_up["value"] = df_statistics["act_up"] * df_statistics["prob_up"]
                _perc_affr_act_down["value"] = df_statistics["act_down"] * df_statistics["prob_down"]

            case "bin_max":
                df_statistics["prob_up"] = 4 * self.datasets["e_afrr_act_up"]["value"] / self.datasets["band_afrr_up"]["value"]
                df_statistics["prob_down"] = 4 * self.datasets["e_afrr_act_down"]["value"] / self.datasets["band_afrr_down"]["value"]

                coin = np.random.rand(len(df_statistics)) < 0.5
                rand_up = np.random.rand(len(df_statistics))
                rand_down = np.random.rand(len(df_statistics))

                df_temp_up = rand_up < df_statistics["prob_up"]
                df_temp_down = rand_down < df_statistics["prob_down"]
                tie = df_temp_up & df_temp_down

                up_wins_tie = (df_statistics["prob_up"] > df_statistics["prob_down"]) | ((df_statistics["prob_up"] == df_statistics["prob_down"]) & coin)
                down_wins_tie = (df_statistics["prob_down"] > df_statistics["prob_up"]) | ((df_statistics["prob_up"] == df_statistics["prob_down"]) & ~coin)

                df_statistics["act_up"] = (df_temp_up & ~df_temp_down) | (tie & up_wins_tie)
                df_statistics["act_down"] = (df_temp_down & ~df_temp_up) | (tie & down_wins_tie)

                _perc_affr_act_up["value"] = df_statistics["act_up"] * 1
                _perc_affr_act_down["value"] = df_statistics["act_down"] * 1

            case "rand":
                coin = np.random.rand(len(df_statistics)) < 0.5
                rand_up = np.random.rand(len(df_statistics))
                rand_down = np.random.rand(len(df_statistics))

                tie = rand_up & rand_down

                up_wins_tie = (rand_up > rand_down) | ((rand_up == rand_down) & coin)
                down_wins_tie = (rand_down > rand_up) | ((rand_up == rand_down) & ~coin)

                # Resultado final (mutuamente excluyente)
                df_statistics["act_up"] = (df_temp_up & ~df_temp_down) | (tie & up_wins_tie)
                df_statistics["act_down"] = (df_temp_down & ~df_temp_up) | (tie & down_wins_tie)

                _perc_affr_act_up["value"] = df_statistics["act_up"] * df_statistics["prob_up"]
                _perc_affr_act_down["value"] = df_statistics["act_down"] * df_statistics["prob_down"]

        e_afrr_act_up = _perc_affr_act_up.fillna(0)
        e_afrr_act_down = _perc_affr_act_down.fillna(0)

        return e_afrr_act_up, e_afrr_act_down
    
class MFRR(Market):
    """
    Class that represents the mFRR market.
    """
    def __init__(self):
        self.parent_name = self.__class__.__name__
        self.datasets: dict[str, pd.DataFrame] = {}

    def get_info(self, esios_token:str, start_date:str, end_date:str, use_cache = False):

        self.datasets[""] = esios_get_indicator(
            token = esios_token,
            id = "",
            params = {"start_date" : start_date, "end_date" : end_date},
            use_cache = use_cache
            )
        return self

# class RRTT(Market):
    # """
    # """
#     def get_info(self, esios_token:str, start_date:str, end_date:str):

#         self.datasets[""] = esios_get_indicator(
#             token = esios_token,
#             id = "",
#             params = {"start_date" : start_date, "end_date" : end_date},
#             use_cache = use_cache
#             )
#         return self