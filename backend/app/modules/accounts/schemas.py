from pydantic import BaseModel, ConfigDict, Field


class SyncAccount(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    display_name: str = Field(alias='displayName', min_length=1, max_length=100)


class PhoneBinding(BaseModel):
    model_config = ConfigDict(extra='forbid')
    phone_token: str = Field(alias='phoneToken', min_length=1, max_length=10000)
