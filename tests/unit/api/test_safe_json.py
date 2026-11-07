"""A non-finite number in a served file (stack qc.json: amplitude_corr NaN) must not fail the request."""
import math

from geoeyes.api.app import SafeJSONResponse, _finite


def test_non_finite_numbers_become_null():
    content = {"a": math.nan, "b": [1.0, math.inf, {"c": -math.inf}], "d": "x", "e": 2}
    assert _finite(content) == {"a": None, "b": [1.0, None, {"c": None}], "d": "x", "e": 2}
    body = SafeJSONResponse(content).body
    assert body == b'{"a":null,"b":[1.0,null,{"c":null}],"d":"x","e":2}'
