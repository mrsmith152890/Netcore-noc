from datetime import datetime, timedelta

MIN_RANGE = timedelta(hours=1)
MAX_RANGE = timedelta(days=366)

def resolve_range(start: datetime | None, end: datetime | None, days: int | None, now: datetime):
    """Devuelve (inicio, fin) validados. Sin fechas: los últimos `days` días."""
    if start is None and end is None:
        end = now
        start = now - timedelta(days=days or 7)
    elif start is None or end is None:
        raise ValueError("Indica inicio y fin, o ninguno de los dos")
    if end > now:
        end = now
    if end - start < MIN_RANGE:
        raise ValueError("El periodo debe ser de al menos 1 hora")
    if end - start > MAX_RANGE:
        raise ValueError("El periodo máximo es de 366 días")
    return start, end

def availability_pct(samples: int, failed: int) -> float | None:
    if samples <= 0:
        return None
    return round((samples - failed) * 100 / samples, 3)

def coverage_pct(samples: int, seconds: float, interval_s: float) -> float:
    """Muestras reales frente a las esperadas; evita un 100 % falso si el monitoreo estuvo apagado."""
    expected = seconds / interval_s if interval_s > 0 else 0
    if expected <= 0:
        return 0.0
    return round(min(100.0, samples * 100 / expected), 1)
