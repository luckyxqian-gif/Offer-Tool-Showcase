#!/usr/bin/env python3
"""Validate resume-model-v1 content before preview or render."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from build_resume_html import ModelError, _read_json, validate_resume_content


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="resume-model-v1 JSON")
    parser.add_argument("--stage", required=True, choices=("preview", "render"))
    parser.add_argument("--baseline", type=Path, help="optional baseline resume-model-v1 JSON")
    args = parser.parse_args()
    try:
        model = _read_json(args.input.expanduser().resolve())
        baseline = (
            _read_json(args.baseline.expanduser().resolve())
            if args.baseline is not None
            else None
        )
        result = validate_resume_content(model, stage=args.stage, baseline=baseline)
    except ModelError as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
