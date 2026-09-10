from collectors.base import BaseCollector
from collectors.catalog import list_platforms
from collectors.noon import NoonCollector
from collectors.talabat import TalabatCollector

COLLECTORS: dict[str, type[BaseCollector]] = {
    "talabat": TalabatCollector,
    "noon_food": NoonCollector,
}


def get_collector(platform: str) -> BaseCollector:
    key = platform.strip().lower().replace(" ", "_")
    if key not in COLLECTORS:
        supported = ", ".join(sorted(COLLECTORS))
        raise ValueError(f"Unsupported platform '{platform}'. Supported: {supported}")
    return COLLECTORS[key]()
