from .base import Market
from ..models.modules import Battery
from esios_request import esios_get_indicator
import pandas as pd
from datetime import datetime
import pyomo.environ as pyo
from typing import Literal
import random as rand

class DayAhead(Market):
    """   
    Class that represents the day ahead market.
    """
    def __init__(self):
        self.name = self.__class__.__name__
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
    
    def components(self, model: pyo.ConcreteModel):
        """
        Adds the components (Sets, Variables, Parameters, Constraints) required to include this market in the ``model``.
        """
        prices = self.datasets["p_pmd"]["value"].to_dict()
        energy = self.datasets["e_pmd"]["value"].to_dict()

        # Sets
            # NONE

        # Parameters
        model.add_component(
            f"p_{self.name}",
            pyo.Param(model.T, initialize = prices, within = pyo.Reals, mutable = False, default = 0)
        )

        model.add_component(
            f"e_{self.name}",
            pyo.Param(model.T, initialize = energy, within = pyo.Reals, mutable = False, default = 0)
        )       
        # Variables
        # model.add_component(
        #     f"bin_{self.name}",
        #     pyo.Var(model.T, domain = pyo.Binary)
        # )

        model.add_component(
            f"P_buy_{self.name}",
            pyo.Var(model.T, domain = pyo.NonNegativeReals)
        )

        model.add_component(
            f"P_sell_{self.name}",
            pyo.Var(model.T, domain = pyo.NonNegativeReals)
        )
        # Constraints
        # model.add_component(
        #     f"output_market_limit_{self.name}",
        #     pyo.Constraint(
        #         model.T,
        #         rule = lambda m, t: (
        #             getattr(model, f"P_sell_{self.name}")[t] +
        #             getattr(model, f"P_buy_{self.name}")[t]
        #             <= getattr(model, f"e_{self.name}")[t]
        #         )
        #     )
        # )

        model.add_component(
            f"sell_mode_limit_{self.name}",
            pyo.Constraint(
                model.T,
                rule = lambda m, t: (
                    getattr(model, f"P_sell_{self.name}")[t]
                    <= m.system_capacity_export# * getattr(model, f"bin_{self.name}")[t]
                )
            )
        )

        model.add_component(
            f"buy_mode_limit_{self.name}",
            pyo.Constraint(
                model.T,
                rule = lambda m, t: (
                    getattr(model, f"P_buy_{self.name}")[t]
                    <= m.system_capacity_import# * (1 - getattr(model, f"bin_{self.name}")[t])
                )
            )
        )

        # Expressions
        model.add_component(
            f"Market_output_{self.name}",
            pyo.Expression(
                model.T,
                rule = lambda m, t: (
                    getattr(model, f"P_sell_{self.name}")[t] -
                    getattr(model, f"P_buy_{self.name}")[t]
                )
            )
        )

        model.add_component(
            f"Power_allocated_{self.name}",
            pyo.Expression(
                model.T,
                rule = lambda m, t: (
                    getattr(model, f"P_sell_{self.name}")[t] +
                    getattr(model, f"P_buy_{self.name}")[t]
                )
            )
        )
        
        model.add_component(
            f"Revenues_{self.name}",
            pyo.Expression(
                expr = sum(
                    (getattr(model, f"P_sell_{self.name}")[t] - getattr(model, f"P_buy_{self.name}")[t]) *
                    getattr(model, f"p_{self.name}")[t] *
                    model.dt[t]
                    for t in model.T
                )
            )
        )

    def results(self, model: pyo.ConcreteModel):
        records = []

        for t in model.T:
            records.append(
                {
                    "time": t,
                    f"p_{self.name}": pyo.value(getattr(model, f"p_{self.name}")[t]),
                    f"e_{self.name}": pyo.value(getattr(model, f"e_{self.name}")[t]),
                    f"P_sell_{self.name}": pyo.value(getattr(model, f"P_sell_{self.name}")[t]),
                    f"P_buy_{self.name}": pyo.value(getattr(model, f"P_buy_{self.name}")[t]),

                }
            )

        df = (
            pd.DataFrame(records)
            .set_index("time")
            .sort_index()
        )

        return df
    
