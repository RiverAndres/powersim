import pandas as pd
import pyomo.environ as pyo
from ...markets.markets import DayAhead, IntraDay01, IntraDay02, IntraDay03, AFRR, MFRR


class Milp_DayAhead(DayAhead):
    """
    Class that represents the day ahead market for the PerfectOptimizer.
    """

    def components(self, model: pyo.ConcreteModel):
        """
        Adds the components (Sets, Variables, Parameters, Constraints) required to include this market in the ``model``.
        """
        self.name = self.__class__.__name__
        prices = self.datasets["p_pmd"]["value"].to_dict()
        energy = self.datasets["e_pmd"]["value"].to_dict()

        # Sets
        # NONE

        # Parameters
        model.add_component(
            f"p_{self.name}",
            pyo.Param(model.T, initialize=prices, within=pyo.Reals, mutable=False, default=0),
        )

        model.add_component(
            f"e_{self.name}",
            pyo.Param(model.T, initialize=energy, within=pyo.Reals, mutable=False, default=0),
        )

        # Variables
        model.add_component(f"P_buy_{self.name}", pyo.Var(model.T, domain=pyo.NonNegativeReals))

        model.add_component(f"P_sell_{self.name}", pyo.Var(model.T, domain=pyo.NonNegativeReals))

        model.add_component(
            f"sell_mode_limit_{self.name}",
            pyo.Constraint(
                model.T,
                rule=lambda m, t: (
                    getattr(model, f"P_sell_{self.name}")[t] <= m.system_capacity_export
                ),
            ),
        )

        model.add_component(
            f"buy_mode_limit_{self.name}",
            pyo.Constraint(
                model.T,
                rule=lambda m, t: (
                    getattr(model, f"P_buy_{self.name}")[t] <= m.system_capacity_import
                ),
            ),
        )

        # Expressions
        model.add_component(
            f"Market_output_{self.name}",
            pyo.Expression(
                model.T,
                rule=lambda m, t: (
                    getattr(model, f"P_sell_{self.name}")[t]
                    - getattr(model, f"P_buy_{self.name}")[t]
                ),
            ),
        )

        model.add_component(
            f"Power_pre_allocated_{self.name}",
            pyo.Expression(
                model.T,
                rule=lambda m, t: (
                    getattr(model, f"P_sell_{self.name}")[t]
                    - getattr(model, f"P_buy_{self.name}")[t]
                ),
            ),
        )

        model.add_component(
            f"Revenues_{self.name}",
            pyo.Expression(
                expr=sum(
                    (
                        getattr(model, f"P_sell_{self.name}")[t]
                        - getattr(model, f"P_buy_{self.name}")[t]
                    )
                    * getattr(model, f"p_{self.name}")[t]
                    * model.dt[t]
                    for t in model.T
                )
            ),
        )

    def results(self, model: pyo.ConcreteModel):
        records = []

        for t in model.T:
            records.append(
                {
                    "time": t,
                    f"p_{self.parent_name}": pyo.value(getattr(model, f"p_{self.name}")[t]),
                    f"e_{self.parent_name}": pyo.value(getattr(model, f"e_{self.name}")[t]),
                    f"P_sell_{self.parent_name}": pyo.value(
                        getattr(model, f"P_sell_{self.name}")[t]
                    ),
                    f"P_buy_{self.parent_name}": pyo.value(getattr(model, f"P_buy_{self.name}")[t]),
                }
            )

        df = pd.DataFrame(records).set_index("time").sort_index()

        return df


