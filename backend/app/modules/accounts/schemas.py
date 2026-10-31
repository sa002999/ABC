from pydantic import BaseModel, ConfigDict


class SyncAccount(BaseModel):
    model_config = ConfigDict(extra="forbid")
