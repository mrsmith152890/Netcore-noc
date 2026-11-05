from datetime import datetime
from pydantic import BaseModel

class PeriodInfo(BaseModel):
    start: datetime
    end: datetime
    hours: float
    site: str | None

class DeviceRow(BaseModel):
    device_id: int
    name: str
    ip: str
    site: str
    availability_pct: float | None
    coverage_pct: float
    samples: int
    failed: int
    outages: int
    est_downtime_s: int
    avg_rtt_ms: float | None
    avg_loss_pct: float | None

class ServiceRow(BaseModel):
    check_id: int
    device: str
    name: str
    kind: str
    availability_pct: float | None
    samples: int
    failed: int
    avg_latency_ms: float | None
    p95_latency_ms: float | None

class AlertRow(BaseModel):
    id: int
    device: str
    rule: str
    severity: str
    state: str
    started_at: datetime
    ended_at: datetime | None
    duration_s: int | None
    detail: str | None

class TopDevice(BaseModel):
    device: str
    alerts: int

class AlertsSummary(BaseModel):
    total: int
    critical: int
    warning: int
    mttr_s: int | None
    top_devices: list[TopDevice]

class Report(BaseModel):
    period: PeriodInfo
    avg_availability_pct: float | None
    total_outages: int
    devices: list[DeviceRow]
    services: list[ServiceRow]
    alerts: AlertsSummary
    alert_rows: list[AlertRow]
