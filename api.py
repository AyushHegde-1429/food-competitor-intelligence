import sqlite3
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from collectors import get_collector, list_platforms
from configurations import list_configurations
from database import (
    compare_latest,
    compare_basket,
    compare_menu_parity,
    get_competitive_price,
    get_data_quality_report,
    get_deal_intelligence,
    get_market_analysis,
    get_menu_intelligence,
    compare_menus,
    create_database,
    get_analytics,
    get_menu_price_history,
    get_price_history,
    get_snapshot,
    list_snapshots,
    save_data,
    get_collection_runs,
    ensure_canonical_item,
    record_item_mapping,
    match_item_names,
    evaluate_item_mapping_results,
    normalize_item_name,
    record_checkout_feedback,
    get_checkout_feedback_summary,
    save_basket,
    get_saved_basket,
    list_saved_baskets,
    update_basket,
    delete_basket,
    get_restaurant_parity,
)


class CollectionRequest(BaseModel):
    platform: str
    country: str
    city: str
    restaurant: str
    location: str | None = None
    url: str
    items: list[str] = Field(default_factory=list)


class CollectionResponse(BaseModel):
    snapshot_id: int
    data: dict[str, Any]


class ComparisonRow(BaseModel):
    platform: str
    price: float
    rating: float | None
    delivery_fee: float | None
    service_fee: float | None
    discount: float | None
    eta: str | None
    collected_at: str


class ComparisonResponse(BaseModel):
    results: list[ComparisonRow]
    cheapest_platform: str | None
    cheapest_price: float | None
    price_difference: float | None
    number_of_platforms_with_data: int


class MenuPlatformSide(BaseModel):
    platform: str
    location: str | None
    snapshot_id: int
    collected_at: str
    item_count: int


class MenuComparisonItem(BaseModel):
    name: str
    prices: dict[str, float]
    cheapest_platform: str
    cheapest_price: float
    price_difference: float | None


class MenuComparisonResponse(BaseModel):
    restaurant: str
    country: str
    city: str
    location: str
    platforms: list[MenuPlatformSide]
    items: list[MenuComparisonItem]
    matched_item_count: int
    number_of_platforms_with_data: int


class BasketItemRequest(BaseModel):
    name: str = Field(min_length=1)
    quantity: int = Field(gt=0, strict=True)

    @field_validator("name")
    @classmethod
    def require_nonblank_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("Item name must not be blank")
        return name


