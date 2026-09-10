import json
import sys
import argparse
from pathlib import Path

import config
from collectors import get_collector
from configurations import CollectionConfiguration, get_configuration
from database import create_database, save_data


def _output_filename(configuration: CollectionConfiguration) -> str:
    restaurant_slug = (
        configuration.restaurant.lower()
        .replace(" ", "_")
        .replace("'", "")
    )
    platform_slug = configuration.platform.lower().replace(" ", "_")
    city_slug = configuration.city.lower().replace(" ", "_")
    return f"{platform_slug}_{restaurant_slug}_{city_slug}.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect FoodLens competitor data")
    parser.add_argument("--platform")
    parser.add_argument("--country")
    parser.add_argument("--city")
    parser.add_argument("--restaurant")
    args = parser.parse_args()
    selected = [args.platform, args.country, args.city, args.restaurant]
    if any(value is not None for value in selected) and not all(selected):
        parser.error(
            "--platform, --country, --city, and --restaurant must be provided together"
        )
    return args


def _selected_configuration(args: argparse.Namespace) -> CollectionConfiguration:
    if all((args.platform, args.country, args.city, args.restaurant)):
        return get_configuration(
            platform=args.platform,
            country=args.country,
            city=args.city,
            restaurant=args.restaurant,
        )
    return config.DEFAULT_CONFIGURATION


def main() -> int:
    args = _parse_args()
    create_database()

    try:
        configuration = _selected_configuration(args)
        collector = get_collector(configuration.platform)
        if configuration.url is None:
            raise ValueError("Selected configuration does not have a verified URL")
    except ValueError as exc:
        print(f"Configuration error: {exc}")
        return 1

    print(f"Collecting from {configuration.platform}: {configuration.url}")

    try:
        result = collector.collect(
            platform=configuration.platform,
            country=configuration.country,
            city=configuration.city,
            restaurant=configuration.restaurant,
            location=configuration.location or "",
            url=configuration.url,
            items=list(configuration.items),
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
    output_path = output_dir / _output_filename(configuration)

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)

    print(f"\nSaved JSON to: {output_path}")
    save_data(data)
    print("Saved data to SQLite database.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
