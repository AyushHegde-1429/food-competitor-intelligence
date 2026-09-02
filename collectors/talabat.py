import json
import re
from typing import Any

import httpx

from collectors.base import BaseCollector
from models import CollectionResult, Item

NEXT_DATA_PATTERN = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.DOTALL,
)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def _parse_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    match = re.search(r"[\d.]+", text.replace(",", ""))
    if not match:
        return None
    try:
        return float(match.group())
    except ValueError:
        return None


def _normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


def _find_item_price(menu_items: list[dict[str, Any]], target_name: str) -> float | None:
    normalized_target = _normalize_name(target_name)
    for menu_item in menu_items:
        if _normalize_name(menu_item.get("name", "")) == normalized_target:
            return _parse_float(menu_item.get("price"))
    return None


def _extract_next_data(html: str) -> dict[str, Any]:
    match = NEXT_DATA_PATTERN.search(html)
    if not match:
        raise RuntimeError("Talabat page did not contain __NEXT_DATA__ (page structure may have changed)")
    return json.loads(match.group(1))


class TalabatCollector(BaseCollector):
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
        response = httpx.get(
            url,
            headers=DEFAULT_HEADERS,
            follow_redirects=True,
            timeout=30,
        )
        response.raise_for_status()

        page_data = _extract_next_data(response.text)
        menu_state = page_data.get("props", {}).get("pageProps", {}).get("initialMenuState", {})
        restaurant_data = menu_state.get("restaurant", {})
        menu_items = menu_state.get("menuData", {}).get("items", [])

        if not restaurant_data:
            raise RuntimeError("Talabat page loaded but restaurant data was missing")

        collected_items = [
            Item(name=item_name, price_aed=_find_item_price(menu_items, item_name))
            for item_name in items
        ]

        delivery_fee = _parse_float(restaurant_data.get("deliveryFee"))
        discount_text = (restaurant_data.get("discountText") or "").strip()
        promotion_text = (restaurant_data.get("promotionText") or "").strip()
        discount = _parse_float(discount_text or promotion_text)

        avg_delivery_time = (restaurant_data.get("avgDeliveryTime") or "").strip()
        eta = avg_delivery_time if avg_delivery_time and avg_delivery_time != "0 mins" else None

        return CollectionResult(
            platform=platform,
            country=country,
            city=city,
            restaurant=restaurant_data.get("name") or restaurant,
            location=restaurant_data.get("areaName") or location,
            rating=_parse_float(restaurant_data.get("rate")),
            items=collected_items,
            delivery_fee_aed=delivery_fee,
            service_fee_aed=None,  # Only shown at checkout, not on menu page
            discount_aed=discount,
            eta_minutes=eta,
        )
