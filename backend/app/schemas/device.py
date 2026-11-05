from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, IPvAnyAddress

DeviceType = Literal["router", "switch", "firewall", "server", "ap", "other"]

class DeviceCreate(BaseModel):
    site_id: int
    name: str = Field(min_length=1, max_length=100)
    ip_address: IPvAnyAddress
    device_type: DeviceType = "other"
    vendor: str | None = Field(default=None, max_length=50)
    model: str | None = Field(default=None, max_length=80)
    wan_gateway_ip: IPvAnyAddress | None = None
    wan_probe_ip: IPvAnyAddress | None = None

class DeviceUpdate(BaseModel):
    site_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=100)
    ip_address: IPvAnyAddress | None = None
    device_type: DeviceType | None = None
    vendor: str | None = Field(default=None, max_length=50)
    model: str | None = Field(default=None, max_length=80)
    wan_gateway_ip: IPvAnyAddress | None = None
    wan_probe_ip: IPvAnyAddress | None = None
    enabled: bool | None = None

class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    site_id: int
    name: str
    ip_address: str
    device_type: str
    vendor: str | None
    model: str | None
    wan_gateway_ip: str | None
    wan_probe_ip: str | None
    enabled: bool
    created_at: datetime
    updated_at: datetime