class BasketComparisonRequest(BaseModel):
    restaurant: str = Field(min_length=1)
    country: str = Field(min_length=1)
    city: str = Field(min_length=1)
    location: str = Field(min_length=1)
    items: list[BasketItemRequest] = Field(min_length=1)

    @field_validator("restaurant", "country", "city", "location")
    @classmethod
    def require_nonblank_value(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Value must not be blank")
        return normalized


class BasketItemResult(BaseModel):
    requested_name: str
    matched_name: str | None
    quantity: int
    unit_price: float | None
    line_total: float | None
    available: bool


class BasketComparisonSummary(BaseModel):
    cheapest_platform: str | None
    best_overall_platform: str | None
    best_deal_platform: str | None
    savings: float | None
    savings_percentage: float | None
    comparison_basis: str | None
    winner_reason: str | None
    winner_confidence: str


class BasketPlatformResult(BaseModel):
    platform: str
    available: bool
    status: str
    snapshot_id: int | None
    snapshot_location: str | None
    collected_at: str | None
    age_minutes: int | None
    freshness_status: str | None
    freshness_label: str | None
    should_refresh: bool
    items: list[BasketItemResult]
    matched_items: list[BasketItemResult]
    missing_items: list[BasketItemResult]
    item_subtotal: float | None
    delivery_fee: float | None
    service_fee: float | None
    discount: float | None
    tax: float | None
    known_total: float | None
    estimated_total: float | None
    total_status: str | None
    complete: bool
    confidence: str
    cartly_score: float | None
    score_band: str
    component_scores: dict[str, float | None]
    score_reasons: list[str]
    score_confidence: str


class BasketComparisonResponse(BaseModel):
    restaurant: str
    country: str
    city: str
    location: str
    items: list[BasketItemRequest]
    requested_items: list[BasketItemRequest]
    platforms: list[BasketPlatformResult]
    cheapest_platform: str | None
    best_overall_platform: str | None
    best_deal_platform: str | None
    savings: float | None
    comparison: BasketComparisonSummary


class MenuParityPlatform(BaseModel):
    platform: str
    available: bool
    snapshot_id: int | None
    location: str | None
    collected_at: str | None
    total_items: int | None
    listed_items: int | None
    availability_rate: float | None


class MenuParityResponse(BaseModel):
    restaurant: str
    country: str
    city: str
    location: str
    status: str
    platform_a: str
    platform_b: str
    platforms: list[MenuParityPlatform]
    total_items_platform_a: int | None
    total_items_platform_b: int | None
    shared_items: int | None
    platform_a_only_count: int | None
    platform_b_only_count: int | None
    platform_a_only_items: list[str]
    platform_b_only_items: list[str]
    availability_rate_a: float | None
    availability_rate_b: float | None
    parity_score: float | None


class PriceHistoryObservation(BaseModel):
    snapshot_id: int
    collected_at: str
    price: float


class PriceHistoryResponse(BaseModel):
    item: str
    platform: str
    location: str
    days: int
    current_price: float
    average_price: float
    minimum_price: float
    maximum_price: float
    observation_count: int
    price_change: float
    price_change_percentage: float | None
    history: list[PriceHistoryObservation]


class DealIntelligenceResponse(BaseModel):
    restaurant: str
    item: str
    platform: str
    location: str
    days: int
    current_price: float | None
    historical_average: float | None
    historical_minimum: float | None
    historical_maximum: float | None
    observation_count: int
    difference_from_average: float | None
    difference_from_average_pct: float | None
    deal_status: str
    confidence: str
    freshness_status: str | None
    freshness_label: str | None = None


class CompetitivePlatformPrice(BaseModel):
    platform: str
    snapshot_id: int
    location: str
    collected_at: str
    age_minutes: int | None
    freshness_status: str
    freshness_label: str
    should_refresh: bool
    available: bool
    item_name: str | None
    item_price: float | None
    difference_from_cheapest: float | None = None
    difference_from_cheapest_pct: float | None = None
    relative_price_position: str | None = None


class CompetitivePriceResponse(BaseModel):
    restaurant: str
    country: str
    city: str
    location: str
    item: str
    platforms: list[CompetitivePlatformPrice]
    comparable_platform_count: int
    cheapest_platform: str | None
    market_average_price: float | None
    price_difference: float | None
    price_difference_percentage: float | None
    comparison_basis: str | None
    confidence: str


class MenuIntelligenceResponse(BaseModel):
    restaurant: str
    country: str
    city: str
    location: str
    platforms: list[MenuParityPlatform]
    menu_parity: dict[str, Any]
    price_gaps: list[dict[str, Any]]
    platform_exclusive_items: list[dict[str, Any]]
    category_comparison: list[dict[str, Any]]
    opportunities: list[dict[str, Any]]
    confidence: str


class HistoryRow(BaseModel):
    platform: str
    item: str
    price: float
    collected_at: str


class AveragePrice(BaseModel):
    platform: str
    average_price: float
    observation_count: int


class CheapestItemPrice(BaseModel):
    item: str
    platform: str
    average_price: float
    observation_count: int


class PriceChange(BaseModel):
    platform: str
    item: str
    earliest_price: float
    latest_price: float
    price_change: float
    earliest_collected_at: str
    latest_collected_at: str


class AnalyticsResponse(BaseModel):
    total_snapshots: int
    total_platforms: int
    total_restaurants: int
    total_tracked_items: int
    number_of_price_observations: int
    average_item_price_by_platform: list[AveragePrice]
    cheapest_platform_by_item: list[CheapestItemPrice]
    price_changes: list[PriceChange]


class MarketAnalysisResponse(BaseModel):
    status: str
    data_scope: dict[str, Any]
    price_difference: dict[str, Any]
    fee_difference: dict[str, Any]
    winner_frequency: dict[str, float]
    winner_stability: dict[str, Any]
    limitations: list[str]


class DataQualityResponse(BaseModel):
    status: str
    issue_count: int
    issues: list[dict[str, Any]]


class ItemMappingReviewRequest(BaseModel):
    status: str
    match_method: str = "manual"
    confidence: float | None = None


class CheckoutFeedbackRequest(BaseModel):
    platform: str
    restaurant: str
    location: str | None = None
    cartly_known_total: float | None = None
    actual_checkout_total: float | None = None
    difference: float | None = None
    difference_percentage: float | None = None
    reason: str | None = None


class SavedBasketRequest(BaseModel):
    basket_name: str = Field(min_length=1)
    restaurant: str = Field(min_length=1)
    country: str = Field(min_length=1)
    city: str = Field(min_length=1)
    location: str = Field(min_length=1)
    items: list[BasketItemRequest] = Field(min_length=1)
    alert_threshold_pct: float | None = None
    alert_direction: str = "lower"


app = FastAPI(title="FoodLens API", version="1.0.0")


@app.on_event("startup")
def initialize_database() -> None:
    create_database()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/market-analysis", response_model=MarketAnalysisResponse)
def market_analysis(
    restaurant: str | None = None,
    platform: str | None = None,
    country: str | None = None,
    city: str | None = None,
    location: str | None = None,
    days: int = Query(default=30, ge=1, le=365),
) -> MarketAnalysisResponse:
    return MarketAnalysisResponse(**get_market_analysis(
        restaurant=restaurant,
        platform=platform,
        country=country,
        city=city,
        location=location,
        days=days,
    ))


@app.get("/data-quality", response_model=DataQualityResponse)
def data_quality() -> DataQualityResponse:
    return DataQualityResponse(**get_data_quality_report())


@app.get("/collection-runs")
def collection_runs(limit: int = Query(default=50, ge=1, le=500)) -> list[dict[str, Any]]:
    return get_collection_runs(limit=limit)


@app.post("/checkout-feedback")
def checkout_feedback(request: CheckoutFeedbackRequest) -> dict[str, Any]:
    return record_checkout_feedback(
        platform=request.platform,
        restaurant=request.restaurant,
        location=request.location,
        cartly_known_total=request.cartly_known_total,
        actual_checkout_total=request.actual_checkout_total,
        difference=request.difference,
        difference_percentage=request.difference_percentage,
        reason=request.reason,
    )


@app.get("/checkout-feedback")
def checkout_feedback_summary() -> dict[str, Any]:
    return get_checkout_feedback_summary()


@app.post("/saved-baskets")
def create_saved_basket(request: SavedBasketRequest) -> dict[str, Any]:
    basket_id = save_basket(
        basket_name=request.basket_name,
        restaurant=request.restaurant,
        country=request.country,
        city=request.city,
        location=request.location,
        items=[item.model_dump() for item in request.items],
        alert_threshold_pct=request.alert_threshold_pct,
        alert_direction=request.alert_direction,
    )
    return {"basket_id": basket_id, "status": "created"}


@app.get("/saved-baskets")
def saved_baskets(
    restaurant: str | None = None,
    country: str | None = None,
    city: str | None = None,
) -> list[dict[str, Any]]:
    return list_saved_baskets(restaurant=restaurant, country=country, city=city)


@app.get("/saved-baskets/{basket_id}")
def saved_basket(basket_id: int) -> dict[str, Any]:
    basket = get_saved_basket(basket_id=basket_id)
    if basket is None:
        raise HTTPException(status_code=404, detail="Saved basket not found")
    return basket


@app.put("/saved-baskets/{basket_id}")
def update_saved_basket(basket_id: int, request: SavedBasketRequest) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "basket_name": request.basket_name,
        "restaurant": request.restaurant,
        "country": request.country,
        "city": request.city,
        "location": request.location,
        "items": [item.model_dump() for item in request.items],
    }
    if request.alert_threshold_pct is not None:
        payload["alert_threshold_pct"] = request.alert_threshold_pct
    payload["alert_direction"] = request.alert_direction
    return update_basket(basket_id=basket_id, **payload)


