import json
import sys
import argparse
from pathlib import Path

import config
from collectors import get_collector
from configurations import (
    CONFIGURATION_CATALOG,
    CollectionConfiguration,
    get_configuration,
)
from database import (
    collect_all_configurations,
    create_database,
    save_data,
    sync_canonical_items_from_snapshots,
)


def _output_filename(configuration: CollectionConfiguration) -> str:
    restaurant_slug = (
        configuration.restaurant.lower()
        .replace(" ", "_")
        .replace("'", "")
    )
    platform_slug = configuration.platform.lower().replace(" ", "_")
    city_slug = configuration.city.lower().replace(" ", "_")
    locations = {
        candidate.location
        for candidate in CONFIGURATION_CATALOG
        if candidate.platform.strip().casefold() == configuration.platform.strip().casefold()
        and candidate.country.strip().casefold() == configuration.country.strip().casefold()
        and candidate.city.strip().casefold() == configuration.city.strip().casefold()
        and candidate.restaurant.strip().casefold() == configuration.restaurant.strip().casefold()
        and candidate.location
    }
    location_suffix = ""
    if len(locations) > 1 and configuration.location:
        location_suffix = "_" + configuration.location.lower().replace(" ", "_")
    return f"{platform_slug}_{restaurant_slug}_{city_slug}{location_suffix}.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect FoodLens competitor data")
    parser.add_argument("--platform")
    parser.add_argument("--country")
    parser.add_argument("--city")
    parser.add_argument("--restaurant")
    parser.add_argument("--location")
    parser.add_argument("--all", action="store_true", help="Collect every executable configuration in the catalog")
    args = parser.parse_args()
    selected = [args.platform, args.country, args.city, args.restaurant]
    if any(value is not None for value in selected) and not all(selected):
        parser.error(
            "--platform, --country, --city, and --restaurant must be provided together"
        )
    if args.location is not None and not all(selected):
        parser.error("--location requires platform, country, city, and restaurant")
    return args


def _selected_configuration(args: argparse.Namespace) -> CollectionConfiguration:
    if all((args.platform, args.country, args.city, args.restaurant)):
        return get_configuration(
            platform=args.platform,
            country=args.country,
            city=args.city,
            restaurant=args.restaurant,
            location=getattr(args, "location", None),
        )
    return config.DEFAULT_CONFIGURATION


def main() -> int:
    args = _parse_args()
    create_database()

    if args.all:
        results = collect_all_configurations()
        if not results:
            print("No executable configurations were found.")
            return 1
        print(f"Running {len(results)} collection jobs.")
        failed = 0
        for result in results:
            status = result.get("status")
            configuration = result.get("configuration", {})
            restaurant = configuration.get("restaurant", "unknown")
            platform = configuration.get("platform", "unknown")
            location = configuration.get("location")
            print(f"[{status.upper()}] {platform} / {restaurant} / {location or 'n/a'}")
            if status == "failed":
                failed += 1
        synced_locations: set[tuple[str, str, str, str]] = set()
        for result in results:
            if result.get("status") != "success":
                continue
            configuration = result.get("configuration", {})
            key = (
                configuration.get("restaurant", ""),
                configuration.get("country", ""),
                configuration.get("city", ""),
                configuration.get("location") or "",
            )
            if key in synced_locations or not key[0]:
                continue
            synced_locations.add(key)
            sync_result = sync_canonical_items_from_snapshots(
                restaurant=key[0],
                country=key[1] or None,
                city=key[2] or None,
                location=key[3] or None,
            )
            print(
                f"[MATCHING] {key[0]} / {key[3] or 'n/a'}: "
                f"{sync_result['canonical_items_created']} canonical items, "
                f"{len(sync_result['mappings_created'])} mappings added"
            )
        return 0 if failed == 0 else 1

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
    save_data(data, location=configuration.location)
    print("Saved data to SQLite database.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
