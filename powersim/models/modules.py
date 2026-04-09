import pvlib
import pandas as pd
import pyomo.environ as pyo
from typing import Literal
from calendar import isleap, monthrange

from ..utils.cache import df_cache

class System():
    """
    Docstring for System
    
    :var modules: Description
    :vartype modules: float
    :var efficiency: Description
    :vartype efficiency: float
    :var capacity_buy: Description
    :vartype capacity_buy: float
    :var capacity_sell: Description
    :vartype capacity_sell: float
    """

    def __init__(
        self,
        capacity_buy: float,
        capacity_sell: float,
        efficiency: float,
    ):

        self.capacity_buy = capacity_buy
        self.capacity_sell = capacity_sell
        self.efficiency = efficiency

        self.batteries = []
        self.generators = []

    def __str__(self):
        
        batteries_str = ""
        generators_str = ""

        for battery in self.batteries:
            batteries_str +=f"{battery}"
        for generator in self.generators:
            generators_str +=f"{generator}"

        return f"""\
System; Access capacity buy{self.capacity_buy:.2f} MW ; Access capacity sell {self.capacity_sell:.2f} MW ; Efficiency {self.efficiency:.2f}
Modules:
{generators_str}
{batteries_str}\
"""
    
    def __repr__(self):
                
        batteries_repr = "["
        generators_repr = "["

        for battery in self.batteries:
            batteries_repr +=f"{repr(battery)},"
        for generator in self.generators:
            generators_repr +=f"{repr(generator)},"

        batteries_repr += "]"
        generators_repr += "]"

        return f"""\
System(capacity_buy={self.capacity_buy}, capacity_sell={self.capacity_sell}, efficiency={self.efficiency})
Modules=[{batteries_repr}, {generators_repr}]\
"""
    
    def add_module(self, module):
        """
        Add a generation/storage module to the system.
        
        :param module: Description
        """
        type_of_module = module.__class__.__name__

        match type_of_module:
            case "Battery":
                self.batteries.append(module)
            case "Photovoltaic":
                self.generators.append(module)

        return self
    
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

