from dataclasses import dataclass


@dataclass(frozen=True)
class PlatformDefinition:
    key: str
    name: str
    country: str
    implemented: bool

    @property
    def status(self) -> str:
        return "available" if self.implemented else "planned"


PLATFORM_CATALOG = (
    PlatformDefinition("talabat", "Talabat", "UAE", True),
    PlatformDefinition("deliveroo", "Deliveroo", "UAE", False),
    PlatformDefinition("noon_food", "Noon Food", "UAE", True),
    PlatformDefinition("swiggy", "Swiggy", "India", False),
    PlatformDefinition("zomato", "Zomato", "India", False),
    PlatformDefinition("ownly", "Ownly", "India", False),
    PlatformDefinition("doordash", "DoorDash", "USA", False),
    PlatformDefinition("uber_eats", "Uber Eats", "USA", False),
    PlatformDefinition("grubhub", "Grubhub", "USA", False),
)


def list_platforms() -> list[dict[str, str | bool]]:
    return [
        {
            "key": platform.key,
            "name": platform.name,
            "country": platform.country,
            "implemented": platform.implemented,
            "status": platform.status,
        }
        for platform in PLATFORM_CATALOG
    ]