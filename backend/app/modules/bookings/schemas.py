from app.core.errors import error
from app.core.schemas import CamelModel
from pydantic import ConfigDict, Field, model_validator
from typing import Literal
from uuid import UUID


class Guest(CamelModel):
    model_config=ConfigDict(extra='forbid')
    display_name: str=Field('',max_length=60)
    guest_type: Literal['ADULT_FEMALE','ADULT_MALE']='ADULT_FEMALE'
    plan_id: UUID | None=None
    kimono_id: UUID | None=None
    saved_look_id: UUID | None=None
    generation_id: UUID | None=None
    accessory_ids: list[UUID]=Field(default_factory=list,max_length=1)

    @model_validator(mode='after')
    def adult_accessories(self):
        if self.guest_type=='ADULT_MALE' and self.accessory_ids:
            error(422,'INVALID_ACCESSORY','男生不可選配件。')
        return self


class OtherContact(CamelModel):
    model_config=ConfigDict(extra='forbid')
    name: str=Field('',max_length=100)
    email: str=Field('',max_length=254)
    phone: str=Field('',max_length=30)


class ContactVersion(CamelModel):
    model_config=ConfigDict(extra='forbid')
    version: int=Field(ge=1)


class ContactEmailCode(ContactVersion):
    code: str=Field(pattern=r'^[0-9]{6}$')


class ContactPhoneProof(ContactVersion):
    phone_token: str=Field(min_length=1,max_length=4096,repr=False)


class DraftInput(CamelModel):
    model_config=ConfigDict(extra='forbid')
    store_id: UUID | None=None
    slot_id: UUID | None=None
    guests: list[Guest]=Field(min_length=1,max_length=3)
    party_size: int | None=Field(None,ge=1,le=3)
    contact_name: str=Field('',max_length=100)
    contact_email: str=Field('',max_length=254)
    contact_phone: str=Field('',max_length=30)
    contact_mode: Literal['member','other'] | None=None
    other_contact: OtherContact | None=None
    locale: Literal['zh-Hant','en','ja']='zh-Hant'
    add_on_ids: list[UUID]=Field(default_factory=list,max_length=20)
    photography_id: UUID | None=None

    @model_validator(mode='after')
    def guest_count(self):
        if self.party_size is not None and self.party_size!=len(self.guests):
            error(422,'INVALID_GUEST_COUNT','每筆預約限 1～3 人，旅客清單須與人數一致。')
        if self.add_on_ids or self.photography_id:
            error(422,'ADDONS_UNAVAILABLE','攝影與其他加購尚未開放。')
        return self


class DraftUpdate(DraftInput):
    version: int=Field(ge=1)


class QuoteInput(CamelModel):
    model_config=ConfigDict(extra='forbid')
    draft_id: UUID
    version: int=Field(ge=1)


class HoldInput(CamelModel):
    model_config=ConfigDict(extra='forbid')
    draft_id: UUID
    quote_token: UUID


class PaymentInput(CamelModel):
    model_config=ConfigDict(extra='forbid')
    hold_id: UUID
    quote_token: UUID
    prime: str=Field(min_length=1,max_length=100,repr=False)
    accepted_policy: bool
    policy_version: str=Field(max_length=80)
