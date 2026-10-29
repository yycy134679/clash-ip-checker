from ..results import score_emoji
import abc
from typing import Dict, Optional

class BaseCheckSource(abc.ABC):
    def get_emoji(self, percentage_str):
        return score_emoji(percentage_str)

    @abc.abstractmethod
    async def check(self, proxy: Optional[str] = None) -> Dict:
        """
        Execute check logic.
        Returns a result dictionary.
        """
        pass
