import copy
from typing import Literal

import pandas as pd
import pvlib

from ..utils.cache import df_cache


class Module:
    """
    Base module, all the common properties in modules are located here.
    """

    @classmethod
    def from_module(cls, other):
        new = cls.__new__(cls)
        new.__dict__.update(copy.deepcopy(other.__dict__))
        return new


class Photovoltaic(Module):
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
        name: str | None = None,
    ):
        if not ((peak_power == None) * (latitude == None) * (longitude == None) + (name == None)):
            raise NameError("peak_power, latitude, longitude cannont be None if name is also None")

        self.peak_power = peak_power
        self.latitude = latitude
        self.longitude = longitude
        self.tracker = tracker
        self.tilt = tilt if tilt is not None else latitude
        self.azimuth = azimuth
        self.losses = losses
        self.name = (
            name or f"PV{str(self.peak_power)}LAT{str(self.latitude)}LON{str(self.longitude)}"
        )

        self.production = None

    def __str__(self):
        return f"""\
Photovoltaic; Name {self.name} ; Peak power {self.peak_power} MWp ; Lat {self.latitude}º ; Lon {self.longitude}º ; Tracker {self.tracker} ; Tilt {self.tilt} ; Azimuth {self.azimuth:.2f} ; Losses {self.losses:.2f}\
"""

    def __repr__(self):
        return f"""\
Photovoltaic(name={self.name}, peak_power={self.peak_power}, latitude={self.latitude}, longitude={self.longitude}, tracker={self.tracker}, tilt={self.tilt}, azimuth={self.azimuth}, losses={self.losses})\
"""

    def get_production(
        self,
        percentile: int | None = 50,
        start_date: str | None = "2001/01/01T00:00:00Z",
        end_date: str | None = "2001/12/31T23:59:00Z",
    ):
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

        production_one_year = self._calculate_percentile_production(percentile=percentile)
        self.production = self._rearrange_production_to_dates(
            production_one_year=production_one_year, start_date=start_date, end_date=end_date
        )

        return self

    def set_production(
        self,
        production_one_year,
        start_date: str | None = "2001/01/01T00:00:00Z",
        end_date: str | None = "2001/12/31T23:59:00Z",
    ):
        """
        Set the production between start_date and end_date by providing a full year of the production.

        :param production_one_year: Production of one full year
        :type production_one_year:
        :param start_date: Start date of the output.
        :type start_date: str | None
        :param end_date: End date of the output.
        :type end_date: str | None
        """

        self.production = self._rearrange_production_to_dates(
            production_one_year=production_one_year, start_date=start_date, end_date=end_date
        )

        return self

    @df_cache()
    def _calculate_percentile_production(self, percentile) -> pd.DataFrame:
        """
        Calculate a syntetic year given a percentile of likelihood.
        """

        meteo, meta = pvlib.iotools.get_pvgis_hourly(
            latitude=self.latitude,
            longitude=self.longitude,
            start=2019,
            end=2023,
            raddatabase="PVGIS-SARAH3",
            components=True,
            surface_tilt=self.latitude,
            surface_azimuth=self.azimuth,
            usehorizon=True,
            outputformat="json",
        )

        meteo["power"] = (
            self.peak_power
            * (meteo["poa_direct"] + meteo["poa_sky_diffuse"] + meteo["poa_ground_diffuse"])
            / 1000
            * self.losses
        ).clip(lower=0)

        meteo["month"] = meteo.index.month
        meteo["day"] = meteo.index.day
        meteo["hour"] = meteo.index.hour

        pxx = (
            meteo.groupby(["month", "day", "hour"])["power"]
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
                utc=True,
            )
        )

        df = pd.DataFrame({"power": pxx["power"].to_numpy()}, index=index).sort_index()

        return df

    def _calculate_production(self, start: int, end: int) -> pd.DataFrame:
        """
        Power output (MW) of the given year.

        Returns
        -------
        pd.DataFrame
        """

        meteo, meta = pvlib.iotools.get_pvgis_hourly(
            latitude=self.latitude,
            longitude=self.longitude,
            start=start,
            end=end,
            raddatabase="PVGIS-SARAH3",
            components=True,
            surface_tilt=self.latitude,
            surface_azimuth=self.azimuth,
            usehorizon=True,
            outputformat="json",
        )

        meteo["power_mw"] = (
            self.peak_power
            * (meteo["poa_direct"] + meteo["poa_sky_diffuse"] + meteo["poa_ground_diffuse"])
            / 1000
            * self.losses
        ).clip(lower=0)

        df = meteo[["power_mw"]]

        return df

    def _rearrange_production_to_dates(
        self, production_one_year: pd.DataFrame, start_date: str, end_date: str
    ) -> pd.DataFrame:
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

        req_dates_index = pd.date_range(start=start_date, end=end_date, freq="1h")
        production_req_dates = pd.DataFrame(index=req_dates_index)
        production_req_dates["dates_key"] = production_req_dates.index.strftime("%m/%dT%H:%M:%SZ")

        production_req_dates = production_req_dates.join(mapping, on="dates_key")
        production_req_dates = production_req_dates.drop(columns="dates_key")

        return production_req_dates

    def power_at(self, t):
        return float(self.production.loc[t, "power"])


