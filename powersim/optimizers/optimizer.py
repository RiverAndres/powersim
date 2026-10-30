from ..assets.modules import System
from ..markets.markets import Market

class Optimizer():
    """Common parameters + migration. Childs add their own __init__."""
 
    system_class = System
    market_map = {}
 
    def __init__(self, system: System, markets: list[Market]):
 
        self.system = self.system_class.from_system(other=system)
        self.markets = [self._migrate_market(market) for market in markets]
        self.timestamps = next(iter(markets[0].datasets.values()))
 
        self.model = None
        self.results = None
 
    @classmethod
    def _migrate_market(cls, market: Market):
        for parent_cls in type(market).__mro__:
            if parent_cls in cls.market_map:
                return cls.market_map[parent_cls].from_market(market)
        raise TypeError(
            f"{cls.__name__}: no hay clase Milp para {type(market).__name__}; "
            f"añádela a {cls.__name__}.market_map"
        )
 