import jesse.math_utils as mu


def test_igcdex():
    assert mu.igcdex(2, 3) == (-1, 1, 1)
    assert mu.igcdex(10, 12) == (-1, 1, 2)