class Battery(Module):
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
        capacity: float,
        rte: float,
        c_rate: float,
        dod: float = 1,
        soc_max: float = 1,
        soc_initial: float = 0,
        max_cycles_day: float | None = None,
        max_cycles_day_monthly_avg: float | None = None,
        max_cycles_day_yearly_avg: float | None = None,
        rsoc: tuple[int | None, int | None, Literal["monthly", "yearly"] | None] | None = None,
        resting_period: int | None = None,
        min_power_output: float | None = 0.1,
        name: str | None = None,
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

    def __post_init__(self):
        self.name = self.name or f"B{str(self.capacity)}C{str(self.c_rate)}RTE{str(self.rte)}"

    def __str__(self):
        return f"""\
Battery; Name {self.name} ; Capacity {self.capacity:.2f} MW ; RTE {self.rte:.2f} ; C_rate {self.c_rate:.2f} 1/h ; DOD {self.dod:.2f} ; SOC_max {self.soc_max:.2f} ; SOC_initial {self.soc_initial:.2f} ; Max cycles per day {self.max_cycles_day} cycles ; Max cycles per day monthly average {self.max_cycles_day_monthly_avg} ; Max cycles per day yearly average {self.max_cycles_day_yearly_avg} cycles ; RSOC {self.rsoc} ; Resting period {self.resting_period} h\
"""

    def __repr__(self):
        return f"""\
Battery(name={self.name}, capacity={self.capacity}, rte={self.rte}, c_rate={self.c_rate}, dod={self.dod}, soc_max={self.soc_max}, soc_initial={self.soc_initial}, max_cycles_day={self.max_cycles_day}, max_cycles_day_monthly_avg={self.max_cycles_day_monthly_avg}, max_cycles_day_yearly_avg={self.max_cycles_day_yearly_avg}, max_power_output={self.max_power_output}, min_power_output={self.min_power_output}, rsoc={self.rsoc}, resting_period={self.resting_period})\
"""


class System:
    """
    Module container. All modules in the system are connected via
    a single module, which in turn connects to the grid; the system's
    import and export power values are limited by capacity_buy and
    capacity_sell.

    :var modules: Description
    :vartype modules: float
    :var efficiency: Description
    :vartype efficiency: float
    :var capacity_buy: Description
    :vartype capacity_buy: float
    :var capacity_sell: Description
    :vartype capacity_sell: float
    """

    module_map = {}

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
            batteries_str += f"{battery}"
        for generator in self.generators:
            generators_str += f"{generator}"

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
            batteries_repr += f"{repr(battery)},"
        for generator in self.generators:
            generators_repr += f"{repr(generator)},"

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
        match module:
            case Battery():
                self.batteries.append(module)
            case Photovoltaic():
                self.generators.append(module)

        return self

    @classmethod
    def from_system(cls, other):
        new = cls.__new__(cls)
        for key, value in other.__dict__.items():
            if key not in ("batteries", "generators"):
                setattr(new, key, copy.deepcopy(value))
        new.batteries = []
        new.generators = []
        for module in other.batteries + other.generators:
            new.add_module(cls._migrate_module(module))
        return new

    @classmethod
    def _migrate_module(cls, module):
        for parent_cls, child_cls in cls.module_map.items():
            if isinstance(module, parent_cls):
                return child_cls.from_module(module)
        return copy.deepcopy(module)
