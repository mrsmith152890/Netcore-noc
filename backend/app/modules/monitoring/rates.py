def counter_rate_bps(prev: int | None, cur: int | None, dt_s: float, bits: int = 64) -> float | None:
    """Tasa en bits/s entre dos lecturas de un contador de octetos.

    - Sin muestra previa o dt inválido -> None.
    - Contador de 32 bits que dio la vuelta -> se corrige sumando 2^32.
    - Contador de 64 bits que baja -> reinicio del equipo; se descarta la muestra.
    """
    if prev is None or cur is None or dt_s <= 0:
        return None
    delta = cur - prev
    if delta < 0:
        if bits == 32:
            delta += 2**32
        else:
            return None
    return delta * 8 / dt_s
