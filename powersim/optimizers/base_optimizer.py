from abc import ABC, abstractmethod

class BaseOptimizer(ABC):
    def __init__(self, photovoltaic, battery, market, rules):
        self.photovoltaic = photovoltaic
        self.battery = battery
        self.market = market
        self.rules = rules
        
    @abstractmethod
    def solve(self):
        pass