#!/usr/bin/env python3
"""Validate that a local edit changed only explicitly allowed fixed-v5 DOM nodes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from extract_resume_html import ExtractionError, ScopeValidationError, compare_html_scope


def _read(path: Path) -> str:
    try:
        return path.expanduser().resolve().read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise ScopeValidationError(f"无法读取 HTML：{path}: {error}") from error


def _read_constraints(path: Path) -> list[dict]:
    try:
        value = json.loads(path.expanduser().resolve().read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ScopeValidationError(f"无法读取全局内容约束：{path}: {error}") from error
    if isinstance(value, dict):
        value = value.get("handoff", value).get("global_content_constraints")
    if not isinstance(value, list):
        raise ScopeValidationError("全局内容约束文件必须是数组或包含 handoff.global_content_constraints")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", required=True, type=Path, help="修改前的最新固定 v5 HTML")
    parser.add_argument("--after", required=True, type=Path, help="修改后的固定 v5 HTML")
    parser.add_argument(
        "--allow",
        action="append",
        required=True,
        help="允许改变的内容节点路径，可重复传入",
    )
    parser.add_argument(
        "--constraints",
        required=True,
        type=Path,
        help="当前 global_content_constraints JSON 快照；无记录时传入空数组文件",
    )
    args = parser.parse_args()
    try:
        result = compare_html_scope(
            _read(args.before),
            _read(args.after),
            allowed_nodes=set(args.allow),
            global_content_constraints=_read_constraints(args.constraints),
        )
    except (ExtractionError, ScopeValidationError) as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
