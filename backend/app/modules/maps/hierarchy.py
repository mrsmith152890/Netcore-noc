def descendants(edges: dict[int, set[int]], root: int) -> set[int]:
    """Todos los mapas alcanzables desde `root` a través de submapas."""
    seen: set[int] = set()
    stack = [root]
    while stack:
        cur = stack.pop()
        for child in edges.get(cur, ()):
            if child not in seen:
                seen.add(child)
                stack.append(child)
    return seen

def would_create_cycle(edges: dict[int, set[int]], parent: int, child: int) -> bool:
    """¿Agregar `child` como submapa de `parent` crearía un ciclo?"""
    return child == parent or parent in descendants(edges, child)
