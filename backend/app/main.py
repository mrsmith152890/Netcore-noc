import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from starlette.concurrency import run_in_threadpool

from app.api.v1 import (alerts, audit, auth, branding, devices, discovery, health, maps, metrics,
                        reports, services, sites, snmp, status, system)
from app.core.audit import record_audit
from app.core.auth import API_PREFIX, SAFE, authorize, client_ip
from app.core.config import settings
from app.core.logging import setup_logging

setup_logging()
log = logging.getLogger("netcore")
DEV = settings.environment == "dev"

@asynccontextmanager
async def lifespan(_app: FastAPI):
    log.info("Iniciando %s (%s)", settings.app_name, settings.environment)
    yield

# Todo es mismo origen (proxy), así que no se habilita CORS.
app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan,
    dependencies=[Depends(authorize)],
    docs_url="/api/docs" if DEV else None,
    redoc_url=None,
    openapi_url="/api/openapi.json" if DEV else None,
)

@app.middleware("http")
async def audit_middleware(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if not path.startswith(API_PREFIX):
        return response
    status_code = response.status_code
    if request.method in SAFE:
        should = status_code == 403              # accesos denegados
    else:
        should = status_code != 401 or path == f"{API_PREFIX}/auth/login"
    if should:
        st = request.state
        await run_in_threadpool(
            record_audit,
            user_id=getattr(st, "user_id", None),
            username=getattr(st, "username", None) or getattr(st, "audit_username", None),
            ip=client_ip(request), method=request.method, path=path,
            status_code=status_code, detail=getattr(st, "audit_detail", None))
    return response

for module in (health, auth, audit, branding, sites, devices, status, snmp, metrics, maps, discovery, alerts, services, reports, system):
    app.include_router(module.router, prefix=API_PREFIX)
