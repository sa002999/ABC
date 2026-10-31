from enum import StrEnum
from pydantic import BaseModel, Field
from uuid import UUID


class City(StrEnum):
    TOKYO = "TOKYO"
    KYOTO = "KYOTO"


class Store(BaseModel):
    id: UUID
    slug: str
    city: City
    name: dict[str, str]
    address: dict[str, str]
    latitude: float | None
    longitude: float | None
    timezone: str
    opening_hours: dict = Field(serialization_alias="openingHours")
    languages: list[str]
    is_demo: bool = Field(serialization_alias="isDemo")
    image_url: str | None = Field(default=None, serialization_alias="imageUrl")


class StoreList(BaseModel):
    data: list[Store]