class IntraDay01(Market):
    """   
    Class that represents the intra day 1 market.
    """
    def __init__(self):
        self.name = self.__class__.__name__
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
    
    def components(self, model: pyo.ConcreteModel):
        """
        Adds the components (Sets, Variables, Parameters, Constraints) required to include this market in the ``model``.
        """
        prices = self.datasets["p_pmi1"]["value"].to_dict()
        energy = self.datasets["e_pmi1"]["value"].to_dict()

        # Sets
            # NONE

        # Parameters
        model.add_component(
            f"p_{self.name}",
            pyo.Param(model.T, initialize = prices, within = pyo.Reals, mutable = False, default = 0)
        )

        model.add_component(
            f"e_{self.name}",
            pyo.Param(model.T, initialize = energy, within = pyo.Reals, mutable = False, default = 0)
        )   
        # Variables
        # model.add_component(
        #     f"bin_{self.name}",
        #     pyo.Var(model.T, domain = pyo.Binary)
        # )

        model.add_component(
            f"P_buy_{self.name}",
            pyo.Var(model.T, domain = pyo.NonNegativeReals)
        )

        model.add_component(
            f"P_sell_{self.name}",
            pyo.Var(model.T, domain = pyo.NonNegativeReals)
        )
        # Constraints
        model.add_component(
            f"output_market_limit_{self.name}",
            pyo.Constraint(
                model.T,
                rule = lambda m, t: (
                    getattr(model, f"P_sell_{self.name}")[t] +
                    getattr(model, f"P_buy_{self.name}")[t]
                    <= getattr(model, f"e_{self.name}")[t]
                )
            )
        )

        model.add_component(
            f"sell_mode_limit_{self.name}",
            pyo.Constraint(
                model.T,
                rule = lambda m, t: (
                    getattr(model, f"P_sell_{self.name}")[t]
                    <= m.system_capacity_export# * getattr(model, f"bin_{self.name}")[t]
                )
            )
        )

        model.add_component(
            f"buy_mode_limit_{self.name}",
            pyo.Constraint(
                model.T,
                rule = lambda m, t: (
                    getattr(model, f"P_buy_{self.name}")[t]
                    <= m.system_capacity_import# * (1 - getattr(model, f"bin_{self.name}")[t])
                )
            )
        )

        # Expressions
        model.add_component(
            f"Market_output_{self.name}",
            pyo.Expression(
                model.T,
                rule = lambda m, t: (
                    getattr(model, f"P_sell_{self.name}")[t] -
                    getattr(model, f"P_buy_{self.name}")[t]
                )
            )
        )

        model.add_component(
            f"Power_allocated_{self.name}",
            pyo.Expression(
                model.T,
                rule = lambda m, t: (
                    getattr(model, f"P_sell_{self.name}")[t] +
                    getattr(model, f"P_buy_{self.name}")[t]
                )
            )
        )
        
        model.add_component(
            f"Revenues_{self.name}",
            pyo.Expression(
                expr = sum(
                    (getattr(model, f"P_sell_{self.name}")[t] - getattr(model, f"P_buy_{self.name}")[t]) *
                    getattr(model, f"p_{self.name}")[t] *
                    model.dt[t]
                    for t in model.T
                )
            )
        )

    def results(self, model: pyo.ConcreteModel):
        records = []

        for t in model.T:
            records.append(
                {
                    "time": t,
                    f"p_{self.name}": pyo.value(getattr(model, f"p_{self.name}")[t]),
                    f"e_{self.name}": pyo.value(getattr(model, f"e_{self.name}")[t]),
                    f"P_sell_{self.name}": pyo.value(getattr(model, f"P_sell_{self.name}")[t]),
                    f"P_buy_{self.name}": pyo.value(getattr(model, f"P_buy_{self.name}")[t]),

                }
            )

        df = (
            pd.DataFrame(records)
            .set_index("time")
            .sort_index()
        )

        return df
    