class Photovoltaic():
    """
    Photovoltaic power plant.

    :var peak_power: Description
    :vartype peak_power: float
    :var latitude: Description
    :vartype latitude: float
    :var longitude: Description
    :vartype longitude: float
    :var tracker: Description
    :vartype tracker: Literal["None","N-S","E-W","Both"]

    Methods
    ----------

    Returns
    ----------
    Photovoltaic object
        * self.production
        * self.ehpp

    """
    def __init__(
        self,
        peak_power: float | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        tracker: str | None = None,
        tilt: float | None = None,
        azimuth: float = 180,
        losses: float = 0.85,
        name: str | None = None
    ):
        if not (
            (peak_power == None)*
            (latitude == None)*
            (longitude == None)+
            (name == None)
            ):
            raise NameError("peak_power, latitude, longitude cannont be None if name is also None")
        

        self.peak_power = peak_power
        self.latitude = latitude
        self.longitude = longitude
        self.tracker = tracker
        self.tilt = tilt if tilt is not None else latitude
        self.azimuth = azimuth
        self.losses = losses
        self.name = name or f"PV{str(self.peak_power)}LAT{str(self.latitude)}LON{str(self.longitude)}"

        self.production = None


    def __str__(self):
        return f"""\
Photovoltaic; Name {self.name} ; Peak power {self.peak_power:.2f} MWp ; Lat {self.latitude:.4f}º ; Lon {self.longitude:.4f}º ; Tracker {self.tracker} ; Tilt {self.tilt:.2f} ; Azimuth {self.azimuth:.2f} ; Losses {self.losses:.2f}\
"""
    
    def __repr__(self):
        return f"""\
Photovoltaic(name={self.name}, peak_power={self.peak_power}, latitude={self.latitude}, longitude={self.longitude}, tracker={self.tracker}, tilt={self.tilt}, azimuth={self.azimuth}, losses={self.losses})\
"""
    
    def get_production(self, percentile: int | None = 50, start_date: str | None = "2001/01/01T00:00:00Z", end_date: str | None = "2001/12/31T23:59:00Z"):
        """
        Obtain a full year of power production of the generation module.

        :param percentile:
            Cumulative probability that the plant will have production equalto or worse than that obtained.
            The output is a full year corresponding to the given percentile.
            In finance, the opposite criterion is often used, which seeks to obtain the cumulative
            probability of obtaining higher (or better, depending on expectations) results. In this case,
            it is usually accompanied by the letter “P” followed by the cumulative probability. Below is an
            example showing both conventions. On the left is the one that should be used in this method.

            * ``percentile`` = 10 ; is equivalent to ; P90 
            * ``percentile`` = 50 ; is equivalent to ; P50
            * ``percentile`` = 90 ; is equivalent to ; P10

        :type percentile: Literal[str, bool]
        
    
        Returns
        ----------

        self
        """

        production_one_year = self._calculate_percentile_production(percentile = percentile)
        self.production = self._rearrange_production_to_dates(production_one_year = production_one_year, start_date = start_date, end_date = end_date)

        return self

    def set_production(self , production_one_year, start_date: str | None = "2001/01/01T00:00:00Z", end_date: str | None = "2001/12/31T23:59:00Z"):
        """
        Set the production between start_date and end_date by providing a full year of the production.
        
        :param production_one_year: Production of one full year
        :type production_one_year:
        :param start_date: Start date of the output.
        :type start_date: str | None
        :param end_date: End date of the output.
        :type end_date: str | None
        """

        self.production = self._rearrange_production_to_dates(production_one_year = production_one_year, start_date = start_date, end_date = end_date)

        return self

    @df_cache()
    def _calculate_percentile_production(self, percentile) -> pd.DataFrame:
        """
        Calculate a syntetic year given a percentile of likelihood.
        """

        meteo, meta = pvlib.iotools.get_pvgis_hourly(
            latitude = self.latitude,
            longitude = self.longitude,
            start = 2019,
            end = 2023,
            raddatabase = "PVGIS-SARAH3",
            components=True,
            surface_tilt=self.latitude,
            surface_azimuth = self.azimuth,
            usehorizon=True,
            outputformat="json"
        )

        meteo["power"] = (
            self.peak_power
            * (meteo["poa_direct"] + meteo["poa_sky_diffuse"] + meteo["poa_ground_diffuse"]) / 1000
            * self.losses
        ).clip(lower=0)

        meteo["month"] = meteo.index.month
        meteo["day"] = meteo.index.day
        meteo["hour"] = meteo.index.hour

        pxx = (
            meteo
            .groupby(["month", "day", "hour"])["power"]
            .quantile(percentile / 100)
            .reset_index()
        )

        index = pd.DatetimeIndex(
            pd.to_datetime(
                {
                    "year": 2000,
                    "month": pxx["month"].astype(int),
                    "day": pxx["day"].astype(int),
                    "hour": pxx["hour"].astype(int),
                },
                utc=True
            )
        )

        df = pd.DataFrame(
            {
                "power": pxx["power"].to_numpy()
            },
            index=index
        ).sort_index()

        return df
    
    def _calculate_production(self, start:int, end:int ) -> pd.DataFrame:
        """
        Power output (MW) of the given year.

        Returns
        -------
        pd.DataFrame
        """

        meteo, meta = pvlib.iotools.get_pvgis_hourly(
            latitude = self.latitude,
            longitude = self.longitude,
            start = start,
            end = end,
            raddatabase = "PVGIS-SARAH3",
            components = True,
            surface_tilt = self.latitude,
            surface_azimuth = self.azimuth,
            usehorizon = True,
            outputformat = "json"
        )

        meteo["power_mw"] = (
            self.peak_power
            * (meteo["poa_direct"] + meteo["poa_sky_diffuse"] + meteo["poa_ground_diffuse"]) / 1000
            * self.losses
        ).clip(lower=0)
        
        df = meteo[["power_mw"]]

        return df
    
    def _rearrange_production_to_dates(self, production_one_year:pd.DataFrame, start_date:str, end_date:str) -> pd.DataFrame:
        """
        Rearrange the production dates into the provided ones. The output production will be the same every year.
        
        :param production: pd.DataFrame with the power production. It must have only one column.
        :type production: pd.DataFrame
        :param start_date: Initial date of the required output power production.
        :type start_date: str
        :param end_date: Final date of the required output power production.
        :type end_date: str
        :return: DataFrame with the power production from ``start_date`` and until ``end_date``.
        :rtype: pd.DataFrame
        """

        production_one_year["dates_key"] = production_one_year.index.strftime("%m/%dT%H:%M:%SZ")
        mapping = production_one_year.set_index("dates_key")

        req_dates_index = pd.date_range(start = start_date, end = end_date, freq = "1h")
        production_req_dates = pd.DataFrame(index = req_dates_index)
        production_req_dates["dates_key"] = production_req_dates.index.strftime("%m/%dT%H:%M:%SZ")
        
        production_req_dates = production_req_dates.join(mapping, on = "dates_key")
        production_req_dates = production_req_dates.drop(columns = "dates_key")

        return production_req_dates
    
    def power_at(self, t):
        return float(self.production.loc[t, "power"])
    
    def results(self):
        df = self.production.copy()
        df = df.rename(columns={"power": "P_gen"})

        return df

