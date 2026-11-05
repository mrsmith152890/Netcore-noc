from app.modules.maps.hierarchy import descendants, would_create_cycle

def test_self_reference_is_a_cycle():
    assert would_create_cycle({}, 1, 1)

def test_back_edge_and_transitive_cycle():
    assert would_create_cycle({1: {2}}, 2, 1)                 # 1 contiene a 2; 2 no puede contener a 1
    assert would_create_cycle({1: {2}, 2: {3}}, 3, 1)         # ciclo indirecto

def test_diamond_and_unrelated_are_not_cycles():
    assert not would_create_cycle({1: {2}, 2: {3}}, 1, 3)     # 1 puede contener también a 3
    assert not would_create_cycle({1: {2}}, 3, 4)

def test_descendants_are_transitive():
    assert descendants({1: {2, 3}, 2: {4}}, 1) == {2, 3, 4}
    assert descendants({1: {2}}, 5) == set()
