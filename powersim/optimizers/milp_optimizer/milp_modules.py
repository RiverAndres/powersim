from ...assets.modules import System, Battery, Photovoltaic

import pvlib
import pandas as pd
import pyomo.environ as pyo
from typing import Literal
from calendar import isleap, monthrange

from ...utils.cache import df_cache
from ...assets.modules import System, Battery, Photovoltaic

class Milp_Photovoltaic(Photovoltaic):
    def results(self):
        df = self.production.copy()
        df = df.rename(columns={"power": "P_gen"})

        return df

class Milp_Battery(Battery):
    def _base_components(self, model: pyo.ConcreteModel):
        name = self.name

        def soc_balance(m, t):
            if t == model.T.first():
                return (
                    m.SOC[name, t]
                    == self.soc_initial
                    + self.rte**(1/2) * m.P_charge[name, t] * m.dt[t] / self.capacity
                    - (1/self.rte**(1/2)) * m.P_discharge[name, t] * m.dt[t] / self.capacity
                )
            t_prev = model.T.prev(t)

            return (
                m.SOC[name, t]
                == m.SOC[name, t_prev]
                + self.rte**(1/2) * m.P_charge[name, t] * m.dt[t] / self.capacity
                - (1 / self.rte**(1/2)) * m.P_discharge[name, t] * m.dt[t] / self.capacity
            )
        
        model.add_component(
            f"soc_balance_{name}",
            pyo.Constraint(model.T, rule = soc_balance),
        )

        model.add_component(
            f"soc_limit_{name}",
            pyo.Constraint(
                model.T, rule  = lambda m, t: m.SOC[name, t] <= self.soc_max
            ),
        )

        model.add_component(
            f"charge_limit_{name}",
            pyo.Constraint(
                model.T, rule = lambda m, t: m.P_charge[name, t] <= self.max_power_output
            ),
        )

        model.add_component(
            f"discharge_limit_{name}",
            pyo.Constraint(
                model.T, rule = lambda m, t: m.P_discharge[name, t] <= self.max_power_output
            ),
        )

    def _additional_components(self, model: pyo.ConcreteModel):
        name = self.name
        day = model.D # SET of days
        month = model.M # set of months
        year = model.Y # set of years

        def mode_of_operation_check(m, t):
            return  m.rest[name, t] + m.charge[name, t] + m.discharge[name, t] == 1
        
        model.add_component(
            f"mode_of_operation_check_{name}",
            pyo.Constraint(
                model.T, rule = mode_of_operation_check
            )
        )

        def discharge_mode(m, t):
            return m.P_charge[name, t] <= self.max_power_output * m.charge[name, t]

        model.add_component(
            f"discharge_mode_{name}",
            pyo.Constraint(
                model.T, rule = discharge_mode
            )
        )

        def charge_mode(m, t):
            return m.P_discharge[name, t] <= self.max_power_output * m.discharge[name, t]

        model.add_component(
            f"charge_mode_{name}",
            pyo.Constraint(
                model.T, rule = charge_mode
            )
        )

        def min_charge_allowed(m, t):
            return m.P_charge[name, t] >= self.min_power_output * m.charge[name, t]
        
        # model.add_component(
        #     f"min_charge_allowed_{b}",
        #     pyo.Constraint(
        #         model.T, rule = min_charge_allowed
        #     )
        # )

        def min_discharge_allowed(m, t):
            return m.P_discharge[name, t] >= self.min_power_output * m.discharge[name, t]
        
        # model.add_component(
        #     f"min_discharge_allowed_{b}",
        #     pyo.Constraint(
        #         model.T, rule = min_discharge_allowed
        #     )
        # )

    # limitacion de ciclado anual/mensual promedio y ciclo diario máximo
        if self.max_cycles_day or self.max_cycles_day_monthly_avg or self.max_cycles_day_yearly_avg:
            def charge_cycles_rule(m, t):
                if t == model.T.first():
                    return m.cycles[name, t] == 0
                t_prev = model.T.prev(t)
                return m.cycles[name, t] >= (m.SOC[name, t] - m.SOC[name, t_prev]) / 2
            
            def discharge_cycles_rule(m, t):
                if t == model.T.first():
                    return pyo.Constraint.Skip
                t_prev = model.T.prev(t)
                return m.cycles[name, t] >= (m.SOC[name, t_prev] - m.SOC[name, t]) / 2 

            model.add_component(
                f"cycles_charge_{name}",
                pyo.Constraint(
                    model.T, rule = charge_cycles_rule
                )
            )
            model.add_component(
                f"cycles_discharge{name}",
                pyo.Constraint(
                    model.T, rule = discharge_cycles_rule
                )
            )

        if self.max_cycles_day:
            def max_cycles_day(m, d):
                return sum(
                    m.cycles[name, t] for t in model.T if m.day_of_t[t] == d
                ) <= self.max_cycles_day
            
            model.add_component(
                f"max_cycles_day_{name}",
                pyo.Constraint(
                    day, rule = max_cycles_day
                )
            )

        if self.max_cycles_day_yearly_avg:
            def max_cycles_year(m, y):
                if isleap(year = y):
                    days_of_the_year = 366
                else:
                    days_of_the_year = 365

                return sum(
                    m.cycles[name, t] for t in model.T if m.year_of_t[t] == y
                ) <= self.max_cycles_day_yearly_avg * days_of_the_year
        
            model.add_component(
                f"max_cycles_day_yearly_avg{name}",
                pyo.Constraint(
                    year, rule = max_cycles_year
                )
            )

        if self.max_cycles_day_monthly_avg:
            def max_cycles_month(m, month):
                return sum(
                    m.cycles[name, t] for t in model.T if m.month_of_t[t] == month
                ) <= self.max_cycles_day_monthly_avg * monthrange(month//100, month%100)[1]

            model.add_component(
                f"max_cycles_day_monthly_avg{name}",
                pyo.Constraint(
                    month, rule = max_cycles_month
                )
            )

    # limitacion de rsoc anual o mensual.
        if self.rsoc:
            rsoc_min = min(self.rsoc[:1])
            rsoc_max = max(self.rsoc[:1])

            model.add_component(
                f"rsoc_upper_absolute_bound_{name}",
                pyo.Constraint(
                    model.T, rule = lambda m, t: m.RSOC[name, t]
                    <= self.soc_max * m.rest[name, t]
                )
            )

            model.add_component(
                f"rsoc_upper_relative_bound_{name}",
                pyo.Constraint(
                    model.T, rule = lambda m, t: m.RSOC[name, t]
                    <= m.SOC[name, t]
                )
            )

            model.add_component(
                f"rsoc_lower_relative_bound_{name}",
                pyo.Constraint(
                    model.T, rule = lambda m, t: m.RSOC[name, t]
                    >= m.SOC[name, t] - self.soc_max * (1- m.rest[name, t])
                )
            )

    # sección específica para rsoc anual
            if self.rsoc[2] == "yearly":

                def rsoc_min_calculation(m, period):
                    return (
                        sum(
                            m.RSOC[name, t] * m.dt[t] for t in model.T if m.year_of_t[t] == period
                        ) 
                        >=
                        rsoc_min * sum(
                            m.dt[t] * m.rest[name, t] for t in model.T if m.year_of_t[t] == period
                        )
                    )

                def rsoc_max_calculation(m, period):
                    return (
                        sum(
                            m.RSOC[name, t] * m.dt[t] for t in model.T if m.year_of_t[t] == period
                        ) <= rsoc_max * sum(
                            m.dt[t] * m.rest[name, t] for t in model.T if m.year_of_t[t] == period
                        )
                    )

                model.add_component(
                    f"rsoc_min_{name}",
                    pyo.Constraint(
                        year, rule = rsoc_min_calculation
                    )
                )

                model.add_component(
                    f"rsoc_max_{name}",
                    pyo.Constraint(
                        year, rule = rsoc_max_calculation
                    )
                )

    # sección específica para rsoc mensual
            else:
                def rsoc_min_calculation(m, period):
                    return (
                        sum(
                            m.RSOC[name, t] * m.dt[t] for t in m.T if m.month_of_t[t] == period
                        ) 
                        >=
                        rsoc_min * sum(
                            m.dt[t] * m.rest[name, t] for t in model.T if m.month_of_t[t] == period
                        )
                    )

                def rsoc_max_calculation(m, period):
                    return (
                        sum(
                            m.RSOC[name, t] * m.dt[t] for t in model.T if m.month_of_t[t] == period
                        ) <= rsoc_max * sum(
                            m.dt[t] * m.rest[name, t] for t in model.T if m.month_of_t[t] == period
                        )
                    )

                model.add_component(
                    f"rsoc_min_{name}",
                    pyo.Constraint(
                        month, rule = rsoc_min_calculation
                    )
                )

                model.add_component(
                    f"rsoc_max_{name}",
                    pyo.Constraint(
                        month, rule = rsoc_max_calculation
                    )
                )

    # Seccion especifica para forzar tiempo de reposo

        if self.resting_period:
            model.add_component(
                f"Switch_{name}",
                pyo.Var(model.T, domain = pyo.Binary)
            )

            def switch_on_at_rest_state(m, t): # switch on when changing from charge/discharge to rest
                if t == model.T.first():
                    return pyo.Constraint.Skip
                
                t_prev = m.T.prev(t)
                return (
                    getattr(model, f"Switch_{name}")[t]
                    >=
                    m.charge[name, t_prev] +
                    m.discharge[name, t_prev] -
                    m.charge[name, t] -
                    m.discharge[name, t]
                )
            
            model.add_component(
                f"switch_on_at_rest_state_{name}",
                pyo.Constraint(
                    model.T, rule = switch_on_at_rest_state
                )
            )
            
            def switch_at_charge_change(m, t): # switch on when changing from charge to discharge
                if t == model.T.first():
                    return pyo.Constraint.Skip
                
                t_prev = m.T.prev(t)
                return (
                    getattr(model, f"Switch_{name}")[t]
                    >=
                    m.charge[name, t_prev] +
                    m.discharge[name, t] -
                    1
                )
                
            model.add_component(
                f"switch_at_charge_change_{name}",
                pyo.Constraint(
                    model.T, rule = switch_at_charge_change
                )
            )

            def switch_at_discharge_change(m, t): # switch on when changing from charge to discharge
                if t == model.T.first():
                    return pyo.Constraint.Skip
                
                t_prev = m.T.prev(t)
                return (
                    getattr(model, f"Switch_{name}")[t]
                    >=
                    m.discharge[name, t_prev] +
                    m.charge[name, t] -
                    1
                )

            model.add_component(
                f"switch_at_discharge_change_{name}",
                pyo.Constraint(
                    model.T, rule = switch_at_discharge_change
                )
            )

            def min_resting_period(m, t):
                total_elapsed_time = 0
                current_rest_time = 0

                for tp in m.T.atleast(t):
                    total_elapsed_time += m.dt[tp]
                    current_rest_time += m.rest[name, tp] * m.dt[tp]

                    if total_elapsed_time >= self.resting_period:
                        break

                    return current_rest_time >= self.resting_period * getattr(model, f"Switch_{name}")[t]

                
            model.add_component(
                f"min_resting_period_{name}",
                pyo.Constraint(
                    model.T, rule = min_resting_period
                )
            )

    def components(self, model: pyo.ConcreteModel):
        components = [
            self.max_cycles_day,
            self.max_cycles_day_monthly_avg,
            self.max_cycles_day_yearly_avg,
            self.rsoc,
            self.resting_period,
        ]
        additional_components = sum([bool(component) for component in components])  

        self._base_components(model = model)
        if additional_components:
            self._additional_components(model = model)

    def results(self, model: pyo.ConcreteModel):
        records = []

        for t in model.T:
            records.append(
                {
                    "time": t,
                    "P_charge": pyo.value(model.P_charge[self.name, t]),
                    "P_discharge": pyo.value(model.P_discharge[self.name, t]),
                    "SOC": pyo.value(model.SOC[self.name, t]),
                    "dt": pyo.value(model.dt[t]),
                    "name": self.name,
                    "charge": pyo.value(model.charge[self.name, t]),
                    "discharge": pyo.value(model.discharge[self.name, t]),
                    "rest": pyo.value(model.rest[self.name, t]),
                    "RSOC": pyo.value(model.RSOC[self.name, t]),
                }
            )

        df = (
            pd.DataFrame(records)
            .set_index("time")
            .sort_index()
        )

        # Energías útiles
        df["E_charge"] = df["P_charge"] * df["dt"]
        df["E_discharge"] = df["P_discharge"] * df["dt"]

        return df

class Milp_System(System):
    module_map = {
        Battery: Milp_Battery,
        Photovoltaic: Milp_Photovoltaic
    }

    def results(self, model):
        records = []

        for t in model.T:
            records.append(
                {
                    "time": t,
                    "P_grid_import": pyo.value(model.P_import[t]),
                    "P_grid_export": pyo.value(model.P_export[t]),
                    "P_excess": pyo.value(model.P_excess[t]),
                    "dt": pyo.value(model.dt[t]),
                }
            )

        df = (
            pd.DataFrame(records)
            .set_index("time")
            .sort_index()
        )

        return df