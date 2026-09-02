from collectors.base import BaseCollector
from collectors.talabat import TalabatCollector

COLLECTORS: dict[str, type[BaseCollector]] = {
    "talabat": TalabatCollector,
}


def get_collector(platform: str) -> BaseCollector:
    key = platform.strip().lower()
    if key not in COLLECTORS:
        supported = ", ".join(sorted(COLLECTORS))
        raise ValueError(f"Unsupported platform '{platform}'. Supported: {supported}")
    return COLLECTORS[key]()
