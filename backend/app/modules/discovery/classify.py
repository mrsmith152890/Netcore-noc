_PREFIX = ".1.3.6.1.4.1."

# número de empresa (enterprises) -> (fabricante, tipo sugerido; None = deducir por sysDescr)
_ENTERPRISES: dict[int, tuple[str, str | None]] = {
    14988: ("MikroTik", "router"),
    12356: ("Fortinet", "firewall"),
    9: ("Cisco", None),
    41112: ("Ubiquiti", "ap"),
    11: ("HP", "switch"),
    14823: ("Aruba", "switch"),
    11863: ("TP-Link", "switch"),
    2636: ("Juniper", "router"),
    674: ("Dell", "server"),
    2011: ("Huawei", None),
    4526: ("Netgear", "switch"),
    311: ("Microsoft", "server"),
}

def _enterprise(oid: str | None) -> int | None:
    if not oid or not oid.startswith(_PREFIX):
        return None
    head = oid[len(_PREFIX):].split(".", 1)[0]
    return int(head) if head.isdigit() else None

def _type_from_descr(d: str) -> str:
    if "switch" in d:
        return "switch"
    if "router" in d:
        return "router"
    if "access point" in d or "wireless" in d:
        return "ap"
    if "firewall" in d:
        return "firewall"
    return "other"

def classify(sys_object_id: str | None, sys_descr: str | None) -> tuple[str | None, str]:
    """Devuelve (fabricante, tipo) sugeridos. Son solo una propuesta: el usuario las valida."""
    d = (sys_descr or "").lower()
    if "pfsense" in d:
        return "pfSense", "firewall"
    ent = _enterprise(sys_object_id)
    if ent == 8072:  # net-snmp: depende del sistema operativo
        if d.startswith("linux"):
            return "Linux", "server"
        if "freebsd" in d:
            return "FreeBSD", "server"
        return None, "server"
    vendor, dtype = _ENTERPRISES.get(ent, (None, None)) if ent is not None else (None, None)
    if vendor == "MikroTik":
        if " crs" in d:
            dtype = "switch"
        elif " cap" in d or " wap" in d:
            dtype = "ap"
    if dtype is None:
        dtype = _type_from_descr(d)
    return vendor, dtype
