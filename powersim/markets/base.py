from abc import ABC, abstractmethod

class Market(ABC):
    def __init__(self, datasets: dict[str, object] = None):
        self.datasets = datasets or {}
        
    @abstractmethod
    def get_info(self, esios_token:str, start_date:str, end_date:str):
        pass