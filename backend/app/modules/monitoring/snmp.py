import asyncio
import re
from dataclasses import dataclass

from app.core.config import settings

class SnmpError(Exception):
    pass

_SYS = {
    "name": ".1.3.6.1.2.1.1.5.0",
    "descr": ".1.3.6.1.2.1.1.1.0",
    "object_id": ".1.3.6.1.2.1.1.2.0",
    "uptime": ".1.3.6.1.2.1.1.3.0",
}
_IF_TABLE = ".1.3.6.1.2.1.2.2.1"        # ifDescr(2) ifSpeed(5) ifAdmin(7) ifOper(8) ifInOctets(10) ifOutOctets(16)
_IFX_TABLE = ".1.3.6.1.2.1.31.1.1.1"    # ifName(1) ifHCIn(6) ifHCOut(10) ifHighSpeed(15)

IF_STATUS = {1: "up", 2: "down", 3: "testing", 4: "unknown", 5: "dormant",
             6: "notPresent", 7: "lowerLayerDown"}

_ENTRY = re.compile(r"^(\.\d+(?:\.\d+)*) ?(.*)$")
_ENUM = re.compile(r"\((-?\d+)\)")

def _int(v: str | None) -> int | None:
    if v is None:
        return None
    v = v.strip()
    try:
        return int(v)
    except ValueError:
        m = _ENUM.search(v)
        return int(m.group(1)) if m else None

def _clean(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
        v = v[1:-1]
    return v

def _parse(out: str) -> dict[str, str]:
    res: dict[str, str] = {}
    last = None
    for line in out.splitlines():
        m = _ENTRY.match(line)
        if m:
            last = m.group(1)
            res[last] = m.group(2)
        elif last is not None and line.strip():
            res[last] += " " + line.strip()   # valor de varias líneas (p. ej. sysDescr de Cisco)
    return {k: _clean(v) for k, v in res.items()
            if not v.startswith(("No Such", "No more"))}

def _target(host: str, port: int) -> str:
    return f"udp6:[{host}]:{port}" if ":" in host else f"{host}:{port}"

async def _run(cmd: str, host: str, port: int, community: str, oids: list[str],
               extra: list[str] | None = None, timeout: float | None = None) -> dict[str, str]:
    args = [cmd, "-v2c", "-c", community,
            "-t", str(settings.snmp_timeout_s), "-r", str(settings.snmp_retries),
            "-Onqte", *(extra or []), _target(host, port), *oids]
    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    limit = timeout or (settings.snmp_timeout_s * (settings.snmp_retries + 1) + 3)
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=limit)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise SnmpError("Tiempo de espera agotado")
    if proc.returncode != 0:
        msg = (err.decode(errors="replace") or out.decode(errors="replace")).strip()
        raise SnmpError(msg.splitlines()[0] if msg else f"{cmd} terminó con código {proc.returncode}")
    return _parse(out.decode(errors="replace"))

async def snmp_get(host, port, community, oids):
    return await _run("snmpget", host, port, community, oids)

async def snmp_walk(host, port, community, oid):
    return await _run("snmpbulkwalk", host, port, community, [oid],
                      extra=["-Cr25"], timeout=settings.snmp_walk_timeout_s)

async def get_identity(host: str, port: int, community: str) -> dict:
    data = await snmp_get(host, port, community, list(_SYS.values()))
    ticks = _int(data.get(_SYS["uptime"]))
    return {
        "sys_name": data.get(_SYS["name"]),
        "sys_descr": data.get(_SYS["descr"]),
        "sys_object_id": data.get(_SYS["object_id"]),
        "uptime_s": ticks // 100 if ticks is not None else None,
    }

@dataclass
class InterfaceData:
    if_index: int
    name: str | None
    descr: str | None
    speed_bps: int | None
    admin_status: str | None
    oper_status: str | None
    in_octets: int | None
    out_octets: int | None
    counter_bits: int

def _by_index(data: dict[str, str], base: str) -> dict[int, dict[int, str]]:
    prefix = base + "."
    out: dict[int, dict[int, str]] = {}
    for oid, val in data.items():
        if not oid.startswith(prefix):
            continue
        col, _, idx = oid[len(prefix):].partition(".")
        if col.isdigit() and idx.isdigit():
            out.setdefault(int(idx), {})[int(col)] = val
    return out

async def get_interfaces(host: str, port: int, community: str) -> list[InterfaceData]:
    t1, t2 = await asyncio.gather(
        snmp_walk(host, port, community, _IF_TABLE),
        snmp_walk(host, port, community, _IFX_TABLE),
    )
    a, b = _by_index(t1, _IF_TABLE), _by_index(t2, _IFX_TABLE)
    result = []
    for idx in sorted(set(a) | set(b)):
        x, y = a.get(idx, {}), b.get(idx, {})
        hc_in, hc_out = _int(y.get(6)), _int(y.get(10))
        bits = 64 if hc_in is not None else 32
        in_oct = hc_in if bits == 64 else _int(x.get(10))
        out_oct = hc_out if bits == 64 else _int(x.get(16))
        high = _int(y.get(15))
        speed = high * 1_000_000 if high else _int(x.get(5))
        result.append(InterfaceData(
            if_index=idx, name=y.get(1) or x.get(2), descr=x.get(2), speed_bps=speed,
            admin_status=IF_STATUS.get(_int(x.get(7))), oper_status=IF_STATUS.get(_int(x.get(8))),
            in_octets=in_oct, out_octets=out_oct, counter_bits=bits,
        ))
    return result

_HR_CPU = ".1.3.6.1.2.1.25.3.3.1.2"              # hrProcessorLoad (% por núcleo)
_HR_STORAGE = ".1.3.6.1.2.1.25.2.3.1"            # type(2) descr(3) allocUnits(4) size(5) used(6)
_HR_STORAGE_RAM = ".1.3.6.1.2.1.25.2.1.2"        # hrStorageRam

@dataclass
class ResourceData:
    cpu_pct: float | None
    mem_total: int | None
    mem_used: int | None
    mem_pct: float | None

async def get_resources(host: str, port: int, community: str) -> ResourceData | None:
    cpu_t, st_t = await asyncio.gather(
        snmp_walk(host, port, community, _HR_CPU),
        snmp_walk(host, port, community, _HR_STORAGE),
    )
    loads = [v for v in (_int(x) for x in cpu_t.values()) if v is not None]
    cpu = round(sum(loads) / len(loads), 1) if loads else None

    mem_total = mem_used = mem_pct = None
    for row in _by_index(st_t, _HR_STORAGE).values():
        if row.get(2) != _HR_STORAGE_RAM:
            continue
        unit, size, used = _int(row.get(4)), _int(row.get(5)), _int(row.get(6))
        if not unit or not size or used is None:
            continue
        mem_total, mem_used = size * unit, used * unit
        mem_pct = round(used * 100 / size, 1)
        break

    if cpu is None and mem_total is None:
        return None
    return ResourceData(cpu, mem_total, mem_used, mem_pct)