@app.delete("/saved-baskets/{basket_id}")
def delete_saved_basket(basket_id: int) -> dict[str, Any]:
    return delete_basket(basket_id=basket_id)


@app.get("/restaurant-parity")
def restaurant_parity(
    restaurant: str = Query(..., min_length=1),
    country: str = Query(..., min_length=1),
    city: str = Query(..., min_length=1),
    location: str = Query(..., min_length=1),
) -> dict[str, Any]:
    return get_restaurant_parity(
        restaurant=restaurant,
        country=country,
        city=city,
        location=location,
    )


@app.get("/item-matches")
def item_matches(
    restaurant: str | None = None,
    platform: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    conn = sqlite3.connect("food_competitor.db")
    conn.row_factory = sqlite3.Row
    try:
        where = []
        values: list[Any] = []
        if restaurant:
            where.append("c.restaurant = ?")
            values.append(restaurant)
        if platform:
            where.append("m.platform = ?")
            values.append(platform)
        if status:
            where.append("m.status = ?")
            values.append(status)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        rows = conn.execute(
            f"""
            SELECT m.*, c.restaurant, c.canonical_name, c.normalized_name AS canonical_normalized
            FROM item_mappings m
            JOIN canonical_items c ON c.id = m.canonical_item_id
            {clause}
            ORDER BY m.updated_at DESC NULLS LAST
            """,
            values,
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


@app.post("/item-matches/manual-review")
def item_mapping_manual_review(
    request: ItemMappingReviewRequest,
    mapping_id: int = Query(..., ge=1),
) -> dict[str, Any]:
    conn = sqlite3.connect("food_competitor.db")
    try:
        conn.execute(
            "UPDATE item_mappings SET status = ?, match_method = ?, confidence = ?, updated_at = ? WHERE id = ?",
            (
                request.status,
                request.match_method,
                request.confidence if request.confidence is not None else 1.0,
                datetime.now(timezone.utc).isoformat(),
                mapping_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return {"status": "updated", "mapping_id": mapping_id, "new_status": request.status}


@app.get("/item-matching/evaluation")
def item_matching_evaluation(
    true_positives: int = Query(default=0, ge=0),
    false_positives: int = Query(default=0, ge=0),
    false_negatives: int = Query(default=0, ge=0),
) -> dict[str, float]:
    return evaluate_item_mapping_results(
        true_positives=true_positives,
        false_positives=false_positives,
        false_negatives=false_negatives,
    )


@app.get("/platforms")
def platforms() -> list[dict[str, str | bool]]:
    return list_platforms()


@app.get("/configurations")
def configurations() -> list[dict[str, Any]]:
    return list_configurations()


@app.get("/compare", response_model=ComparisonResponse)
def compare(
    restaurant: str,
    item: str,
    city: str | None = None,
    country: str | None = None,
) -> ComparisonResponse:
    return ComparisonResponse(**compare_latest(
        restaurant=restaurant,
        item=item,
        city=city,
        country=country,
    ))


@app.get("/compare-menu", response_model=MenuComparisonResponse)
def compare_menu(
    restaurant: str = Query(..., min_length=1),
    country: str = Query(..., min_length=1),
    city: str = Query(..., min_length=1),
    location: str = Query(..., min_length=1),
) -> MenuComparisonResponse:
    return MenuComparisonResponse(**compare_menus(
        restaurant=restaurant,
        country=country,
        city=city,
        location=location,
    ))


@app.get(
    "/menu-parity",
    response_model=MenuParityResponse,
    description=(
        "Compares latest valid full-menu snapshots after exact requested-location "
        "filtering. Usable items have positive finite prices and are not marked "
        "unavailable; exact normalized names are used. parity_score is shared usable "
        "items divided by the union of usable items, multiplied by 100. Menu parity "
        "describes catalog overlap, not completeness of any user basket."
    ),
)
def menu_parity(
    restaurant: str = Query(..., min_length=1),
    country: str = Query(..., min_length=1),
    city: str = Query(..., min_length=1),
    location: str = Query(..., min_length=1),
) -> MenuParityResponse:
    """Return exact-name menu overlap; a missing platform yields a partial result."""
    try:
        result = compare_menu_parity(
            restaurant=restaurant,
            country=country,
            city=city,
            location=location,
        )
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail="Menu parity lookup failed") from exc
    if result.pop("valid_platform_count") == 0:
        raise HTTPException(
            status_code=404,
            detail="No valid full-menu snapshot exists for the requested restaurant and location",
        )
    return MenuParityResponse(**result)


@app.get(
    "/price-history",
    response_model=PriceHistoryResponse,
    description=(
        "Returns exact normalized item observations from full-menu snapshots only, "
        "filtered by restaurant, platform, market, and normalized location. Statistics "
        "use valid positive prices from the requested rolling day window; price_change "
        "is current price minus the window average. History is limited to the newest "
        "requested number of observations."
    ),
)
def menu_price_history(
    restaurant: str = Query(..., min_length=1),
    platform: str = Query(..., min_length=1),
    country: str = Query(..., min_length=1),
    city: str = Query(..., min_length=1),
    location: str = Query(..., min_length=1),
    item: str = Query(..., min_length=1),
    days: int = Query(default=30, ge=1, le=90),
    limit: int = Query(default=200, ge=1, le=500),
) -> PriceHistoryResponse:
    """Return location-isolated historical menu prices and window statistics."""
    try:
        result = get_menu_price_history(
            restaurant=restaurant,
            platform=platform,
            country=country,
            city=city,
            location=location,
            item=item,
            days=days,
            limit=limit,
        )
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail="Price history lookup failed") from exc
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="No valid price history exists for the requested item and location",
        )
    return PriceHistoryResponse(**result)


@app.get(
    "/deal-intelligence",
    response_model=DealIntelligenceResponse,
    description=(
        "Classifies current menu price against real exact-location full-menu history. "
        "At least three observations are required for a deal claim. Thresholds are "
        "great_deal at least 10% below the historical average, good_deal at least 5% "
        "below, above_average at least 5% above, and normal otherwise. Fewer than three "
        "observations yields insufficient_history. Promotional discount fields are not "
        "used as historical deal evidence; stale observations lower confidence."
    ),
)
def deal_intelligence(
    restaurant: str = Query(..., min_length=1),
    platform: str = Query(..., min_length=1),
    country: str = Query(..., min_length=1),
    city: str = Query(..., min_length=1),
    location: str = Query(..., min_length=1),
    item: str = Query(..., min_length=1),
    days: int = Query(default=30, ge=1, le=90),
) -> DealIntelligenceResponse:
    """Return a deterministic historical-price classification, not a promo claim."""
    try:
        result = get_deal_intelligence(
            restaurant=restaurant,
            platform=platform,
            country=country,
            city=city,
            location=location,
            item=item,
            days=days,
        )
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail="Deal intelligence lookup failed") from exc
    return DealIntelligenceResponse(**result)


