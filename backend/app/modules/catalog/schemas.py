from app.core.schemas import CamelModel
from app.integrations.s3 import cloudfront_url
from pydantic import ConfigDict, Field, model_validator
from typing import Literal
from uuid import UUID
import hashlib
import json

City = Literal['TOKYO', 'KYOTO']

class Asset(CamelModel):
    id: UUID
    kind: Literal['PRODUCT', 'STYLED', 'GENERATION']
    url: str
    alt: dict[str, str]

    @model_validator(mode='before')
    @classmethod
    def image_url(cls, value):
        if value.get('s3_key'):
            value = {**value, 'url': cloudfront_url(value['s3_key'])}
        return value


class Kimono(CamelModel):
    id: UUID
    sku: str
    name: dict[str, str]
    gender: str = 'FEMALE'
    kimono_type: str
    style_tags: list[str]
    is_demo: bool
    images: list[Asset]


class StoreSummary(CamelModel):
    id: UUID
    slug: str
    city: City
    name: dict[str, str]


class Plan(CamelModel):
    id: UUID
    slug: str
    name: dict[str, str]
    summary: dict[str, str]
    description: dict[str, str]
    audience: list[str]
    duration_minutes: int
    kind: str = 'SINGLE'
    cover_image_url: str | None = None
    additional_guest_price: int = 1500
    base_price: int
    currency: Literal['TWD']
    included_items: list[str]
    is_demo: bool
    kimono: Kimono
    stores: list[StoreSummary]


class PlanList(CamelModel):
    data: list[Plan]
    total: int
    next_page: int | None


class KimonoList(CamelModel):
    data: list[Kimono]
    next_page: int | None




class Participant(CamelModel):
    model_config = ConfigDict(extra='forbid')
    id: str
    role: Literal['FEMALE','MALE']
    kimono_id: UUID
    belt_id: UUID | None = None
    generation_id: UUID | None = None


class LookSelection(CamelModel):
    model_config = ConfigDict(extra='forbid')
    plan_id: UUID
    kimono_id: UUID | None = None
    participants: list[Participant] = Field(default_factory=list,max_length=3)
    accessory_ids: list[UUID] = Field(default_factory=list, max_length=20)
    scene_id: UUID | None = None
    generation_id: UUID | None = None

    @model_validator(mode='after')
    def supported_options(self):
        if self.participants:
            if len({p.id for p in self.participants})!=len(self.participants):
                raise ValueError('旅客識別不可重複。')
            self.kimono_id=self.participants[0].kimono_id
        if not self.kimono_id:
            raise ValueError('請選擇和服。')
        if self.accessory_ids and not self.participants:
            if len(self.accessory_ids)!=1: raise ValueError('每位女生限一條腰帶。')
            self.participants=[Participant(id='guest_1',role='FEMALE',kimono_id=self.kimono_id,belt_id=self.accessory_ids[0],generation_id=self.generation_id)]

        if self.scene_id:
            raise ValueError('場景尚未開放。')
        return self

    def fingerprint(self):
        return hashlib.sha256(json.dumps(self.model_dump(mode='json', exclude={'version'}), sort_keys=True).encode()).hexdigest()
