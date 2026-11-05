from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

class SiteCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=255)

class SiteUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=255)
    enabled: bool | None = None

class SiteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: str | None
    enabled: bool
    created_at: datetime
    device_count: int = 0
    scope_count: int = 0
    rule_count: int = 0
    silence_count: int = 0


class SiteDelete(BaseModel):
    target_site_id: int | None = None