@app.get(
    "/competitive-price",
    response_model=CompetitivePriceResponse,
    description=(
        "Compares exact normalized item prices from the latest valid full menu at the "
        "requested location. Only platforms carrying the same item are comparable; "
        "market average and price differences use those exact matches only. Top-level "
        "price_difference_percentage is relative to the higher matching price (savings "
        "versus that alternative); per-platform difference_from_cheapest_pct is relative "
        "to the cheapest matching price. Absent alternatives do not produce a market comparison."
    ),
)
def competitive_price(
    restaurant: str = Query(..., min_length=1),
    country: str = Query(..., min_length=1),
    city: str = Query(..., min_length=1),
    location: str = Query(..., min_length=1),
    item: str = Query(..., min_length=1),
) -> CompetitivePriceResponse:
    """Return location-isolated exact-item price positioning across platforms."""
    try:
        result = get_competitive_price(
            restaurant=restaurant,
            country=country,
            city=city,
            location=location,
            item=item,
        )
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail="Competitive price lookup failed") from exc
    if not any(platform["available"] for platform in result["platforms"]):
        raise HTTPException(
            status_code=404,
            detail="No matching priced menu item exists at the requested location",
        )
    return CompetitivePriceResponse(**result)


@app.get(
    "/menu-intelligence",
    response_model=MenuIntelligenceResponse,
    description=(
        "Summarizes observed full-menu price gaps, platform-only items, and category "
        "counts for the exact restaurant location. Opportunities report only measured "
        "coverage or price differences; parity is shared usable items divided by the "
        "union of usable items. No popularity, demand, or profitability is inferred."
    ),
)
def menu_intelligence(
    restaurant: str = Query(..., min_length=1),
    country: str = Query(..., min_length=1),
    city: str = Query(..., min_length=1),
    location: str = Query(..., min_length=1),
    limit: int = Query(default=50, ge=1, le=200),
) -> MenuIntelligenceResponse:
    """Return evidence-based menu gaps without demand or popularity claims."""
    try:
        result = get_menu_intelligence(
            restaurant=restaurant,
            country=country,
            city=city,
            location=location,
            limit=limit,
        )
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail="Menu intelligence lookup failed") from exc
    if not any(platform["available"] for platform in result["platforms"]):
        raise HTTPException(
            status_code=404,
            detail="No valid full-menu snapshot exists for the requested restaurant and location",
        )
    return MenuIntelligenceResponse(**result)


