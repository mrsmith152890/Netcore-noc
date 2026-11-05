import ipaddress

from app.core.config import settings

class ScopeError(ValueError):
    pass

_THIS_NETWORK = ipaddress.ip_network("0.0.0.0/8")

def validate_cidr(cidr: str, allow_public: bool = False):
    """Valida que el rango sea escaneable. Se usa al registrarlo y otra vez antes de escanear."""
    try:
        net = ipaddress.ip_network(cidr.strip(), strict=True)
    except ValueError as e:
        raise ScopeError(f"CIDR inválido: {e}")
    if net.version != 4:
        raise ScopeError("Por ahora solo se admiten rangos IPv4")
    if net.subnet_of(_THIS_NETWORK) or any((net.network_address.is_multicast, net.network_address.is_loopback, net.network_address.is_link_local, net.network_address.is_reserved, net.network_address.is_unspecified)):
        raise ScopeError("Rango no permitido: solo redes privadas utilizables o unicast globales")
    if not net.is_private and not (allow_public or settings.discovery_allow_public):
        raise ScopeError("Este rango no es privado. Marca que es una red pública propia usada por VPN para autorizar este rango")
    if not net.is_private and (not net.is_global or net.network_address.is_multicast):
        raise ScopeError("Solo se admiten rangos IPv4 privados o públicos unicast globales")
    if net.num_addresses > settings.discovery_max_hosts:
        raise ScopeError(f"El rango tiene {net.num_addresses} direcciones; "
                         f"el máximo es {settings.discovery_max_hosts}")
    return net

def host_list(net) -> list[str]:
    if net.num_addresses <= 2:          # /32 y /31
        return [str(ip) for ip in net]
    return [str(ip) for ip in net.hosts()]
