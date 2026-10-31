from app.core.schemas import CamelModel
from app.modules.catalog.schemas import Asset, LookSelection, Participant, Plan
from pydantic import ConfigDict, Field
from typing import Literal
from uuid import UUID


class LookUpdate(LookSelection):
    version: int = Field(ge=1)


class Look(CamelModel):
    look_id: UUID
    name: str = ''
    image_url: str | None = None
    price: int | None = None
    participants: list[Participant] = Field(default_factory=list)
    plan_id: UUID
    kimono_id: UUID
    selected_accessory_ids: list[UUID] = Field(default_factory=list)
    scene_id: UUID | None = None
    generation_id: UUID | None = None
    generation_status: Literal['NOT_GENERATED', 'AVAILABLE', 'EXPIRED', 'DELETED', 'UNAVAILABLE'] = 'NOT_GENERATED'
    version: int
    available: bool
    unavailable_reason: Literal['PLAN_UNAVAILABLE'] | None
    current_price: int | None
    currency: Literal['TWD'] = 'TWD'
    image: Asset | None
    image_source: Literal['PRODUCT', 'GENERATION', 'UNAVAILABLE']
    plan: Plan | None


class LookList(CamelModel):
    data: list[Look]
    total: int
    next_page: int | None


class CompareInput(CamelModel):
    model_config = ConfigDict(extra='forbid')
    look_ids: list[UUID] = Field(min_length=2, max_length=3)
