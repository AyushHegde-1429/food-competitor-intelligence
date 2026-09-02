from abc import ABC, abstractmethod

from models import CollectionResult


class BaseCollector(ABC):
    @abstractmethod
    def collect(
        self,
        *,
        platform: str,
        country: str,
        city: str,
        restaurant: str,
        location: str,
        url: str,
        items: list[str],
    ) -> CollectionResult:
        """Collect competitor intelligence for one restaurant."""