@app.post(
    "/cart/compare",
    response_model=BasketComparisonResponse,
    description=(
        "Compares an exact requested basket against each platform's latest full menu "
        "at the requested location. item_subtotal includes matched requested items only. "
        "NULL fees, discounts, and taxes remain unknown, never zero. known_total adds "
        "only stored non-NULL components; estimated_total is NULL because no estimation "
        "basis exists. Incomplete baskets cannot win. Winners use the same available "
        "cost components across complete platforms; no fees or taxes are estimated. "
        "Freshness bands are fresh (<15 min), recent (<60 min), aging (up to 24 hr), "
        "and stale (>24 hr). should_refresh becomes true at the configurable 24-hour "
        "default threshold or when collection time is unavailable; it does not run a "
        "collector. Confidence is deterministic: fresh, complete comparable known-cost "
        "results may be high; partial known-cost/freshness information is medium; "
        "subtotal-only, incomplete, or stale comparisons are low. Cartly Score weights "
        "are price 40, completeness 20, freshness 15, rating 10, ETA 10, and fee "
        "transparency 5. Only observed component scores earn weight; missing signals "
        "remain null and incomplete baskets are ineligible for best-overall selection."
    ),
)
def compare_cart(request: BasketComparisonRequest) -> BasketComparisonResponse:
    """Return basket item subtotals and known costs, not final checkout totals.

    Missing items make a platform partial. Unknown fees and taxes remain NULL.
    Only complete baskets compete, and savings requires at least two comparable
    complete baskets.
    """
    try:
        result = compare_basket(**request.model_dump())
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=500,
            detail="Basket comparison failed",
        ) from exc
    if result.pop("available_platform_count") == 0:
        raise HTTPException(
            status_code=404,
            detail="No valid full-menu snapshot exists for the requested restaurant and location",
        )
    return BasketComparisonResponse(**result)


