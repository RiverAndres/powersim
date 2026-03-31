import pyomo.environ as pyo
from pyomo.opt import SolverStatus, TerminationCondition
from .base_optimizer import BaseOptimizer
from ..visualization.results import SimulationResult
from ..models.modules import System, Battery, Photovoltaic
from ..markets.base import Market
from ..utils.helpers import calculate_time_deltas
import pandas as pd
import numpy as np


class PerfectOptimizer(BaseOptimizer):
    """
    MILP approach to maximize the benefit of the system. 
    """

    def __init__(self, system:System, markets:list[Market], solver_name:str = "highs", precision:int = 1):

        self.system = system
        self.markets = markets
        self.prices = markets[0].datasets["p_pmd"]
        self.solver_name = solver_name
        self.precision = precision

        self.model = None
        self.results = None

    def _model_setup(self) -> pyo.ConcreteModel:
        
        time_index = self.prices.index.tolist()
        time_duration = calculate_time_deltas(time_index)

        day_index = sorted({t.date() for t in time_index})
        month_index = sorted({t.year*100 + t.month for t in time_index})
        year_index = sorted({t.year for t in time_index})

        for g in self.system.generators:
            g.production = g.production.reindex(time_index, method = "ffill")

        if len(self.system.batteries) == 0:
            self.system.capacity_buy = 0

        # MODEL
        self.model = pyo.ConcreteModel()

        # SETS
        self.model.T = pyo.Set(initialize = time_index, ordered = True)

        self.model.D = pyo.Set(initialize = day_index, ordered = True)
        self.model.M = pyo.Set(initialize = month_index, ordered = True)
        self.model.Y = pyo.Set(initialize = year_index, ordered = True)

        battery_names = [b.name for b in self.system.batteries]
        self.model.B = pyo.Set(initialize = battery_names)

        # PARAMETERS
        self.model.system_capacity_export = pyo.Param(
            initialize = self.system.capacity_sell,
            within = pyo.NonNegativeReals
        )

        self.model.system_capacity_import = pyo.Param(
            initialize = self.system.capacity_buy,
            within = pyo.NonNegativeReals
        )

        self.model.dt = pyo.Param(
            self.model.T,
            initialize = time_duration,
            within = pyo.PositiveReals,
            mutable = False,
        )

        self.model.day_of_t = pyo.Param(
            self.model.T,
            initialize = {t: t.date() for t in time_index},
            within = self.model.D
        )

        self.model.month_of_t = pyo.Param(
            self.model.T,
            initialize = {t: t.year*100 + t.month for t in time_index},
            within= self.model.M
        )

        self.model.year_of_t = pyo.Param(
            self.model.T,
            initialize = {t: t.year for t in time_index},
            within = self.model.Y
        )

        # VARIABLES
            ## MARKET VARIABLES 
                # NONE

            ## SYSTEM VARIABLES
        self.model.bin_system = pyo.Var(self.model.T, domain = pyo.Binary)
        self.model.P_import = pyo.Var(self.model.T, domain = pyo.NonNegativeReals)
        self.model.P_export = pyo.Var(self.model.T, domain = pyo.NonNegativeReals)
        self.model.P_excess = pyo.Var(self.model.T, domain = pyo.NonNegativeReals)

            ## BATTERY VARIABLES
        self.model.P_charge = pyo.Var(self.model.B, self.model.T, domain = pyo.NonNegativeReals)
        self.model.P_discharge = pyo.Var(self.model.B, self.model.T, domain = pyo.NonNegativeReals)
        self.model.SOC = pyo.Var(self.model.B, self.model.T, domain = pyo.NonNegativeReals)
        self.model.cycles = pyo.Var(self.model.B, self.model.T, within = pyo.NonNegativeReals)
        self.model.charge = pyo.Var(self.model.B, self.model.T, within = pyo.Binary, initialize = 0)
        self.model.discharge = pyo.Var(self.model.B, self.model.T, within = pyo.Binary, initialize = 0)
        self.model.rest = pyo.Var(self.model.B, self.model.T, within = pyo.Binary, initialize = 0)
        self.model.RSOC = pyo.Var(self.model.B, self.model.T, within = pyo.NonNegativeReals, initialize = 0)

        # SYSTEM CONSTRAINTS
            ## Balance between modules and system
        def system_balance_rule(m, t):
            generation = sum(
                g.power_at(t) for g in self.system.generators
            )

            discharge = sum(
                m.P_discharge[b, t] for b in m.B
            )

            charge = sum(
                m.P_charge[b, t] for b in m.B
            )

            if len(self.system.batteries) == 0:
                return (
                generation
                == m.P_export[t]
                + m.P_excess[t]
                )

            return (
                m.P_import[t]
                + generation
                + discharge
                == m.P_export[t]
                + charge
                + m.P_excess[t]
            )

        self.model.system_balance = pyo.Constraint(
            self.model.T, rule = system_balance_rule
        )

        # self.model.import_limit = pyo.Constraint(
        #     self.model.T,
        #     rule = lambda m, t: m.P_import[t]
        #     <= m.system_capacity_export,
        # )

        # self.model.export_limit = pyo.Constraint(
        #     self.model.T,
        #     rule = lambda m, t: m.P_export[t]
        #     <= m.system_capacity_import,
        # )

        self.model.export_mode_limit = pyo.Constraint(
            self.model.T,
            rule = lambda m, t: (m.P_export[t]
                <= m.system_capacity_export * m.bin_system[t]
            )
        )

        self.model.import_mode_limit = pyo.Constraint(
            self.model.T,
            rule = lambda m, t: (m.P_import[t]
                <= m.system_capacity_import * (1 - m.bin_system[t])
            )
        )

        def excess_power_rule(m, t):
            generation = sum(
                g.power_at(t) for g in self.system.generators
            )

            if generation > m.system_capacity_export:
                return (
                    m.P_excess[t]
                    <= generation 
                    - self.model.system_capacity_export
                )
            return (
                m.P_excess[t]
                == 0
            )
        
        self.model.excess_power = pyo.Constraint(
            self.model.T, rule = excess_power_rule
        )

        for battery in self.system.batteries:
            battery.constraints(self.model)

        for market in self.markets:
            market.components(self.model)

        # MARKET CONSTRAINTS
            ## Balace between markets and output power

        def market_sell_limit(m, t):
            return (
                sum(
                    getattr(m, f"Market_output_{market.__class__.__name__}")[t]
                    for market in self.markets
                ) <= m.P_export[t] * self.system.efficiency
            )
        
        self.model.market_sell_limit = pyo.Constraint(
            self.model.T,
            rule = market_sell_limit
        )

        def market_buy_limit(m, t):
            return (
                sum(
                    - getattr(m, f"Market_output_{market.__class__.__name__}")[t]
                    for market in self.markets
                ) <= m.P_import[t]
            )
        
        self.model.market_buy_limit = pyo.Constraint(
            self.model.T,
            rule = market_buy_limit
        )

        def market_balance_rule(m, t):
            return (
                sum(
                    getattr(m, f"Power_allocated_{market.__class__.__name__}")[t]
                    for market in self.markets
                )
                ==
                self.system.efficiency * m.P_export[t] + 
                m.P_import[t]
            )

        self.model.market_balance = pyo.Constraint(
            self.model.T,
            rule = market_balance_rule
        )

        return self.model
    

    
    def _objective_maximize_revenues(self) -> pyo.ConcreteModel:
        
        self.model.objective = pyo.Objective(
            expr = sum(
                getattr(self.model, f"Revenues_{market.__class__.__name__}")
                for market in self.markets
            ),
            sense = pyo.maximize,
        )

        return self.model

    def _solve(self):

        solver = pyo.SolverFactory(self.solver_name)
        solver.options["mip_rel_gap"] = self.precision / 100
        # solver.options["threads"] = 12
        results = solver.solve(self.model, tee = True)

        if (
            results.solver.status != SolverStatus.ok
            or results.solver.termination_condition
            != TerminationCondition.optimal
        ):
            raise RuntimeError("Optimización fallida")
        
        self.results = SimulationResult(
            optimizer_name = self.__class__.__name__,
            markets = self.markets,
            system = self.system,
            simulation = self.model,
            )

        return self.model

    def solve(self):
        self._model_setup()
        self._objective_maximize_revenues()
        self._solve()

        return self