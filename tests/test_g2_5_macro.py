import numpy as np

from gates import g2_5_macro
from tests.conftest import _frame


def _rising():
    return _frame(50 + np.linspace(0, 10, 60))


def _falling():
    return _frame(60 - np.linspace(0, 10, 60))


def test_macro_tailwind_tech():
    # Tech: yields down, dollar down, semis up -> all tailwinds.
    macro = {"^TNX": _falling(), "DX-Y.NYB": _falling(), "^SOX": _rising()}
    res = g2_5_macro.check("X", {"sector": "Technology", "macro": macro})
    assert res.passed
    assert "tailwind" in res.reasoning
    assert res.score > 5


def test_macro_headwind_rejects_tech():
    # Tech: yields up, dollar up, semis down -> fighting 3 factors.
    macro = {"^TNX": _rising(), "DX-Y.NYB": _rising(), "^SOX": _falling()}
    res = g2_5_macro.check("X", {"sector": "Technology", "macro": macro})
    assert not res.passed


def test_macro_unknown_sector_neutral():
    res = g2_5_macro.check("X", {"sector": "Nonsense", "macro": {}})
    assert res.passed and res.score == 5.0
