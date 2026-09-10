import re
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

from collectors.base import BaseCollector
from models import CollectionResult, Item, MenuItem


CATALOG_ENDPOINT = (
    "https://food.noon.com/uae-en/_svc/mp-food-api-catalog/api/"
    "canonical-zone/{zone}/"
)
GUEST_RESTAURANT_ENDPOINT = (
    "https://food.noon.com/_svc/mp-food-api-mpnoon/consumer/restaurant/"
    "outlet/details/guest"
)
PRECISION = 10_000_000
ZONE_COORDINATES = {
    "dubai silicon oasis": (25.0920, 55.1530),
    "discovery gardens": (25.0352571, 55.1454134),
    "al karama": (25.242223, 55.305696),
    "karama": (25.242223, 55.305696),
}
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Content-Type": "application/json",
    "x-locale": "en-ae",
    "x-mp": "noon",
    "x-experience": "food",
    "x-platform": "web",
    "Connection": "close",
}


def _normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


def _outlet_code(url: str) -> str:
    query_value = parse_qs(urlparse(url).query).get("outlet_code", [None])[0]
    if query_value:
        return query_value
    match = re.search(r"/outlet/([^/?#]+)", urlparse(url).path, re.IGNORECASE)
    if match:
        return match.group(1)
    raise RuntimeError("No Noon outlet code was found in the configured public URL")


def _find_item_price(menu_items: list[dict[str, Any]], target_name: str) -> float | None:
    target = _normalize_name(target_name)
    fallback_price: float | None = None
    for menu_item in menu_items:
        if _normalize_name(menu_item.get("name", "")) == target:
            price = menu_item.get("price")
            listing_price = menu_item.get("listingPrice")
            if isinstance(price, (int, float)) and price > 0:
                return float(price)
            if isinstance(listing_price, (int, float)) and listing_price > 0:
                return float(listing_price)
            if isinstance(price, (int, float)):
                fallback_price = float(price)
    return fallback_price


def _zone_from_location(location: str) -> str:
    if location.strip().lower() in ZONE_COORDINATES:
        return location.strip()
    raise RuntimeError(f"No Noon public coordinates configured for location '{location}'")


def _get_guest_data(outlet_code: str, latitude: float, longitude: float) -> dict[str, Any]:
    body = {
        "addressLat": round(latitude * PRECISION),
        "addressLng": round(longitude * PRECISION),
        "deliveryType": "default",
        "outletCode": outlet_code,
    }
    last_error: Exception | None = None
    for _ in range(3):
        try:
            response = httpx.post(
                GUEST_RESTAURANT_ENDPOINT,
                headers={**HEADERS, "x-visitor-id": "foodlens-collector"},
                json=body,
                timeout=60,
            )
            response.raise_for_status()
            payload = response.json()
            data = payload.get("data", {})
            if payload.get("status") != "success" or not data:
                raise RuntimeError(
                    "Noon guest restaurant response did not contain restaurant data"
                )
            return data
        except (httpx.HTTPError, RuntimeError) as exc:
            last_error = exc
    raise RuntimeError(f"Noon guest restaurant request failed: {last_error}")


def _get_catalog(zone: str, outlet_code: str) -> dict[str, Any]:
    url = CATALOG_ENDPOINT.format(zone=zone.replace(" ", "%20"))
    catalog_headers = {
        key: value for key, value in HEADERS.items() if key != "Content-Type"
    }
    catalog_headers["x-visitor-id"] = "foodlens-collector"
    last_error: Exception | None = None
    for _ in range(3):
        try:
            response = httpx.get(url, headers=catalog_headers, timeout=90)
            response.raise_for_status()
            catalog = response.json()
            record = next(
                (
                    result
                    for result in catalog.get("results", [])
                    if result.get("outletCode") == outlet_code
                ),
                None,
            )
            if record is None:
                raise RuntimeError(
                    "Configured Noon outlet was not found in the public catalog"
                )
            return record
        except (httpx.HTTPError, RuntimeError) as exc:
            last_error = exc
    raise RuntimeError(f"Noon catalog request failed: {last_error}")


class NoonCollector(BaseCollector):
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
        outlet_code = _outlet_code(url)
        zone = _zone_from_location(location)
        latitude, longitude = ZONE_COORDINATES[zone.lower()]

        catalog_record = _get_catalog(zone, outlet_code)

        data = _get_guest_data(outlet_code, latitude, longitude)

        menu_items = data.get("menu", {}).get("items", [])
        categories = {
            category.get("categoryCode"): category.get("name")
            for category in data.get("menu", {}).get("categories", [])
            if category.get("categoryCode")
        }
        collected_items = [
            Item(name=item_name, price_aed=_find_item_price(menu_items, item_name))
            for item_name in items
        ]
        full_menu = [
            MenuItem(
                name=menu_item.get("name", ""),
                price_aed=(
                    float(menu_item["price"])
                    if isinstance(menu_item.get("price"), (int, float))
                    and menu_item["price"] > 0
                    else (
                        float(menu_item["listingPrice"])
                        if isinstance(menu_item.get("listingPrice"), (int, float))
                        and menu_item["listingPrice"] > 0
                        else menu_item.get("price")
                    )
                ),
                category=categories.get(menu_item.get("categoryCode")),
                available=(not menu_item["isOos"] if "isOos" in menu_item else None),
                platform_item_id=menu_item.get("itemCode"),
            )
            for menu_item in menu_items
            if menu_item.get("name") and menu_item.get("itemType") == "main"
        ]

        discounts = data.get("discounts") or []
        flat_discounts = [
            discount.get("configs", {}).get("flat")
            for discount in discounts
            if discount.get("configs", {}).get("flat") is not None
        ]

        return CollectionResult(
            platform=platform,
            country=country,
            city=city,
            restaurant=data.get("name") or catalog_record.get("name") or restaurant,
            location=data.get("address") or location,
            rating=data.get("ratingScore"),
            items=collected_items,
            menu_items=full_menu,
            delivery_fee_aed=data.get("deliveryFee"),
            service_fee_aed=None,
            discount_aed=float(flat_discounts[0]) if flat_discounts else None,
            eta_minutes=str(data["minutesToDeliver"])
            if data.get("minutesToDeliver") is not None
            else catalog_record.get("delivery", {}).get("time"),
        )