from app.core.config import PHOTO_MAX_BYTES as MAX_BYTES
from app.core.schemas import CamelModel
from app.modules.catalog.schemas import LookSelection
from pydantic import ConfigDict, Field, StrictBool, model_validator
from typing import Literal
from uuid import UUID


class SessionInput(LookSelection):
    source: Literal['SELF', 'MODEL']
    model_id: UUID | None = None
    photo_id: UUID | None = None
    consent_accepted: bool = False
    consent_version: str | None = Field(None, max_length=100)


class UploadInput(CamelModel):
    model_config = ConfigDict(extra='forbid')
    content_type: Literal['image/jpeg', 'image/png', 'image/heic', 'image/heif']
    size: int = Field(gt=0, le=MAX_BYTES)
    file_name: str = Field(min_length=1, max_length=255)
    replace_photo_id: UUID | None = None


class SceneInput(CamelModel):
    model_config = ConfigDict(extra='forbid')
    scene_id: Literal['CHERRY_BLOSSOM','TEMPLE']
    confirmed: StrictBool


class ValidateInput(CamelModel):
    model_config = ConfigDict(extra='forbid')
    photo_id: UUID


class GenerationInput(LookSelection):
    model_config = ConfigDict(extra='forbid')
    photo_id: UUID | None = None
    model_id: UUID | None = None
    belt_id: UUID | None = None
    confirmed: StrictBool

    @model_validator(mode='after')
    def one_outfit(self):
        if self.participants or self.accessory_ids or self.generation_id:
            raise ValueError('每次試穿只接受一位人物、一件和服與選填的一條 beltId 腰帶。')
        return self
