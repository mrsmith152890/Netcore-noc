def apply_result(state: str, failures: int, success: bool, fail_threshold: int) -> tuple[str, int]:
    """Devuelve (nuevo_estado, nuevos_fallos_consecutivos).

    - Un éxito siempre deja el equipo en UP y reinicia el contador.
    - Un fallo solo cambia a DOWN al alcanzar el umbral; antes conserva el estado.
    """
    if success:
        return "UP", 0
    failures += 1
    if failures >= fail_threshold:
        return "DOWN", failures
    return state, failures