class IntraDay02(Market):
    """
    Class that represents the intra day 2 market.
    """
    def __init__(self):
        self.name = self.__class__.__name__
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
    
    def components(self, model: pyo.ConcreteModel):
        """
        Adds the components (Sets, Variables, Parameters, Constraints) required to include this market in the ``model``.
        """
        prices = self.datasets["p_pmi2"]["value"].to_dict()
        energy = self.datasets["e_pmi2"]["value"].to_dict()
        # Sets
            # NONE

        # Parameters
        model.add_component(
            f"p_{self.name}",
            pyo.Param(model.T, initialize = prices, within = pyo.Reals, mutable = False, default = 0)
        )

        model.add_component(
            f"e_{self.name}",
            pyo.Param(model.T, initialize = energy, within = pyo.Reals, mutable = False, default = 0)
        )   
        # Variables
        # model.add_component(
        #     f"bin_{self.name}",
        #     pyo.Var(model.T, domain = pyo.Binary)
        # )

        model.add_component(
            f"P_buy_{self.name}",
            pyo.Var(model.T, domain = pyo.NonNegativeReals)
        )

        model.add_component(
            f"P_sell_{self.name}",
            pyo.Var(model.T, domain = pyo.NonNegativeReals)
        )
        # Constraints
        model.add_component(
            f"output_market_limit_{self.name}",
            pyo.Constraint(
                model.T,
                rule = lambda m, t: (
                    getattr(model, f"P_sell_{self.name}")[t] +
                    getattr(model, f"P_buy_{self.name}")[t]
                    <= getattr(model, f"e_{self.name}")[t]
                )
            )
        )

        model.add_component(
            f"sell_mode_limit_{self.name}",
            pyo.Constraint(
                model.T,
                rule = lambda m, t: (
                    getattr(model, f"P_sell_{self.name}")[t]
                    <= m.system_capacity_export #* getattr(model, f"bin_{self.name}")[t]
                )
            )
        )

        model.add_component(
            f"buy_mode_limit_{self.name}",
            pyo.Constraint(
                model.T,
                rule = lambda m, t: (
                    getattr(model, f"P_buy_{self.name}")[t]
                    <= m.system_capacity_import #* (1 - getattr(model, f"bin_{self.name}")[t])
                )
            )
        )

        # Expressions
        model.add_component(
            f"Market_output_{self.name}",
            pyo.Expression(
                model.T,
                rule = lambda m, t: (
                    getattr(model, f"P_sell_{self.name}")[t] -
                    getattr(model, f"P_buy_{self.name}")[t]
                )
            )
        )

        model.add_component(
            f"Power_allocated_{self.name}",
            pyo.Expression(
                model.T,
                rule = lambda m, t: (
                    getattr(model, f"P_sell_{self.name}")[t] +
                    getattr(model, f"P_buy_{self.name}")[t]
                )
            )
        )
        
        model.add_component(
            f"Revenues_{self.name}",
            pyo.Expression(
                expr = sum(
                    (getattr(model, f"P_sell_{self.name}")[t] - getattr(model, f"P_buy_{self.name}")[t]) *
                    getattr(model, f"p_{self.name}")[t] *
                    model.dt[t]
                    for t in model.T
                )
            )
        )

    def results(self, model: pyo.ConcreteModel):
        records = []

        for t in model.T:
            records.append(
                {
                    "time": t,
                    f"p_{self.name}": pyo.value(getattr(model, f"p_{self.name}")[t]),
                    f"e_{self.name}": pyo.value(getattr(model, f"e_{self.name}")[t]),
                    f"P_sell_{self.name}": pyo.value(getattr(model, f"P_sell_{self.name}")[t]),
                    f"P_buy_{self.name}": pyo.value(getattr(model, f"P_buy_{self.name}")[t]),

                }
            )

        df = (
            pd.DataFrame(records)
            .set_index("time")
            .sort_index()
        )

        return df
    
