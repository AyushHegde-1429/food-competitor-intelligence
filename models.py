from datetime import datetime

from pydantic import BaseModel, Field


class Item(BaseModel):
    name: str
    price_aed: float | None


class MenuItem(BaseModel):
    name: str
    price_aed: float | None
    category: str | None = None
    available: bool | None = None
    platform_item_id: str | None = None


class CollectionResult(BaseModel):
    platform: str
    country: str
    city: str
    restaurant: str
    location: str | None
    rating: float | None
    items: list[Item]
    menu_items: list[MenuItem] = Field(default_factory=list)
    delivery_fee_aed: float | None = None
    service_fee_aed: float | None = None
    discount_aed: float | None = None
    eta_minutes: str | None = None
    collected_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    restaurant_status: str | None = None
    busy_status: str | None = None
    store_open: bool | None = None
    promotion_text: str | None = None
    promotion_type: str | None = None
    raw_status: str | None = None

    def to_dict(self) -> dict:
        return self.model_dump()
