from __future__ import annotations

import argparse
import json
from pathlib import Path

from .project import plan_project
from .schema import canonical_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic talking-head semantic framing planner")
    parser.add_argument("input", type=Path, help="Frozen planner input JSON")
    parser.add_argument("output", type=Path, help="Canonical planner output JSON")
    args = parser.parse_args(argv)

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    result = plan_project(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(canonical_json(result) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
