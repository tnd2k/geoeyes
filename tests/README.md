# tests/

| Folder | What | Data |
|---|---|---|
| `unit/` | fast tests of the package (config, controller, geometry, sensors, processing steps, products, export, catalog, web API) on synthetic data | none |
| `parity/` | the native PS engine against the legacy StaMPS outputs, step by step | `$GEOEYES_WORKSPACE/legacy` (skipped when absent) |
| `golden/` | end-to-end runs compared with stored references (`cases/*.json`): S1 Mexico (native stack + ps_lite), Capella Mexico (native stripmap + ps_lite), CSK Hanoi (the production chain through the controller: stack, phase linking, ps engine, product) | `$GEOEYES_TEST_DATA/golden/<case>/expected` (skipped when absent) |

```
pytest tests/unit -q                       # seconds, no data
pytest tests/parity -q                     # ~15 min, legacy outputs
pytest tests/golden -m golden -q           # tens of minutes, raw scenes + references
python -m tests.golden.make_golden <case> [--force]    # (re)create a reference, deliberately only
```

Golden comparisons match points on their stack position (line, sample), so a change may reorder points without
failing; tolerances are in the case file. TSX has no golden case yet (no data).