class Milp_IntraDay01(IntraDay01):
    def components(self, model: pyo.ConcreteModel):
        """
        Adds the components (Sets, Variables, Parameters, Constraints) required to include this market in the ``model``.
        """
        self.name = self.__class__.__name__
        prices = self.datasets["p_pmi1"]["value"].to_dict()
        energy = self.datasets["e_pmi1"]["value"].to_dict()

        # Sets
        # NONE

        # Parameters
        model.add_component(
            f"p_{self.name}",
            pyo.Param(model.T, initialize=prices, within=pyo.Reals, mutable=False, default=0),
        )

        model.add_component(
            f"e_{self.name}",
            pyo.Param(model.T, initialize=energy, within=pyo.Reals, mutable=False, default=0),
        )

        model.add_component(f"P_buy_{self.name}", pyo.Var(model.T, domain=pyo.NonNegativeReals))

        model.add_component(f"P_sell_{self.name}", pyo.Var(model.T, domain=pyo.NonNegativeReals))
        # Constraints
        model.add_component(
            f"output_market_limit_{self.name}",
            pyo.Constraint(
                model.T,
                rule=lambda m, t: (
                    getattr(model, f"P_sell_{self.name}")[t]
                    + getattr(model, f"P_buy_{self.name}")[t]
                    <= getattr(model, f"e_{self.name}")[t]
                ),
            ),
        )

        model.add_component(
            f"sell_mode_limit_{self.name}",
            pyo.Constraint(
                model.T,
                rule=lambda m, t: (
                    getattr(model, f"P_sell_{self.name}")[t] <= m.system_capacity_export
                ),
            ),
        )

        model.add_component(
            f"buy_mode_limit_{self.name}",
            pyo.Constraint(
                model.T,
                rule=lambda m, t: (
                    getattr(model, f"P_buy_{self.name}")[t] <= m.system_capacity_import
                ),
            ),
        )

        # Expressions
        model.add_component(
            f"Market_output_{self.name}",
            pyo.Expression(
                model.T,
                rule=lambda m, t: (
                    getattr(model, f"P_sell_{self.name}")[t]
                    - getattr(model, f"P_buy_{self.name}")[t]
                ),
            ),
        )

        model.add_component(
            f"Power_pre_allocated_{self.name}",
            pyo.Expression(
                model.T,
                rule=lambda m, t: (
                    getattr(model, f"P_sell_{self.name}")[t]
                    - getattr(model, f"P_buy_{self.name}")[t]
                ),
            ),
        )

        model.add_component(
            f"Revenues_{self.name}",
            pyo.Expression(
                expr=sum(
                    (
                        getattr(model, f"P_sell_{self.name}")[t]
                        - getattr(model, f"P_buy_{self.name}")[t]
                    )
                    * getattr(model, f"p_{self.name}")[t]
                    * model.dt[t]
                    for t in model.T
                )
            ),
        )

    def results(self, model: pyo.ConcreteModel):
        records = []

        for t in model.T:
            records.append(
                {
                    "time": t,
                    f"p_{self.parent_name}": pyo.value(getattr(model, f"p_{self.name}")[t]),
                    f"e_{self.parent_name}": pyo.value(getattr(model, f"e_{self.name}")[t]),
                    f"P_sell_{self.parent_name}": pyo.value(
                        getattr(model, f"P_sell_{self.name}")[t]
                    ),
                    f"P_buy_{self.parent_name}": pyo.value(getattr(model, f"P_buy_{self.name}")[t]),
                }
            )

        df = pd.DataFrame(records).set_index("time").sort_index()

        return df


