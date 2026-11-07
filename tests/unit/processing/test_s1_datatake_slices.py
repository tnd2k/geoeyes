"""The bursts of one date can lie in two consecutive slices of a datatake (Choshui desc 105: 53 of 132 dates)."""
from geoeyes.processing.stack.native.s1_stack import datatake_slices

A = "S1A_IW_SLC__1SDV_20180301T215201_20180301T215231_020827_023B6A_FA9B"
B = "S1A_IW_SLC__1SDV_20180301T215229_20180301T215304_020827_023B6A_055F"
OTHER_DATE = "S1A_IW_SLC__1SDV_20180313T215201_20180313T215231_021002_024100_AAAA"
OTHER_TAKE = "S1B_IW_SLC__1SDV_20180301T215229_20180301T215304_009900_011111_BBBB"


def _mk(root, name, bursts=True):
    d = root / name
    d.mkdir()
    if bursts:
        (d / "bursts.json").write_text("[]", encoding="utf-8")
    return d


def test_same_datatake_slices_are_found(tmp_path):
    a = _mk(tmp_path, A)
    b = _mk(tmp_path, B)
    _mk(tmp_path, OTHER_DATE)
    _mk(tmp_path, OTHER_TAKE)
    assert datatake_slices(a) == [a, b]
    assert datatake_slices(b) == [b, a]


def test_lone_slice_and_unparsable_name(tmp_path):
    a = _mk(tmp_path, A)
    _mk(tmp_path, B, bursts=False)          # a slice without its burst list is not usable
    assert datatake_slices(a) == [a]
    odd = _mk(tmp_path, "20180301")
    assert datatake_slices(odd) == [odd]