class IntraDay03(Market):
    """
    Class that represents the intra day 2 market.
    """
    def __init__(self):
        self.name = self.__class__.__name__
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

    def components(self, model: pyo.ConcreteModel):
        """
        Adds the components (Sets, Variables, Parameters, Constraints) required to include this market in the ``model``.
        """
        prices = self.datasets["p_pmi3"]["value"].to_dict()
        energy = self.datasets["e_pmi3"]["value"].to_dict()

        # Sets
            # NONE

        # Parameters
        model.add_component(
            f"p_{self.name}",
            pyo.Param(model.T, initialize = prices, within = pyo.Reals, mutable = False, default = 0)
        )

        model.add_component(
            f"e_{self.name}",
            pyo.Param(model.T, initialize = energy, within = pyo.Reals, mutable = False, default = 0)
        )  
        # Variables
        # model.add_component(
        #     f"bin_{self.name}",
        #     pyo.Var(model.T, domain = pyo.Binary)
        # )

        model.add_component(
            f"P_buy_{self.name}",
            pyo.Var(model.T, domain = pyo.NonNegativeReals)
        )

        model.add_component(
            f"P_sell_{self.name}",
            pyo.Var(model.T, domain = pyo.NonNegativeReals)
        )
        # Constraints
        model.add_component(
            f"output_market_limit_{self.name}",
            pyo.Constraint(
                model.T,
                rule = lambda m, t: (
                    getattr(model, f"P_sell_{self.name}")[t] +
                    getattr(model, f"P_buy_{self.name}")[t]
                    <= getattr(model, f"e_{self.name}")[t]
                )
            )
        )

        model.add_component(
            f"sell_mode_limit_{self.name}",
            pyo.Constraint(
                model.T,
                rule = lambda m, t: (
                    getattr(model, f"P_sell_{self.name}")[t]
                    <= m.system_capacity_export #* getattr(model, f"bin_{self.name}")[t]
                )
            )
        )

        model.add_component(
            f"buy_mode_limit_{self.name}",
            pyo.Constraint(
                model.T,
                rule = lambda m, t: (
                    getattr(model, f"P_buy_{self.name}")[t]
                    <= m.system_capacity_import #* (1 - getattr(model, f"bin_{self.name}")[t])
                )
            )
        )

        # Expressions
        model.add_component(
            f"Market_output_{self.name}",
            pyo.Expression(
                model.T,
                rule = lambda m, t: (
                    getattr(model, f"P_sell_{self.name}")[t] -
                    getattr(model, f"P_buy_{self.name}")[t]
                )
            )
        )

        model.add_component(
            f"Power_allocated_{self.name}",
            pyo.Expression(
                model.T,
                rule = lambda m, t: (
                    getattr(model, f"P_sell_{self.name}")[t] +
                    getattr(model, f"P_buy_{self.name}")[t]
                )
            )
        )
        
        model.add_component(
            f"Revenues_{self.name}",
            pyo.Expression(
                expr = sum(
                    (getattr(model, f"P_sell_{self.name}")[t] - getattr(model, f"P_buy_{self.name}")[t]) *
                    getattr(model, f"p_{self.name}")[t] *
                    model.dt[t]
                    for t in model.T
                )
            )
        )

    def results(self, model: pyo.ConcreteModel):
        records = []

        for t in model.T:
            records.append(
                {
                    "time": t,
                    f"p_{self.name}": pyo.value(getattr(model, f"p_{self.name}")[t]),
                    f"e_{self.name}": pyo.value(getattr(model, f"e_{self.name}")[t]),
                    f"P_sell_{self.name}": pyo.value(getattr(model, f"P_sell_{self.name}")[t]),
                    f"P_buy_{self.name}": pyo.value(getattr(model, f"P_buy_{self.name}")[t]),

                }
            )

        df = (
            pd.DataFrame(records)
            .set_index("time")
            .sort_index()
        )

        return df
    