class Milp_IntraDay02(IntraDay02):
    def components(self, model: pyo.ConcreteModel):
        """
        Adds the components (Sets, Variables, Parameters, Constraints) required to include this market in the ``model``.
        """
        self.name = self.__class__.__name__
        prices = self.datasets["p_pmi2"]["value"].to_dict()
        energy = self.datasets["e_pmi2"]["value"].to_dict()

        # Sets
        # NONE

        # Parameters
        model.add_component(
            f"p_{self.name}",
            pyo.Param(model.T, initialize=prices, within=pyo.Reals, mutable=False, default=0),
        )

        model.add_component(
            f"e_{self.name}",
            pyo.Param(model.T, initialize=energy, within=pyo.Reals, mutable=False, default=0),
        )

        model.add_component(f"P_buy_{self.name}", pyo.Var(model.T, domain=pyo.NonNegativeReals))

        model.add_component(f"P_sell_{self.name}", pyo.Var(model.T, domain=pyo.NonNegativeReals))
        # Constraints
        model.add_component(
            f"output_market_limit_{self.name}",
            pyo.Constraint(
                model.T,
                rule=lambda m, t: (
                    getattr(model, f"P_sell_{self.name}")[t]
                    + getattr(model, f"P_buy_{self.name}")[t]
                    <= getattr(model, f"e_{self.name}")[t]
                ),
            ),
        )

        model.add_component(
            f"sell_mode_limit_{self.name}",
            pyo.Constraint(
                model.T,
                rule=lambda m, t: (
                    getattr(model, f"P_sell_{self.name}")[t] <= m.system_capacity_export
                ),
            ),
        )

        model.add_component(
            f"buy_mode_limit_{self.name}",
            pyo.Constraint(
                model.T,
                rule=lambda m, t: (
                    getattr(model, f"P_buy_{self.name}")[t] <= m.system_capacity_import
                ),
            ),
        )

        # Expressions
        model.add_component(
            f"Market_output_{self.name}",
            pyo.Expression(
                model.T,
                rule=lambda m, t: (
                    getattr(model, f"P_sell_{self.name}")[t]
                    - getattr(model, f"P_buy_{self.name}")[t]
                ),
            ),
        )

        model.add_component(
            f"Power_pre_allocated_{self.name}",
            pyo.Expression(
                model.T,
                rule=lambda m, t: (
                    getattr(model, f"P_sell_{self.name}")[t]
                    - getattr(model, f"P_buy_{self.name}")[t]
                ),
            ),
        )

        model.add_component(
            f"Revenues_{self.name}",
            pyo.Expression(
                expr=sum(
                    (
                        getattr(model, f"P_sell_{self.name}")[t]
                        - getattr(model, f"P_buy_{self.name}")[t]
                    )
                    * getattr(model, f"p_{self.name}")[t]
                    * model.dt[t]
                    for t in model.T
                )
            ),
        )

    def results(self, model: pyo.ConcreteModel):
        records = []

        for t in model.T:
            records.append(
                {
                    "time": t,
                    f"p_{self.parent_name}": pyo.value(getattr(model, f"p_{self.name}")[t]),
                    f"e_{self.parent_name}": pyo.value(getattr(model, f"e_{self.name}")[t]),
                    f"P_sell_{self.parent_name}": pyo.value(
                        getattr(model, f"P_sell_{self.name}")[t]
                    ),
                    f"P_buy_{self.parent_name}": pyo.value(getattr(model, f"P_buy_{self.name}")[t]),
                }
            )

        df = pd.DataFrame(records).set_index("time").sort_index()

        return df


class Milp_IntraDay03(IntraDay03):
    def components(self, model: pyo.ConcreteModel):
        """
        Adds the components (Sets, Variables, Parameters, Constraints) required to include this market in the ``model``.
        """
        self.name = self.__class__.__name__
        prices = self.datasets["p_pmi3"]["value"].to_dict()
        energy = self.datasets["e_pmi3"]["value"].to_dict()

        # Sets
        # NONE

        # Parameters
        model.add_component(
            f"p_{self.name}",
            pyo.Param(model.T, initialize=prices, within=pyo.Reals, mutable=False, default=0),
        )

        model.add_component(
            f"e_{self.name}",
            pyo.Param(model.T, initialize=energy, within=pyo.Reals, mutable=False, default=0),
        )

        model.add_component(f"P_buy_{self.name}", pyo.Var(model.T, domain=pyo.NonNegativeReals))

        model.add_component(f"P_sell_{self.name}", pyo.Var(model.T, domain=pyo.NonNegativeReals))
        # Constraints
        model.add_component(
            f"output_market_limit_{self.name}",
            pyo.Constraint(
                model.T,
                rule=lambda m, t: (
                    getattr(model, f"P_sell_{self.name}")[t]
                    + getattr(model, f"P_buy_{self.name}")[t]
                    <= getattr(model, f"e_{self.name}")[t]
                ),
            ),
        )

        model.add_component(
            f"sell_mode_limit_{self.name}",
            pyo.Constraint(
                model.T,
                rule=lambda m, t: (
                    getattr(model, f"P_sell_{self.name}")[t] <= m.system_capacity_export
                ),
            ),
        )

        model.add_component(
            f"buy_mode_limit_{self.name}",
            pyo.Constraint(
                model.T,
                rule=lambda m, t: (
                    getattr(model, f"P_buy_{self.name}")[t] <= m.system_capacity_import
                ),
            ),
        )

        # Expressions
        model.add_component(
            f"Market_output_{self.name}",
            pyo.Expression(
                model.T,
                rule=lambda m, t: (
                    getattr(model, f"P_sell_{self.name}")[t]
                    - getattr(model, f"P_buy_{self.name}")[t]
                ),
            ),
        )

        model.add_component(
            f"Power_pre_allocated_{self.name}",
            pyo.Expression(
                model.T,
                rule=lambda m, t: (
                    getattr(model, f"P_sell_{self.name}")[t]
                    - getattr(model, f"P_buy_{self.name}")[t]
                ),
            ),
        )

        model.add_component(
            f"Revenues_{self.name}",
            pyo.Expression(
                expr=sum(
                    (
                        getattr(model, f"P_sell_{self.name}")[t]
                        - getattr(model, f"P_buy_{self.name}")[t]
                    )
                    * getattr(model, f"p_{self.name}")[t]
                    * model.dt[t]
                    for t in model.T
                )
            ),
        )

    def results(self, model: pyo.ConcreteModel):
        records = []

        for t in model.T:
            records.append(
                {
                    "time": t,
                    f"p_{self.parent_name}": pyo.value(getattr(model, f"p_{self.name}")[t]),
                    f"e_{self.parent_name}": pyo.value(getattr(model, f"e_{self.name}")[t]),
                    f"P_sell_{self.parent_name}": pyo.value(
                        getattr(model, f"P_sell_{self.name}")[t]
                    ),
                    f"P_buy_{self.parent_name}": pyo.value(getattr(model, f"P_buy_{self.name}")[t]),
                }
            )

        df = pd.DataFrame(records).set_index("time").sort_index()

        return df


