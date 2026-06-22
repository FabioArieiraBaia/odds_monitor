from abc import ABC, abstractmethod
from typing import List
from core.normalizer import NormalizedEvent

class BaseSource(ABC):
    @abstractmethod
    def get_name(self) -> str:
        pass

    @abstractmethod
    async def fetch_live_events(self) -> List[NormalizedEvent]:
        pass