class AFRR(Market):
    """
    Class that represents the aFRR market.
    """
    def __init__(self, act:Literal["bin_prop", "bin_max", "rand"] | None = None):
        self.name = self.__class__.__name__
        self.datasets: dict[str, pd.DataFrame] = {}
        self.act = act

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
    
    def components(self, model: pyo.ConcreteModel):
        """
        Adds the components (Sets, Variables, Parameters, Constraints) required to include this market in the ``model``.
        """
        p_afrr_up = self.datasets["p_afrr_up"]["value"].to_dict()
        p_afrr_down = self.datasets["p_afrr_down"]["value"].to_dict()
        p_afrr_act_up = self.datasets["p_afrr_act_up"]["value"].to_dict()
        p_afrr_act_down = self.datasets["p_afrr_act_down"]["value"].to_dict()
        band_afrr_up = self.datasets["band_afrr_up"]["value"].to_dict()
        band_afrr_down = self.datasets["band_afrr_down"]["value"].to_dict()

        # TODO change e_afrr_act_up and e_afrr_act_down for the activated energy for the unit. Param self.act: Literal[str...]
        # TODO only one of the two params can be != 0 for each t.
        # TODO both params need to be a value between 0 and 1 being the % of the band that is gonna be activated.
        e_afrr_act_up, e_afrr_act_down = self._energy_activation_requirements()

        # Sets
            # NONE

        # Parameters
        model.add_component(
            f"p_up_{self.name}",
            pyo.Param(model.T, initialize = p_afrr_up, within = pyo.Reals, mutable = False, default = 0)
        )
        model.add_component(
            f"p_down_{self.name}",
            pyo.Param(model.T, initialize = p_afrr_down, within = pyo.Reals, mutable = False, default = 0)
        )
        model.add_component(
            f"p_act_up_{self.name}",
            pyo.Param(model.T, initialize = p_afrr_act_up, within = pyo.Reals, mutable = False, default = 0)
        )
        model.add_component(
            f"p_act_down_{self.name}",
            pyo.Param(model.T, initialize = p_afrr_act_down, within = pyo.Reals, mutable = False, default = 0)
        )
        model.add_component(
            f"band_up_{self.name}",
            pyo.Param(model.T, initialize = band_afrr_up, within = pyo.Reals, mutable = False, default = 0)
        )
        model.add_component(
            f"band_down_{self.name}",
            pyo.Param(model.T, initialize = band_afrr_down, within = pyo.Reals, mutable = False, default = 0)
        )
        model.add_component(
            f"e_act_up_{self.name}",
            pyo.Param(model.T, initialize = e_afrr_act_up, within = pyo.Reals, mutable = False, default = 0)
        )
        model.add_component(
            f"e_act_down_{self.name}",
            pyo.Param(model.T, initialize = e_afrr_act_down, within = pyo.Reals, mutable = False, default = 0)
        )
        # Variables
        model.add_component(
            f"Band_up_{self.name}",
            pyo.Var(model.T, domain = pyo.NonNegativeReals)
        )

        model.add_component(
            f"Band_down_{self.name}",
            pyo.Var(model.T, domain = pyo.NonNegativeReals)
        )

        model.add_component(
            f"P_up_{self.name}",
            pyo.Var(model.T, domain = pyo.NonNegativeReals)
        )

        model.add_component(
            f"P_down_{self.name}",
            pyo.Var(model.T, domain = pyo.NonNegativeReals)
        )
        # Constraints
        model.add_component(
            f"band_up_market_limit_{self.name}",
            pyo.Constraint(
                model.T,
                rule = lambda m, t: (
                    getattr(model, f"Band_up_{self.name}")[t]
                    <= getattr(model, f"band_up_{self.name}")[t]
                )
            )
        )

        model.add_component(
            f"band_down_market_limit_{self.name}",
            pyo.Constraint(
                model.T,
                rule = lambda m, t: (
                    getattr(model, f"Band_down_{self.name}")[t]
                    <= getattr(model, f"band_down_{self.name}")[t]
                )
            )
        )

        model.add_component(
            f"band_up_system_limit_{self.name}",
            pyo.Constraint(
                model.T,
                rule = lambda m, t: (
                    getattr(model, f"Band_up_{self.name}")[t]
                    <= m.system_capacity_export # Crear una expresion que calcule la banda disponible a subir
                )
            )
        )

        model.add_component(
            f"band_down_system_limit_{self.name}",
            pyo.Constraint(
                model.T,
                rule = lambda m, t: (
                    getattr(model, f"Band_down_{self.name}")[t]
                    <= m.system_capacity_import # Crear una expresion que calcule la banda disponible a bajar
                )
            )
        )

        model.add_component(
            f"act_up_requirement_{self.name}",
            pyo.Constraint(
                model.T,
                rule = lambda m, t: (
                    getattr(model, f"P_up_{self.name}")[t] # Var
                    == 
                    getattr(model, f"e_act_up_{self.name}")[t] * # Param from 0 to 1
                    getattr(model, f"Band_up_{self.name}")[t] # Var ofered act band
                )
            )
        )

        model.add_component(
            f"act_down_requirement_{self.name}",
            pyo.Constraint(
                model.T,
                rule = lambda m, t: (
                    getattr(model, f"P_down_{self.name}")[t]
                    == 
                    getattr(model, f"e_act_down_{self.name}")[t] *
                    getattr(model, f"Band_up_{self.name}")[t]
                )
            )
        )

        # Expressions
            # TODO decide if the activated energy (P_up and P_down) goes into the equation of allocated energy,
            # TODO or the allocated band (Band_up and Band_down).
        model.add_component(
            f"Market_output_{self.name}",
            pyo.Expression(
                model.T,
                rule = lambda m, t: (
                    getattr(model, f"P_up_{self.name}")[t] -
                    getattr(model, f"P_down_{self.name}")[t]
                )
            )
        )

        model.add_component(
            f"Power_allocated_{self.name}",
            pyo.Expression(
                model.T,
                rule = lambda m, t: (
                    getattr(model, f"P_up_{self.name}")[t] +
                    getattr(model, f"P_down_{self.name}")[t]
                )
            )
        )
        
        model.add_component(
            f"Revenues_{self.name}",
            pyo.Expression(
                expr = sum(
                    (getattr(model, f"Band_up_{self.name}")[t] * getattr(model, f"p_up_{self.name}")[t]) +
                    (getattr(model, f"Band_down_{self.name}")[t] * getattr(model, f"p_down_{self.name}")[t]) +
                    (
                        (getattr(model, f"P_up_{self.name}")[t] * getattr(model, f"p_act_up_{self.name}")[t]) -
                        (getattr(model, f"P_down_{self.name}")[t] * getattr(model, f"p_act_down_{self.name}")[t])
                    ) *
                    model.dt[t]
                    for t in model.T
                )
            )
        )

    def results(self, model: pyo.ConcreteModel):
        records = []

        for t in model.T:
            records.append(
                {
                    "time": t,
                    f"p_up_{self.name}": pyo.value(getattr(model, f"p_up_{self.name}")[t]),
                    f"p_down_{self.name}": pyo.value(getattr(model, f"p_down_{self.name}")[t]),
                    f"p_act_up_{self.name}": pyo.value(getattr(model, f"p_act_up_{self.name}")[t]),
                    f"p_act_down_{self.name}": pyo.value(getattr(model, f"p_act_down_{self.name}")[t]),
                    f"band_up_{self.name}": pyo.value(getattr(model, f"band_up_{self.name}")[t]),
                    f"band_down_{self.name}": pyo.value(getattr(model, f"band_down_{self.name}")[t]),
                    f"e_act_up_{self.name}": pyo.value(getattr(model, f"e_act_up_{self.name}")[t]),
                    f"e_act_down_{self.name}": pyo.value(getattr(model, f"e_act_down_{self.name}")[t]),
                    f"Band_up_{self.name}": pyo.value(getattr(model, f"Band_up_{self.name}")[t]),
                    f"Band_down_{self.name}": pyo.value(getattr(model, f"Band_down_{self.name}")[t]),
                    f"P_up_{self.name}": pyo.value(getattr(model, f"P_up_{self.name}")[t]),
                    f"P_down_{self.name}": pyo.value(getattr(model, f"P_down_{self.name}")[t]),
                }
            )

        df = (
            pd.DataFrame(records)
            .set_index("time")
            .sort_index()
        )

        return df

    def _energy_activation_requirements(self) -> tuple[dict, dict]:
        """
        Provides the aFRR energy activation requirements by giving a timeseries 
        of activation percentages both aFRR activation up and down.
        """
        # TODO
        self.act

        index = self.datasets["e_afrr_act_up"].index
        _perc_affr_act_up = pd.DataFrame(
            # data = self.datasets["e_afrr_act_up"]["value"] / self.datasets["band_afrr_up"]["value"],
            index = index
        )
        _perc_affr_act_down = pd.DataFrame(
            # data = self.datasets["e_afrr_act_down"]["value"] / self.datasets["band_afrr_down"]["value"],
            index = index
        )

        match self.act:
            case None:
                _perc_affr_act_up["value"] = 0
                _perc_affr_act_down["value"] = 0
            case "bin_prop":
                _perc_affr_act_up["value"] = self.datasets["e_afrr_act_up"]["value"] / self.datasets["band_afrr_up"]["value"]
                _perc_affr_act_down["value"] = self.datasets["e_afrr_act_down"]["value"] / self.datasets["band_afrr_down"]["value"]
            case "bin_max":
                pass
            case "rand":
                pass

        e_afrr_act_up = _perc_affr_act_up
        e_afrr_act_down = _perc_affr_act_down

        return e_afrr_act_up, e_afrr_act_down
    
