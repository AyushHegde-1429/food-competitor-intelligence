import json
import sys
from pathlib import Path

import config
from collectors import get_collector
from database import create_database, save_data


def _output_filename() -> str:
    restaurant_slug = (
        config.RESTAURANT.lower()
        .replace(" ", "_")
        .replace("'", "")
    )
    platform_slug = config.PLATFORM.lower().replace(" ", "_")
    city_slug = config.CITY.lower().replace(" ", "_")
    return f"{platform_slug}_{restaurant_slug}_{city_slug}.json"


def main() -> int:
    create_database()

    collector = get_collector(config.PLATFORM)
    print(f"Collecting from {config.PLATFORM}: {config.RESTAURANT_URL}")

    try:
        result = collector.collect(
            platform=config.PLATFORM,
            country=config.COUNTRY,
            city=config.CITY,
            restaurant=config.RESTAURANT,
            location=config.LOCATION,
            url=config.RESTAURANT_URL,
            items=config.ITEMS,
        )
    except Exception as exc:
        print("\n==============================")
        print("COLLECTION FAILED")
        print("==============================")
        print(exc)
        return 1

    data = result.to_dict()

    print("\n==============================")
    print("COLLECTION SUCCESSFUL")
    print("==============================")
    print(json.dumps(data, indent=2, ensure_ascii=False))

    output_dir = Path(config.OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / _output_filename()

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)

    print(f"\nSaved JSON to: {output_path}")
    save_data(data)
    print("Saved data to SQLite database.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