@app.get("/history", response_model=list[HistoryRow])
def history(
    restaurant: str,
    item: str,
    platform: str | None = None,
    days: int = Query(default=30, ge=1, le=3650),
) -> list[HistoryRow]:
    return get_price_history(
        restaurant=restaurant,
        item=item,
        platform=platform,
        days=days,
    )


@app.get("/analytics", response_model=AnalyticsResponse)
def analytics() -> AnalyticsResponse:
    return AnalyticsResponse(**get_analytics())


@app.get("/snapshots")
def snapshots(
    platform: str | None = None,
    country: str | None = None,
    restaurant: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict[str, Any]]:
    return list_snapshots(
        platform=platform,
        country=country,
        restaurant=restaurant,
        limit=limit,
    )


@app.get("/snapshots/{snapshot_id}")
def snapshot(snapshot_id: int) -> dict[str, Any]:
    result = get_snapshot(snapshot_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return result


@app.post("/collections", response_model=CollectionResponse, status_code=201)
def collect(request: CollectionRequest) -> CollectionResponse:
    try:
        collector = get_collector(request.platform)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        result = collector.collect(**request.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Collection failed: {exc}") from exc

    data = result.to_dict()
    snapshot_id = save_data(data, location=request.location)
    return CollectionResponse(snapshot_id=snapshot_id, data=data)