from typing import Any

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from collectors import get_collector, list_platforms
from configurations import list_configurations
from database import (
    compare_latest,
    create_database,
    get_analytics,
    get_price_history,
    get_snapshot,
    list_snapshots,
    save_data,
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


app = FastAPI(title="FoodLens API", version="1.0.0")


@app.on_event("startup")
def initialize_database() -> None:
    create_database()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


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
    snapshot_id = save_data(data)
    return CollectionResponse(snapshot_id=snapshot_id, data=data)