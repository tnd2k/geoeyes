"""Create (or refresh) the reference output of a golden case with the current code.

    python -m tests.golden.make_golden capella_mexico_native [--force]      (from the repository root)

Writes ``$GEOEYES_TEST_DATA/golden/<case>/expected/`` plus ``case.json`` (the case it was made
from). Only refresh a golden deliberately: the point of it is to catch unintended changes.
"""
from __future__ import annotations

import argparse
import json
import shutil

from tests.golden.golden import data_root, expected_dir, load_case, run_case


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("case")
    ap.add_argument("--force", action="store_true", help="overwrite an existing reference")
    args = ap.parse_args(argv)

    if data_root() is None:
        ap.error("set GEOEYES_TEST_DATA to the golden data folder")
    case = load_case(args.case)
    out = expected_dir(args.case)
    if out.exists():
        if not args.force:
            ap.error(f"{out} exists; pass --force to overwrite")
        shutil.rmtree(out)
    out.mkdir(parents=True)
    run_case(case, out)
    if (out / "stack.zarr").exists():               # intermediate; only the engine output is the reference
        shutil.rmtree(out / "stack.zarr")
    (out.parent / "case.json").write_text(json.dumps(case, indent=2), encoding="utf-8")
    print(f"golden written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
