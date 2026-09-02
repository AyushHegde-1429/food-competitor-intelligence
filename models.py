from datetime import datetime

from pydantic import BaseModel, Field


class Item(BaseModel):
    name: str
    price_aed: float | None


class CollectionResult(BaseModel):
    platform: str
    country: str
    city: str
    restaurant: str
    location: str | None
    rating: float | None
    items: list[Item]
    delivery_fee_aed: float | None
    service_fee_aed: float | None
    discount_aed: float | None
    eta_minutes: str | None
    collected_at: str = Field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return self.model_dump()