class Milp_AFRR(AFRR):
    def components(self, model: pyo.ConcreteModel):
        """
        Adds the components (Sets, Variables, Parameters, Constraints) required to include this market in the ``model``.
        """
        self.name = self.__class__.__name__
        p_afrr_up = self.datasets["p_afrr_up"]["value"].to_dict()
        p_afrr_down = self.datasets["p_afrr_down"]["value"].to_dict()
        p_afrr_act_up = self.datasets["p_afrr_act_up"]["value"].to_dict()
        p_afrr_act_down = self.datasets["p_afrr_act_down"]["value"].to_dict()
        band_afrr_up = self.datasets["band_afrr_up"]["value"].to_dict()
        band_afrr_down = self.datasets["band_afrr_down"]["value"].to_dict()

        e_afrr_act_up, e_afrr_act_down = self._energy_activation_requirements()
        max_afrr_up = model.system_capacity_export
        max_afrr_down = model.system_capacity_import

        if self._max_up:
            max_afrr_up = min(self._max_up, model.system_capacity_export)

        if self._max_down:
            max_afrr_down = min(self._max_down, model.system_capacity_import)

        # Sets
        # NONE

        # Parameters
        model.add_component(
            f"p_up_{self.name}",
            pyo.Param(model.T, initialize=p_afrr_up, within=pyo.Reals, mutable=False, default=0),
        )
        model.add_component(
            f"p_down_{self.name}",
            pyo.Param(model.T, initialize=p_afrr_down, within=pyo.Reals, mutable=False, default=0),
        )
        model.add_component(
            f"p_act_up_{self.name}",
            pyo.Param(
                model.T, initialize=p_afrr_act_up, within=pyo.Reals, mutable=False, default=0
            ),
        )
        model.add_component(
            f"p_act_down_{self.name}",
            pyo.Param(
                model.T, initialize=p_afrr_act_down, within=pyo.Reals, mutable=False, default=0
            ),
        )
        model.add_component(
            f"band_up_{self.name}",
            pyo.Param(model.T, initialize=band_afrr_up, within=pyo.Reals, mutable=False, default=0),
        )
        model.add_component(
            f"band_down_{self.name}",
            pyo.Param(
                model.T, initialize=band_afrr_down, within=pyo.Reals, mutable=False, default=0
            ),
        )
        model.add_component(
            f"e_act_up_{self.name}",
            pyo.Param(
                model.T, initialize=e_afrr_act_up, within=pyo.Reals, mutable=False, default=0
            ),
        )
        model.add_component(
            f"e_act_down_{self.name}",
            pyo.Param(
                model.T, initialize=e_afrr_act_down, within=pyo.Reals, mutable=False, default=0
            ),
        )
        # Variables
        model.add_component(f"Band_up_{self.name}", pyo.Var(model.T, domain=pyo.NonNegativeReals))

        model.add_component(f"Band_down_{self.name}", pyo.Var(model.T, domain=pyo.NonNegativeReals))

        model.add_component(f"P_up_{self.name}", pyo.Var(model.T, domain=pyo.NonNegativeReals))

        model.add_component(f"P_down_{self.name}", pyo.Var(model.T, domain=pyo.NonNegativeReals))
        # Constraints
        model.add_component(
            f"band_up_market_limit_{self.name}",
            pyo.Constraint(
                model.T,
                rule=lambda m, t: (
                    getattr(model, f"Band_up_{self.name}")[t]
                    <= getattr(model, f"band_up_{self.name}")[t]
                ),
            ),
        )

        model.add_component(
            f"band_down_market_limit_{self.name}",
            pyo.Constraint(
                model.T,
                rule=lambda m, t: (
                    getattr(model, f"Band_down_{self.name}")[t]
                    <= getattr(model, f"band_down_{self.name}")[t]
                ),
            ),
        )

        model.add_component(
            f"band_up_system_limit_{self.name}",
            pyo.Constraint(
                model.T, rule=lambda m, t: getattr(m, f"Band_up_{self.name}")[t] <= max_afrr_up
            ),
        )

        model.add_component(
            f"band_down_system_limit_{self.name}",
            pyo.Constraint(
                model.T, rule=lambda m, t: getattr(m, f"Band_down_{self.name}")[t] <= max_afrr_down
            ),
        )

        model.add_component(
            f"act_up_requirement_{self.name}",
            pyo.Constraint(
                model.T,
                rule=lambda m, t: (
                    getattr(m, f"P_up_{self.name}")[t]  # Var
                    == getattr(m, f"e_act_up_{self.name}")[t]  # Param from 0 to 1
                    * getattr(m, f"Band_up_{self.name}")[t]  # Var ofered act band
                ),
            ),
        )

        model.add_component(
            f"act_down_requirement_{self.name}",
            pyo.Constraint(
                model.T,
                rule=lambda m, t: (
                    getattr(m, f"P_down_{self.name}")[t]
                    == getattr(m, f"e_act_down_{self.name}")[t]
                    * getattr(m, f"Band_up_{self.name}")[t]
                ),
            ),
        )

        # Expressions
        model.add_component(
            f"Market_output_{self.name}",
            pyo.Expression(
                model.T,
                rule=lambda m, t: (
                    getattr(m, f"P_up_{self.name}")[t] - getattr(m, f"P_down_{self.name}")[t]
                ),
            ),
        )

        model.add_component(
            f"Power_pre_allocated_{self.name}", pyo.Expression(model.T, rule=lambda m, t: 0)
        )

        model.add_component(
            f"Revenues_{self.name}",
            pyo.Expression(
                expr=sum(
                    (
                        getattr(model, f"Band_up_{self.name}")[t]
                        * getattr(model, f"p_up_{self.name}")[t]
                    )
                    + (
                        getattr(model, f"Band_down_{self.name}")[t]
                        * getattr(model, f"p_down_{self.name}")[t]
                    )
                    + (
                        (
                            getattr(model, f"P_up_{self.name}")[t]
                            * getattr(model, f"p_act_up_{self.name}")[t]
                        )
                        + (
                            -getattr(model, f"P_down_{self.name}")[t]
                            * getattr(model, f"p_act_down_{self.name}")[t]
                        )
                    )
                    * model.dt[t]
                    for t in model.T
                )
            ),
        )

    def results(self, model: pyo.ConcreteModel):
        records = []

        for t in model.T:
            records.append(
                {
                    "time": t,
                    f"p_up_{self.parent_name}": pyo.value(getattr(model, f"p_up_{self.name}")[t]),
                    f"p_down_{self.parent_name}": pyo.value(
                        getattr(model, f"p_down_{self.name}")[t]
                    ),
                    f"p_act_up_{self.parent_name}": pyo.value(
                        getattr(model, f"p_act_up_{self.name}")[t]
                    ),
                    f"p_act_down_{self.parent_name}": pyo.value(
                        getattr(model, f"p_act_down_{self.name}")[t]
                    ),
                    f"band_up_{self.parent_name}": pyo.value(
                        getattr(model, f"band_up_{self.name}")[t]
                    ),
                    f"band_down_{self.parent_name}": pyo.value(
                        getattr(model, f"band_down_{self.name}")[t]
                    ),
                    f"e_act_up_{self.parent_name}": pyo.value(
                        getattr(model, f"e_act_up_{self.name}")[t]
                    ),
                    f"e_act_down_{self.parent_name}": pyo.value(
                        getattr(model, f"e_act_down_{self.name}")[t]
                    ),
                    f"Band_up_{self.parent_name}": pyo.value(
                        getattr(model, f"Band_up_{self.name}")[t]
                    ),
                    f"Band_down_{self.parent_name}": pyo.value(
                        getattr(model, f"Band_down_{self.name}")[t]
                    ),
                    f"P_up_{self.parent_name}": pyo.value(getattr(model, f"P_up_{self.name}")[t]),
                    f"P_down_{self.parent_name}": pyo.value(
                        getattr(model, f"P_down_{self.name}")[t]
                    ),
                }
            )

        df = pd.DataFrame(records).set_index("time").sort_index()

        return df


