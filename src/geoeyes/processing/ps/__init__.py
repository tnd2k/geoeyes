"""StaMPS-type persistent-scatterer engine (S1, CSK, TSX, ALOS), ported step by step from the legacy
``python/*/stamps/flow.py``. Each step is a pure function in ``steps/``; parity with the legacy engine is
checked per step against its intermediate outputs (``tests/parity``).

Steps: 1 ``load`` · 2 ``est_gamma`` · 3 ``select`` · 4 ``weed`` · 5 ``correct_phase`` · 6 ``unwrap`` ·
7 ``scla`` · 8 ``scn_filt``.
"""