class MFRR(Market):
    """
    Class that represents the mFRR market.
    """
    def __init__(self):
        self.name = self.__class__.__name__
        self.datasets: dict[str, pd.DataFrame] = {}

    def get_info(self, esios_token:str, start_date:str, end_date:str, use_cache = False):

        self.datasets[""] = esios_get_indicator(
            token = esios_token,
            id = "",
            params = {"start_date" : start_date, "end_date" : end_date},
            use_cache = use_cache
            )
        return self

    def components(self, model: pyo.ConcreteModel):
        """
        Adds the components (Sets, Variables, Parameters, Constraints) required to include this market in the ``model``.
        """
        prices = self.datasets["p_pmd"]["value"].to_dict()
        energy = self.datasets["e_pmd"]["value"].to_dict()

        # Sets
            # NONE

        # Parameters
        model.add_component(
            f"p_{self.name}",
            pyo.Param(model.T, initialize = prices, within = pyo.Reals, mutable = False, default = 0)
        )

        model.add_component(
            f"e_{self.name}",
            pyo.Param(model.T, initialize = energy, within = pyo.Reals, mutable = False, default = 0)
        )       
        # Variables
        model.add_component(
            f"bin_{self.name}",
            pyo.Var(model.T, domain = pyo.Binary)
        )

        model.add_component(
            f"P_buy_{self.name}",
            pyo.Var(model.T, domain = pyo.NonNegativeReals)
        )

        model.add_component(
            f"P_sell_{self.name}",
            pyo.Var(model.T, domain = pyo.NonNegativeReals)
        )
        # Constraints
        model.add_component(
            f"output_market_limit_{self.name}",
            pyo.Constraint(
                model.T,
                rule = lambda m, t: (
                    getattr(model, f"P_sell_{self.name}")[t] +
                    getattr(model, f"P_buy_{self.name}")[t]
                    <= getattr(model, f"e_{self.name}")[t]
                )
            )
        )

        model.add_component(
            f"sell_mode_limit_{self.name}",
            pyo.Constraint(
                model.T,
                rule = lambda m, t: (
                    getattr(model, f"P_sell_{self.name}")[t]
                    <= m.system_capacity_export * getattr(model, f"bin_{self.name}")[t]
                )
            )
        )

        model.add_component(
            f"buy_mode_limit_{self.name}",
            pyo.Constraint(
                model.T,
                rule = lambda m, t: (
                    getattr(model, f"P_buy_{self.name}")[t]
                    <= m.system_capacity_import * (1 - getattr(model, f"bin_{self.name}")[t])
                )
            )
        )

        # Expressions
        model.add_component(
            f"Power_allocated_{self.name}",
            pyo.Expression(
                model.T,
                rule = lambda m, t: (
                    getattr(model, f"P_sell_{self.name}")[t] +
                    getattr(model, f"P_buy_{self.name}")[t]
                )
            )
        )
        
        model.add_component(
            f"Revenues_{self.name}",
            pyo.Expression(
                expr = sum(
                    (getattr(model, f"P_sell_{self.name}")[t] - getattr(model, f"P_buy_{self.name}")[t]) *
                    getattr(model, f"p_{self.name}")[t] *
                    model.dt[t]
                    for t in model.T
                )
            )
        )

    def results(self, model: pyo.ConcreteModel):
        records = []

        for t in model.T:
            records.append(
                {
                    "time": t,
                    f"p_{self.name}": pyo.value(getattr(model, f"p_{self.name}")[t]),
                    f"P_sell_{self.name}": pyo.value(getattr(model, f"P_sell_{self.name}")[t]),
                    f"P_buy_{self.name}": pyo.value(getattr(model, f"P_buy_{self.name}")[t]),

                }
            )

        df = (
            pd.DataFrame(records)
            .set_index("time")
            .sort_index()
        )

        return df

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