class Battery():
    """   
    Class that represents a standalone - battery. 
    
    :vartype capacity: float
    :var capacity: Total amount of energy that can be storaged in the battery in MWh.
    :vartype rte: float
    :var rte: Roundtrip efficiency (both charge and discharge). 
    :vartype c_rate: float
    :var c_rate: Inverse of hours of storage: max power output (of the battery, not the interconnection capacity) over capacity.
    :vartype dod: float = 1
    :var dod: Dept of discharge. Amount of the energy that can be discharged (percentual): (1 - minimal amount of energy that needs to remain always in the battery) / capacity.
    :vartype soc_max: float = 1
    :var soc_max: Max state of charge. Max amount of energy that can be stored (percentual).
    :vartype soc_initial: float = 0
    :var soc_initial: Initial state of charge of the battery.
    :vartype max_cycles_day: float | None = None
    :var max_cycles_day: Maximum amount of cycles allowed per day.
    :vartype max_cycles_day_avg: float | None = None
    :var max_cycles_day_avg: Maximum amount of cycles allowed per day, yearly average.
    :vartype rsoc: tuple[int | None, int | None, Literal["monthly", "yearly"] | None] | None = None
    :var rsoc: Allowed range of values for the average soc during rest periods. The average is calculated monthly or yearly.
    :vartype resting_period: float | None = None
    :var resting_period: Minimum rest period in hours between battery charging and discharging periods.
    :vartype min_power_output: float | None = 0.1
    :var min_power_output: Minimum power output.
    :vartype name: str | None = None
    :var name: Name of the battery.

    """
    def __init__(
            self,
            capacity:float,
            rte:float,
            c_rate:float,
            dod:float = 1,
            soc_max:float = 1,
            soc_initial:float = 0,
            max_cycles_day:float | None = None,
            max_cycles_day_monthly_avg:float | None = None,
            max_cycles_day_yearly_avg:float | None = None,
            rsoc: tuple[int | None, int | None, Literal["monthly", "yearly"] | None] | None = None,
            resting_period: int | None = None,
            min_power_output: float | None = 0.1,
            name:str | None = None
    ):
        self.capacity = capacity
        self.rte = rte
        self.c_rate = c_rate
        self.dod = dod
        self.soc_max = soc_max
        self.soc_initial = soc_initial
        self.max_cycles_day = max_cycles_day
        self.max_cycles_day_monthly_avg = max_cycles_day_monthly_avg
        self.max_cycles_day_yearly_avg = max_cycles_day_yearly_avg
        self.max_power_output = capacity * c_rate
        self.min_power_output = min_power_output
        self.rsoc = rsoc
        self.resting_period = resting_period
        self.name = name or f"B{str(self.capacity)}C{str(self.c_rate)}RTE{str(self.rte)}"
    
    def __str__(self):
        return f"""\
Battery; Name {self.name} ; Capacity {self.capacity:.2f} MW ; RTE {self.rte:.2f} ; C_rate {self.c_rate:.2f} 1/h ; DOD {self.dod:.2f} ; SOC_max {self.soc_max:.2f} ; SOC_initial {self.soc_initial:.2f} ; Max cycles per day {self.max_cycles_day} cycles ; Max cycles per day monthly average {self.max_cycles_day_monthly_avg} ; Max cycles per day yearly average {self.max_cycles_day_yearly_avg} cycles ; RSOC {self.rsoc} ; Resting period {self.resting_period} h\
"""
    
    def __repr__(self):
        return f"""\
Battery(name={self.name}, capacity={self.capacity}, rte={self.rte}, c_rate={self.c_rate}, dod={self.dod}, soc_max={self.soc_max}, soc_initial={self.soc_initial}, max_cycles_day={self.max_cycles_day}, max_cycles_day_monthly_avg={self.max_cycles_day_monthly_avg}, max_cycles_day_yearly_avg={self.max_cycles_day_yearly_avg}, max_power_output={self.max_power_output}, min_power_output={self.min_power_output}, rsoc={self.rsoc}, resting_period={self.resting_period})\
"""
    def _base_lp_components(self, model: pyo.ConcreteModel):
        b = self.name

        def soc_balance(m, t):
            if t == model.T.first():
                return (
                    m.SOC[b, t]
                    == self.soc_initial
                    + self.rte**(1/2) * m.P_charge[b, t] * m.dt[t] / self.capacity
                    - (1/self.rte**(1/2)) * m.P_discharge[b, t] * m.dt[t] / self.capacity
                )
            t_prev = model.T.prev(t)

            return (
                m.SOC[b, t]
                == m.SOC[b, t_prev]
                + self.rte**(1/2) * m.P_charge[b, t] * m.dt[t] / self.capacity
                - (1 / self.rte**(1/2)) * m.P_discharge[b, t] * m.dt[t] / self.capacity
            )
        
        model.add_component(
            f"soc_balance_{b}",
            pyo.Constraint(model.T, rule = soc_balance),
        )

        model.add_component(
            f"soc_limit_{b}",
            pyo.Constraint(
                model.T, rule  = lambda m, t: m.SOC[b, t] <= self.soc_max
            ),
        )

        model.add_component(
            f"charge_limit_{b}",
            pyo.Constraint(
                model.T, rule = lambda m, t: m.P_charge[b, t] <= self.max_power_output
            ),
        )

        model.add_component(
            f"discharge_limit_{b}",
            pyo.Constraint(
                model.T, rule = lambda m, t: m.P_discharge[b, t] <= self.max_power_output
            ),
        )

    def _additional_milp_components(self, model: pyo.ConcreteModel):
        b = self.name
        day = model.D # SET of days
        month = model.M # set of months
        year = model.Y # set of years

        def mode_of_operation_check(m, t):
            return  m.rest[b, t] + m.charge[b, t] + m.discharge[b, t] == 1
        
        model.add_component(
            f"mode_of_operation_check_{b}",
            pyo.Constraint(
                model.T, rule = mode_of_operation_check
            )
        )

        def discharge_mode(m, t):
            return m.P_charge[b, t] <= self.max_power_output * m.charge[b, t]

        model.add_component(
            f"discharge_mode_{b}",
            pyo.Constraint(
                model.T, rule = discharge_mode
            )
        )

        def charge_mode(m, t):
            return m.P_discharge[b, t] <= self.max_power_output * m.discharge[b, t]

        model.add_component(
            f"charge_mode_{b}",
            pyo.Constraint(
                model.T, rule = charge_mode
            )
        )

        def min_charge_allowed(m, t):
            return m.P_charge[b, t] >= self.min_power_output * m.charge[b, t]
        
        model.add_component(
            f"min_charge_allowed_{b}",
            pyo.Constraint(
                model.T, rule = min_charge_allowed
            )
        )

        def min_discharge_allowed(m, t):
            return m.P_discharge[b, t] >= self.min_power_output * m.discharge[b, t]
        
        model.add_component(
            f"min_discharge_allowed_{b}",
            pyo.Constraint(
                model.T, rule = min_discharge_allowed
            )
        )

    # limitacion de ciclado anual promedio y ciclo diario máximo
        if self.max_cycles_day or self.max_cycles_day_monthly_avg or self.max_cycles_day_yearly_avg:
            def charge_cycles_rule(m, t):
                if t == model.T.first():
                    return m.cycles[b, t] == 0
                t_prev = model.T.prev(t)
                return m.cycles[b, t] >= (m.SOC[b, t] - m.SOC[b, t_prev]) / 2
            
            def discharge_cycles_rule(m, t):
                if t == model.T.first():
                    return pyo.Constraint.Skip
                t_prev = model.T.prev(t)
                return m.cycles[b, t] >= (m.SOC[b, t_prev] - m.SOC[b, t]) / 2 

            model.add_component(
                f"cycles_charge_{b}",
                pyo.Constraint(
                    model.T, rule = charge_cycles_rule
                )
            )
            model.add_component(
                f"cycles_discharge{b}",
                pyo.Constraint(
                    model.T, rule = discharge_cycles_rule
                )
            )

        if self.max_cycles_day:
            def max_cycles_day(m, d):
                return sum(
                    m.cycles[b, t] for t in model.T if m.day_of_t[t] == d
                ) <= self.max_cycles_day
            
            model.add_component(
                f"max_cycles_day_{b}",
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
                    m.cycles[b, t] for t in model.T if m.year_of_t[t] == y
                ) <= self.max_cycles_day_yearly_avg * days_of_the_year
        
            model.add_component(
                f"max_cycles_day_yearly_avg{b}",
                pyo.Constraint(
                    year, rule = max_cycles_year
                )
            )

        if self.max_cycles_day_monthly_avg:
            def max_cycles_month(m, month):
                return sum(
                    m.cycles[b, t] for t in model.T if m.month_of_t[t] == month
                ) <= self.max_cycles_day_monthly_avg * monthrange(month//100, month%100)[1]

            model.add_component(
                f"max_cycles_day_monthly_avg{b}",
                pyo.Constraint(
                    month, rule = max_cycles_month
                )
            )

    # limitacion de rsoc anual o mensual.
        if self.rsoc:
            rsoc_min = min(self.rsoc[:1])
            rsoc_max = max(self.rsoc[:1])

            model.add_component(
                f"rsoc_upper_absolute_bound_{b}",
                pyo.Constraint(
                    model.T, rule = lambda m, t: m.RSOC[b, t]
                    <= self.soc_max * m.rest[b, t]
                )
            )

            model.add_component(
                f"rsoc_upper_relative_bound_{b}",
                pyo.Constraint(
                    model.T, rule = lambda m, t: m.RSOC[b, t]
                    <= m.SOC[b, t]
                )
            )

            model.add_component(
                f"rsoc_lower_relative_bound_{b}",
                pyo.Constraint(
                    model.T, rule = lambda m, t: m.RSOC[b, t]
                    >= m.SOC[b, t] - self.soc_max * (1- m.rest[b, t])
                )
            )

    # sección específica para rsoc anual
            if self.rsoc[2] == "yearly":

                def rsoc_min_calculation(m, period):
                    return (
                        sum(
                            m.RSOC[b, t] * m.dt[t] for t in model.T if m.year_of_t[t] == period
                        ) 
                        >=
                        rsoc_min * sum(
                            m.dt[t] * m.rest[b, t] for t in model.T if m.year_of_t[t] == period
                        )
                    )

                def rsoc_max_calculation(m, period):
                    return (
                        sum(
                            m.RSOC[b, t] * m.dt[t] for t in model.T if m.year_of_t[t] == period
                        ) <= rsoc_max * sum(
                            m.dt[t] * m.rest[b, t] for t in model.T if m.year_of_t[t] == period
                        )
                    )

                model.add_component(
                    f"rsoc_min_{b}",
                    pyo.Constraint(
                        year, rule = rsoc_min_calculation
                    )
                )

                model.add_component(
                    f"rsoc_max_{b}",
                    pyo.Constraint(
                        year, rule = rsoc_max_calculation
                    )
                )

    # sección específica para rsoc mensual
            else:
                def rsoc_min_calculation(m, period):
                    return (
                        sum(
                            m.RSOC[b, t] * m.dt[t] for t in m.T if m.month_of_t[t] == period
                        ) 
                        >=
                        rsoc_min * sum(
                            m.dt[t] * m.rest[b, t] for t in model.T if m.month_of_t[t] == period
                        )
                    )

                def rsoc_max_calculation(m, period):
                    return (
                        sum(
                            m.RSOC[b, t] * m.dt[t] for t in model.T if m.month_of_t[t] == period
                        ) <= rsoc_max * sum(
                            m.dt[t] * m.rest[b, t] for t in model.T if m.month_of_t[t] == period
                        )
                    )

                model.add_component(
                    f"rsoc_min_{b}",
                    pyo.Constraint(
                        month, rule = rsoc_min_calculation
                    )
                )

                model.add_component(
                    f"rsoc_max_{b}",
                    pyo.Constraint(
                        month, rule = rsoc_max_calculation
                    )
                )

    # Seccion especifica para forzar tiempo de reposo

        if self.resting_period:
            model.add_component(
                f"Switch_{self.name}",
                pyo.Var(model.T, domain = pyo.Binary)
            )

            def switch_on_at_rest_state(m, t): # switch on when changing from charge/discharge to rest
                if t == model.T.first():
                    return pyo.Constraint.Skip
                
                t_prev = m.T.prev(t)
                return (
                    getattr(model, f"Switch_{self.name}")[t]
                    >=
                    m.charge[b, t_prev] +
                    m.discharge[b, t_prev] -
                    m.charge[b, t] -
                    m.discharge[b, t]
                )
            
            model.add_component(
                f"switch_on_at_rest_state_{b}",
                pyo.Constraint(
                    model.T, rule = switch_on_at_rest_state
                )
            )
            
            def switch_at_charge_change(m, t): # switch on when changing from charge to discharge
                if t == model.T.first():
                    return pyo.Constraint.Skip
                
                t_prev = m.T.prev(t)
                return (
                    getattr(model, f"Switch_{self.name}")[t]
                    >=
                    m.charge[b, t_prev] +
                    m.discharge[b, t] -
                    1
                )
                
            model.add_component(
                f"switch_at_charge_change_{b}",
                pyo.Constraint(
                    model.T, rule = switch_at_charge_change
                )
            )

            def switch_at_discharge_change(m, t): # switch on when changing from charge to discharge
                if t == model.T.first():
                    return pyo.Constraint.Skip
                
                t_prev = m.T.prev(t)
                return (
                    getattr(model, f"Switch_{self.name}")[t]
                    >=
                    m.discharge[b, t_prev] +
                    m.charge[b, t] -
                    1
                )

            model.add_component(
                f"switch_at_discharge_change_{b}",
                pyo.Constraint(
                    model.T, rule = switch_at_discharge_change
                )
            )

            def min_resting_period(m, t):
                total_elapsed_time = 0
                current_rest_time = 0

                for tp in m.T.atleast(t):
                    total_elapsed_time += m.dt[tp]
                    current_rest_time += m.rest[b, tp] * m.dt[tp]

                    if total_elapsed_time >= self.resting_period:
                        break

                    return current_rest_time >= self.resting_period * getattr(model, f"Switch_{self.name}")[t]

                
            model.add_component(
                f"min_resting_period_{b}",
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

        self._base_lp_components(model = model)
        if additional_components:
            self._additional_milp_components(model = model)

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