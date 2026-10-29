import pytest

from quanttool.data.utilities.registry import Registry


def test_register_and_lookup():
    reg = Registry("test")

    @reg.register("A")
    class A:
        pass

    assert reg["A"] is A
    assert "A" in reg and reg.keys() == ["A"]
    with pytest.raises(KeyError, match="A"):
        reg.register("A")(object)
    with pytest.raises(KeyError, match="등록된 키"):
        reg["B"]