class Milp_MFRR(MFRR):
    def components(self, model: pyo.ConcreteModel):
        """
        Adds the components (Sets, Variables, Parameters, Constraints) required to include this market in the ``model``.
        """
        self.name = self.__class__.__name__
        prices = self.datasets["p_pmd"]["value"].to_dict()
        energy = self.datasets["e_pmd"]["value"].to_dict()

        # Sets
        # NONE

        # Parameters
        model.add_component(
            f"p_{self.name}",
            pyo.Param(model.T, initialize=prices, within=pyo.Reals, mutable=False, default=0),
        )

        model.add_component(
            f"e_{self.name}",
            pyo.Param(model.T, initialize=energy, within=pyo.Reals, mutable=False, default=0),
        )
        # Variables
        model.add_component(f"bin_{self.name}", pyo.Var(model.T, domain=pyo.Binary))

        model.add_component(f"P_buy_{self.name}", pyo.Var(model.T, domain=pyo.NonNegativeReals))

        model.add_component(f"P_sell_{self.name}", pyo.Var(model.T, domain=pyo.NonNegativeReals))
        # Constraints
        model.add_component(
            f"output_market_limit_{self.name}",
            pyo.Constraint(
                model.T,
                rule=lambda m, t: (
                    getattr(model, f"P_sell_{self.name}")[t]
                    + getattr(model, f"P_buy_{self.name}")[t]
                    <= getattr(model, f"e_{self.name}")[t]
                ),
            ),
        )

        model.add_component(
            f"sell_mode_limit_{self.name}",
            pyo.Constraint(
                model.T,
                rule=lambda m, t: (
                    getattr(model, f"P_sell_{self.name}")[t]
                    <= m.system_capacity_export * getattr(model, f"bin_{self.name}")[t]
                ),
            ),
        )

        model.add_component(
            f"buy_mode_limit_{self.name}",
            pyo.Constraint(
                model.T,
                rule=lambda m, t: (
                    getattr(model, f"P_buy_{self.name}")[t]
                    <= m.system_capacity_import * (1 - getattr(model, f"bin_{self.name}")[t])
                ),
            ),
        )

        # Expressions
        model.add_component(
            f"Power_pre_allocated_{self.name}", pyo.Expression(model.T, rule=lambda m, t: 0)
        )

        model.add_component(
            f"Revenues_{self.name}",
            pyo.Expression(
                expr=sum(
                    (
                        getattr(model, f"P_sell_{self.name}")[t]
                        - getattr(model, f"P_buy_{self.name}")[t]
                    )
                    * getattr(model, f"p_{self.name}")[t]
                    * model.dt[t]
                    for t in model.T
                )
            ),
        )

    def results(self, model: pyo.ConcreteModel):
        records = []

        for t in model.T:
            records.append(
                {
                    "time": t,
                    f"p_{self.parent_name}": pyo.value(getattr(model, f"p_{self.name}")[t]),
                    f"P_sell_{self.parent_name}": pyo.value(
                        getattr(model, f"P_sell_{self.name}")[t]
                    ),
                    f"P_buy_{self.parent_name}": pyo.value(getattr(model, f"P_buy_{self.name}")[t]),
                }
            )

        df = pd.DataFrame(records).set_index("time").sort_index()

        return df
