import asyncio
import ipaddress
import re
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import dns.asyncresolver
import dns.exception
import dns.resolver
import httpx

class CheckConfigError(ValueError):
    pass

@dataclass
class CheckResult:
    success: bool
    latency_ms: float | None
    error: str | None

_STATUS_RE = re.compile(r"^\d{3}(-\d{3})?(,\d{3}(-\d{3})?)*$")
_HOST_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")
_QNAME_RE = re.compile(r"^[A-Za-z0-9_]([A-Za-z0-9_.-]{0,251}[A-Za-z0-9_])?\.?$")
MAX_BODY = 65536

# ---------- validación (pura) ----------
def parse_status_ranges(spec: str | None) -> list[tuple[int, int]]:
    spec = (spec or "200-399").replace(" ", "")
    if not _STATUS_RE.match(spec):
        raise CheckConfigError("Códigos esperados inválidos (ejemplo: 200-399,401)")
    out = []
    for part in spec.split(","):
        lo, _, hi = part.partition("-")
        out.append((int(lo), int(hi or lo)))
    return out

def status_ok(code: int, ranges: list[tuple[int, int]]) -> bool:
    return any(lo <= code <= hi for lo, hi in ranges)

def validate_host(host: str) -> str:
    host = host.strip()
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        if not _HOST_RE.match(host):
            raise CheckConfigError(f"Destino inválido: {host!r}")
        return host
    if ip.is_link_local or ip.is_unspecified or ip.is_multicast:
        raise CheckConfigError("Dirección de destino no permitida")
    return host

def validate_dns_name(name: str) -> str:
    name = name.strip()
    if not _QNAME_RE.match(name):
        raise CheckConfigError("Nombre DNS inválido")
    return name

def validate_http_url(url: str) -> str:
    test = url.strip().replace("{ip}", "192.0.2.1")
    try:
        u = urlparse(test)
        host, _port = u.hostname, u.port       # u.port lanza ValueError si el puerto es inválido
    except ValueError:
        raise CheckConfigError("URL inválida")
    if u.scheme not in ("http", "https") or not host:
        raise CheckConfigError("La URL debe empezar por http:// o https://")
    if u.username or u.password:
        raise CheckConfigError("No se permiten credenciales dentro de la URL")
    validate_host(host)
    return url.strip()

# ---------- ejecución ----------
async def run_tcp(host: str, port: int, timeout: float) -> CheckResult:
    start = time.perf_counter()
    try:
        _reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
    except asyncio.TimeoutError:
        return CheckResult(False, None, "Tiempo de espera agotado")
    except OSError as e:
        return CheckResult(False, None, f"{type(e).__name__}: {e.strerror or e}"[:200])
    latency = (time.perf_counter() - start) * 1000
    writer.close()
    try:
        await writer.wait_closed()
    except OSError:
        pass
    return CheckResult(True, latency, None)

async def run_http(url: str, ranges: list[tuple[int, int]], expect_text: str | None,
                   verify_tls: bool, timeout: float) -> CheckResult:
    start = time.perf_counter()
    elapsed = lambda: (time.perf_counter() - start) * 1000   # noqa: E731
    try:
        async with httpx.AsyncClient(timeout=timeout, verify=verify_tls, follow_redirects=False) as client:
            async with client.stream("GET", url, headers={"User-Agent": "NetCore-NOC/1.0"}) as r:
                if not status_ok(r.status_code, ranges):
                    return CheckResult(False, elapsed(), f"HTTP {r.status_code}")
                if expect_text:
                    needle, body = expect_text.lower(), ""
                    async for chunk in r.aiter_bytes():
                        body += chunk.decode("utf-8", "replace").lower()
                        if needle in body or len(body) >= MAX_BODY:
                            break
                    if needle not in body:
                        return CheckResult(False, elapsed(), "Texto esperado no encontrado en la respuesta")
                return CheckResult(True, elapsed(), None)
    except httpx.TimeoutException:
        return CheckResult(False, None, "Tiempo de espera agotado")
    except httpx.HTTPError as e:
        return CheckResult(False, None, f"{type(e).__name__}: {e}"[:200])

async def run_dns(server: str, port: int, qname: str, qtype: str, expect: str | None,
                  timeout: float) -> CheckResult:
    resolver = dns.asyncresolver.Resolver(configure=False)
    resolver.nameservers = [server]
    resolver.port = port
    resolver.timeout = timeout
    resolver.lifetime = timeout
    start = time.perf_counter()
    try:
        answer = await resolver.resolve(qname, qtype)
    except dns.resolver.NXDOMAIN:
        return CheckResult(False, None, "NXDOMAIN (el nombre no existe)")
    except dns.resolver.NoAnswer:
        return CheckResult(False, None, "Sin respuesta para el tipo de registro pedido")
    except dns.exception.Timeout:
        return CheckResult(False, None, "Tiempo de espera agotado")
    except dns.resolver.NoNameservers:
        return CheckResult(False, None, "El servidor rechazó o no pudo resolver la consulta")
    except dns.exception.DNSException as e:
        return CheckResult(False, None, f"{type(e).__name__}"[:200])
    latency = (time.perf_counter() - start) * 1000
    answers = [r.to_text() for r in answer]
    if expect and not any(expect.lower() in a.lower() for a in answers):
        return CheckResult(False, latency, f"Respuesta inesperada: {', '.join(answers)}"[:200])
    return CheckResult(True, latency, None)
