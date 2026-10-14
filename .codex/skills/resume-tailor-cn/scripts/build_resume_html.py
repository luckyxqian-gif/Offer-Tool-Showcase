#!/usr/bin/env python3
"""Build one self-contained editable A4 HTML resume from resume-model-v1."""

from __future__ import annotations

import argparse
import base64
import html
import json
import mimetypes
import os
import re
import tempfile
from pathlib import Path
from typing import Any


SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE = SKILL_DIR / "assets" / "resume-v5-a4.html"
DEFAULT_PROFILE = SKILL_DIR / "assets" / "format-profile-v5-a4.json"
TOKENS = re.compile(
    r"__(?:DOCUMENT_TITLE|PROFILE_JSON|RESUME_CONTENT|OUTPUT_FILENAME)__"
)
DATA_IMAGE = re.compile(
    r"^data:image/(?:jpeg|png|webp);base64,[A-Za-z0-9+/=\s]+$",
    re.IGNORECASE,
)
MAX_PHOTO_BYTES = 5 * 1024 * 1024
SECTION_KEYS = ("education", "skills", "practice", "research")
CHANGE_ACTIONS = {"modify", "add", "delete", "merge", "move"}
SHA256 = re.compile(r"^[0-9a-f]{64}$")
CONTENT_ORIGINS = {"tailored", "direct-confirmed"}
TARGET_KINDS = {
    "single-jd": "jd-business-semantic-model",
    "target-family": "target-family-semantic-matrix",
    "generic-target-base": "generic-target-semantic-model",
}
RENDER_GATES = (
    "target_semantic",
    "retrieval",
    "architecture",
    "writing",
    "review",
)
DEFAULT_SECTION_TITLES = {
    "education": "教育背景",
    "skills": "奖项技能",
    "practice": "法律实践",
    "research": "科研成果",
}
CLAUSE_BREAKS = re.compile(r"[，；。！？\n]")
FORBIDDEN_EXPERIENCE_LABEL_CONNECTORS = ("与", "及", "或")
PENDING_CONFIRMATION_SOURCE = "pending-confirmation"
PENDING_CONFIRMATION_MARKER = "[待确认]"
INVALID_PUNCTUATION = re.compile(
    r"、{2,}|[，。；：！？]{2,}|"
    r"(?:^|[，；。！？\n])、|、(?:$|[，；。！？\n])"
)


class ModelError(ValueError):
    """Raised when the content model cannot safely produce a complete resume."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ModelError(f"无法读取 JSON：{path}: {error}") from error
    if not isinstance(value, dict):
        raise ModelError(f"JSON 顶层必须是对象：{path}")
    return value


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ModelError(f"{field} 不能为空")
    return value.strip()


def _optional_text(value: Any, field: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ModelError(f"{field} 必须是字符串")
    return value.strip()


def _list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ModelError(f"{field} 必须是数组")
    return value


def _safe_json(value: Any) -> str:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _nonempty_string_list(value: Any, field: str) -> list[str]:
    items = _list(value, field)
    normalized: list[str] = []
    for index, item in enumerate(items):
        normalized.append(_required_text(item, f"{field}[{index}]"))
    if len(normalized) != len(set(normalized)):
        raise ModelError(f"{field} 不能重复")
    return normalized


def _content_entries(model: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    entries_by_node: dict[str, Any] = {}
    bullets_by_node: dict[str, Any] = {}
    for section in ("practice", "research"):
        entries = _list(model.get(section), section)
        for entry_index, entry in enumerate(entries):
            entry_field = f"{section}[{entry_index}]"
            if not isinstance(entry, dict):
                raise ModelError(f"{entry_field} 必须是对象")
            entry_node = _optional_text(entry.get("node_id"), f"{entry_field}.node_id")
            if entry_node:
                if entry_node in entries_by_node:
                    raise ModelError(f"entry node_id 重复：{entry_node}")
                entries_by_node[entry_node] = entry
            bullets = _list(entry.get("bullets", []), f"{entry_field}.bullets")
            for bullet_index, bullet in enumerate(bullets):
                bullet_field = f"{entry_field}.bullets[{bullet_index}]"
                if not isinstance(bullet, dict):
                    raise ModelError(f"{bullet_field} 必须是对象")
                bullet_node = _optional_text(
                    bullet.get("node_id"), f"{bullet_field}.node_id"
                )
                if bullet_node:
                    if bullet_node in bullets_by_node:
                        raise ModelError(f"bullet node_id 重复：{bullet_node}")
                    bullets_by_node[bullet_node] = (entry_node, bullet)
    overlap = set(entries_by_node) & set(bullets_by_node)
    if overlap:
        raise ModelError(f"entry / bullet node_id 不能共用：{sorted(overlap)[0]}")
    return entries_by_node, bullets_by_node


def _plain_bullet_body(bullet: dict[str, Any], field: str) -> str:
    if "runs" not in bullet:
        return _optional_text(bullet.get("text"), f"{field}.text")
    runs = _list(bullet.get("runs"), f"{field}.runs")
    parts: list[str] = []
    for index, run in enumerate(runs):
        if not isinstance(run, dict):
            raise ModelError(f"{field}.runs[{index}] 必须是 run 对象")
        text = run.get("text")
        if not isinstance(text, str):
            raise ModelError(f"{field}.runs[{index}].text 必须是字符串")
        parts.append(text)
    return "".join(parts).strip()


def _validate_experience_label_boundary(bullet: dict[str, Any], field: str) -> None:
    raw_label = bullet.get("label")
    label = _optional_text(raw_label, f"{field}.label")
    if label:
        if raw_label != label:
            raise ModelError(f"{field}.label 不得含首尾空白")
        if not label.endswith("："):
            raise ModelError(f"{field}.label 必须以中文全角冒号‘：’结尾")

        if "runs" in bullet:
            runs = _list(bullet.get("runs"), f"{field}.runs")
            raw_body_parts: list[str] = []
            for index, run in enumerate(runs):
                if not isinstance(run, dict):
                    raise ModelError(f"{field}.runs[{index}] 必须是 run 对象")
                run_text = run.get("text")
                if not isinstance(run_text, str):
                    raise ModelError(f"{field}.runs[{index}].text 必须是字符串")
                raw_body_parts.append(run_text)
            raw_body = "".join(raw_body_parts)
        else:
            raw_body = bullet.get("text")
            if not isinstance(raw_body, str):
                raise ModelError(f"{field}.text 必须是字符串")
        if raw_body[:1].isspace():
            raise ModelError(f"{field} 的冒号与正文之间不得有空格")


def _validate_experience_bullet_mechanics(bullet: dict[str, Any], field: str) -> None:
    _validate_experience_label_boundary(bullet, field)
    label = _optional_text(bullet.get("label"), f"{field}.label")

    connector = next(
        (item for item in FORBIDDEN_EXPERIENCE_LABEL_CONNECTORS if item in label),
        None,
    )
    if connector:
        raise ModelError(f"{field}.label 不得含‘{connector}’")

    body = _plain_bullet_body(bullet, field)
    if any(clause.count("、") > 2 for clause in CLAUSE_BREAKS.split(body)):
        raise ModelError(f"{field}.text 同一分句不得出现超过 2 个顿号")


def _validate_all_experience_bullets(
    model: dict[str, Any], *, tailored_mechanics: bool
) -> None:
    for section in ("practice", "research"):
        entries = _list(model.get(section), section)
        for entry_index, entry in enumerate(entries):
            entry_field = f"{section}[{entry_index}]"
            if not isinstance(entry, dict):
                raise ModelError(f"{entry_field} 必须是对象")
            bullets = _list(entry.get("bullets", []), f"{entry_field}.bullets")
            for bullet_index, bullet in enumerate(bullets):
                bullet_field = f"{entry_field}.bullets[{bullet_index}]"
                if not isinstance(bullet, dict):
                    raise ModelError(f"{bullet_field} 必须是对象")
                if tailored_mechanics:
                    _validate_experience_bullet_mechanics(bullet, bullet_field)
                else:
                    _validate_experience_label_boundary(bullet, bullet_field)


def _visible_content_contains_pending_marker(model: dict[str, Any]) -> bool:
    """Check rendered content only; handoff metadata is intentionally excluded."""

    def contains(value: Any) -> bool:
        if isinstance(value, str):
            return PENDING_CONFIRMATION_MARKER in value
        if isinstance(value, list):
            return any(contains(item) for item in value)
        if isinstance(value, dict):
            return any(contains(item) for item in value.values())
        return False

    return any(
        contains(model.get(key))
        for key in (
            "personal",
            "education",
            "skills",
            "practice",
            "research",
            "self_summary",
            "section_titles",
            "section_plan",
        )
    )


def _visible_content_strings(model: dict[str, Any]) -> list[tuple[str, str]]:
    """Return rendered-content strings with deterministic model paths."""

    values: list[tuple[str, str]] = []

    def visit(value: Any, path: str) -> None:
        if isinstance(value, str):
            values.append((path, value))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, f"{path}[{index}]")
        elif isinstance(value, dict):
            for key, item in value.items():
                visit(item, f"{path}.{key}" if path else key)

    for key in (
        "personal",
        "education",
        "skills",
        "practice",
        "research",
        "self_summary",
        "section_titles",
        "section_plan",
    ):
        visit(model.get(key), key)
    return values


def _validate_deterministic_punctuation(model: dict[str, Any]) -> None:
    for field, value in _visible_content_strings(model):
        if INVALID_PUNCTUATION.search(value):
            raise ModelError(f"{field} 存在连续标点或空并列项")


def _global_constraints(handoff: dict[str, Any], *, required: bool) -> list[dict[str, Any]]:
    raw = handoff.get("global_content_constraints")
    if raw is None:
        if required:
            raise ModelError(
                "content_origin: tailored 必须携带 global_content_constraints（无记录时为空数组）"
            )
        return []
    constraints = _list(raw, "handoff.global_content_constraints")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, constraint in enumerate(constraints):
        field = f"handoff.global_content_constraints[{index}]"
        if not isinstance(constraint, dict):
            raise ModelError(f"{field} 必须是对象")
        constraint_id = _required_text(
            constraint.get("constraint_id"), f"{field}.constraint_id"
        )
        if constraint_id in seen:
            raise ModelError(f"全局删除约束 constraint_id 重复：{constraint_id}")
        seen.add(constraint_id)
        _required_text(constraint.get("subject"), f"{field}.subject")
        if constraint.get("decision_source") != "user-explicit":
            raise ModelError(f"{field}.decision_source 必须为 user-explicit")
        if constraint.get("scope") != "all-future-job-versions":
            raise ModelError(f"{field}.scope 必须为 all-future-job-versions")
        status = constraint.get("status")
        if status not in {"active", "restored"}:
            raise ModelError(f"{field}.status 必须为 active 或 restored")
        _required_text(constraint.get("source_ref"), f"{field}.source_ref")
        if status == "restored":
            if constraint.get("restored_by") != "user-explicit" or not isinstance(
                constraint.get("restoration_ref"), str
            ) or not constraint["restoration_ref"].strip():
                raise ModelError("恢复全局删除约束必须记录用户明确恢复")
        locator = constraint.get("mechanical_locator")
        if locator is not None:
            if not isinstance(locator, dict):
                raise ModelError(f"{field}.mechanical_locator 必须是对象")
            unknown = set(locator) - {"node_id", "forbidden_texts"}
            if unknown:
                raise ModelError(
                    f"{field}.mechanical_locator 包含未知字段：{sorted(unknown)[0]}"
                )
            node_id = locator.get("node_id")
            if node_id is not None:
                _required_text(node_id, f"{field}.mechanical_locator.node_id")
            forbidden = locator.get("forbidden_texts")
            if forbidden is not None:
                _nonempty_string_list(
                    forbidden, f"{field}.mechanical_locator.forbidden_texts"
                )
            if node_id is None and forbidden is None:
                raise ModelError(f"{field}.mechanical_locator 不得为空")
        normalized.append(constraint)
    return normalized


def _validate_global_content_constraints(
    model: dict[str, Any], handoff: dict[str, Any], *, required: bool
) -> None:
    constraints = _global_constraints(handoff, required=required)
    entries, bullets = _content_entries(model)
    present_nodes = set(entries) | set(bullets)
    visible = _visible_content_strings(model)
    for constraint in constraints:
        if constraint["status"] != "active":
            continue
        locator = constraint.get("mechanical_locator") or {}
        node_id = locator.get("node_id")
        if node_id and node_id in present_nodes:
            raise ModelError(
                f"全局删除约束 {constraint['constraint_id']} 检测到节点复活：{node_id}"
            )
        for forbidden in locator.get("forbidden_texts", []):
            if any(forbidden in value for _field, value in visible):
                raise ModelError(
                    f"全局删除约束 {constraint['constraint_id']} 检测到内容复活：{forbidden}"
                )


def _editable_content_nodes(model: dict[str, Any]) -> dict[str, Any]:
    """Return stable, mechanically comparable content nodes.

    This deliberately covers only fields that already have stable node IDs in the
    Resume Model contract. It is not a semantic facts diff or a second content
    model.
    """
    nodes: dict[str, Any] = {}

    def add_tree(value: Any, path: str) -> None:
        if isinstance(value, dict):
            nodes[f"{path}.__keys__"] = tuple(sorted(value))
            for key in sorted(value):
                add_tree(value[key], f"{path}.{key}")
        elif isinstance(value, list):
            nodes[f"{path}.__length__"] = len(value)
            for index, item in enumerate(value):
                add_tree(item, f"{path}[{index}]")
        else:
            nodes[path] = value

    for key in (
        "personal",
        "education",
        "skills",
        "self_summary",
        "section_order",
        "section_titles",
        "section_plan",
    ):
        if key in model:
            add_tree(model[key], key)
    for section in ("practice", "research"):
        entries = _list(model.get(section), section)
        nodes[f"{section}.__order__"] = tuple(
            entry.get("node_id") if isinstance(entry, dict) else None
            for entry in entries
        )
        for entry_index, entry in enumerate(entries):
            entry_field = f"{section}[{entry_index}]"
            if not isinstance(entry, dict):
                raise ModelError(f"{entry_field} 必须是对象")
            entry_node = _optional_text(entry.get("node_id"), f"{entry_field}.node_id")
            if not entry_node:
                add_tree(entry, f"{section}[{entry_index}]")
                continue
            for key in ("name", "field", "date"):
                nodes[f"{entry_node}.{key}"] = entry.get(key)
            bullets = _list(entry.get("bullets", []), f"{entry_field}.bullets")
            nodes[f"{entry_node}.bullets.__order__"] = tuple(
                bullet.get("node_id") if isinstance(bullet, dict) else None
                for bullet in bullets
            )
            for bullet_index, bullet in enumerate(bullets):
                bullet_field = f"{entry_field}.bullets[{bullet_index}]"
                if not isinstance(bullet, dict):
                    raise ModelError(f"{bullet_field} 必须是对象")
                bullet_node = _optional_text(
                    bullet.get("node_id"), f"{bullet_field}.node_id"
                )
                if bullet_node:
                    nodes[bullet_node] = {
                        key: bullet.get(key)
                        for key in ("label", "text", "runs")
                        if key in bullet
                    }
    return nodes


def _node_is_covered(node: str, declared_nodes: set[str]) -> bool:
    return any(node == declared or node.startswith(f"{declared}.") for declared in declared_nodes)


def _validate_change_set_against_baseline(
    model: dict[str, Any], baseline: dict[str, Any]
) -> None:
    handoff = model.get("handoff")
    if not isinstance(handoff, dict):
        raise ModelError("handoff 必须是已确认的交接对象")
    change_set = _list(handoff.get("change_set"), "handoff.change_set")
    changed_nodes = {
        _required_text(change.get("node"), f"handoff.change_set[{index}].node")
        for index, change in enumerate(change_set)
        if isinstance(change, dict)
    }
    locked_nodes = set(
        _nonempty_string_list(handoff.get("locked_nodes"), "handoff.locked_nodes")
    )

    baseline_handoff = baseline.get("handoff")
    if isinstance(baseline_handoff, dict):
        baseline_constraints = {
            item["constraint_id"]: item
            for item in _global_constraints(baseline_handoff, required=False)
        }
        current_constraints = {
            item["constraint_id"]: item
            for item in _global_constraints(handoff, required=False)
        }
        missing_constraints = set(baseline_constraints) - set(current_constraints)
        if missing_constraints:
            raise ModelError(
                "全局删除约束不得在后续版本中丢失："
                + sorted(missing_constraints)[0]
            )

    current_nodes = _editable_content_nodes(model)
    baseline_nodes = _editable_content_nodes(baseline)
    for node in sorted(set(current_nodes) | set(baseline_nodes)):
        if current_nodes.get(node) == baseline_nodes.get(node):
            continue
        if _node_is_covered(node, locked_nodes):
            raise ModelError(f"锁定节点不得漂移：{node}")
        if not _node_is_covered(node, changed_nodes):
            raise ModelError(f"节点发生变化但未进入 Change Set：{node}")


def _validate_tailoring_decisions(
    model: dict[str, Any], handoff: dict[str, Any], decisions: Any, *, stage: str
) -> None:
    if not isinstance(decisions, dict):
        raise ModelError("handoff.tailoring_decisions 必须是对象")

    task_mode = _required_text(
        decisions.get("task_mode"), "handoff.tailoring_decisions.task_mode"
    )
    if task_mode not in TARGET_KINDS:
        raise ModelError(
            "handoff.tailoring_decisions.task_mode 必须是 single-jd、target-family 或 generic-target-base"
        )
    target_input = decisions.get("target_semantic_input")
    if not isinstance(target_input, dict):
        raise ModelError("handoff.tailoring_decisions.target_semantic_input 必须是对象")
    target_kind = _required_text(
        target_input.get("kind"),
        "handoff.tailoring_decisions.target_semantic_input.kind",
    )
    if target_kind != TARGET_KINDS[task_mode]:
        raise ModelError("target_semantic_input.kind 必须与 task_mode 匹配")
    _required_text(
        target_input.get("summary"),
        "handoff.tailoring_decisions.target_semantic_input.summary",
    )

    gates = decisions.get("execution_gates")
    if not isinstance(gates, dict):
        raise ModelError("handoff.tailoring_decisions.execution_gates 必须是对象")
    missing_gates = set(RENDER_GATES) - set(gates)
    if missing_gates:
        raise ModelError(
            "execution_gates 缺少：" + "、".join(sorted(missing_gates))
        )
    for gate in RENDER_GATES:
        if gates.get(gate) != "PASS":
            raise ModelError(f"execution_gates.{gate} 必须为 PASS 才能渲染")

    change_set = _list(handoff.get("change_set"), "handoff.change_set")
    change_actions = {
        _required_text(change.get("node"), f"handoff.change_set[{index}].node"):
        _required_text(change.get("action"), f"handoff.change_set[{index}].action")
        for index, change in enumerate(change_set)
        if isinstance(change, dict)
    }

    decision_diff = decisions.get("decision_diff")
    if decision_diff is not None:
        for index, item in enumerate(
            _list(decision_diff, "handoff.tailoring_decisions.decision_diff")
        ):
            field = f"handoff.tailoring_decisions.decision_diff[{index}]"
            if not isinstance(item, dict):
                raise ModelError(f"{field} 必须是对象")
            _required_text(item.get("node"), f"{field}.node")
            _nonempty_string_list(item.get("changed_decisions"), f"{field}.changed_decisions")
            _required_text(item.get("reason"), f"{field}.reason")

    content_entries, content_bullets = _content_entries(model)
    decision_entries = _list(
        decisions.get("entries"), "handoff.tailoring_decisions.entries"
    )
    seen_entries: set[str] = set()
    seen_bullets: set[str] = set()
    for entry_index, entry_decision in enumerate(decision_entries):
        entry_field = f"handoff.tailoring_decisions.entries[{entry_index}]"
        if not isinstance(entry_decision, dict):
            raise ModelError(f"{entry_field} 必须是对象")
        entry_node = _required_text(
            entry_decision.get("entry_node"), f"{entry_field}.entry_node"
        )
        if entry_node in seen_entries:
            raise ModelError(f"tailoring_decisions entry_node 重复：{entry_node}")
        seen_entries.add(entry_node)
        final_entry = content_entries.get(entry_node)
        if final_entry is None:
            raise ModelError(f"entry decision 找不到对应最终内容节点：{entry_node}")
        _required_text(entry_decision.get("inclusion"), f"{entry_field}.inclusion")
        _required_text(entry_decision.get("priority"), f"{entry_field}.priority")
        _required_text(
            entry_decision.get("proving_task"), f"{entry_field}.proving_task"
        )
        if not isinstance(entry_decision.get("content_budget"), (str, dict)):
            raise ModelError(f"{entry_field}.content_budget 必须是非空文本或对象")
        if isinstance(entry_decision.get("content_budget"), str):
            _required_text(
                entry_decision.get("content_budget"), f"{entry_field}.content_budget"
            )
        elif not entry_decision["content_budget"]:
            raise ModelError(f"{entry_field}.content_budget 不能为空")

        field_intent = _optional_text(
            entry_decision.get("field_intent"), f"{entry_field}.field_intent"
        )
        final_field = _optional_text(
            final_entry.get("field"), f"content entry {entry_node}.field"
        )
        field_changed = change_actions.get(f"{entry_node}.field") in {"modify", "add"}
        entry_added = change_actions.get(entry_node) == "add"
        if (field_changed or (entry_added and final_field)) and not field_intent:
            raise ModelError(f"{entry_field}.field_intent 在新增或修改 field 时必填")

        bullet_decisions = _list(entry_decision.get("bullets"), f"{entry_field}.bullets")
        for bullet_index, bullet_decision in enumerate(bullet_decisions):
            bullet_field = f"{entry_field}.bullets[{bullet_index}]"
            if not isinstance(bullet_decision, dict):
                raise ModelError(f"{bullet_field} 必须是对象")
            bullet_node = _required_text(
                bullet_decision.get("bullet_node"), f"{bullet_field}.bullet_node"
            )
            if bullet_node in seen_bullets:
                raise ModelError(
                    f"tailoring_decisions bullet_node 重复：{bullet_node}"
                )
            if bullet_node in seen_entries:
                raise ModelError(f"entry / bullet node 不能共用：{bullet_node}")
            seen_bullets.add(bullet_node)
            final_bullet = content_bullets.get(bullet_node)
            if final_bullet is None or final_bullet[0] != entry_node:
                raise ModelError(
                    f"bullet decision 找不到同一 entry 下的最终内容节点：{bullet_node}"
                )
            _validate_experience_bullet_mechanics(
                final_bullet[1], f"content bullet {bullet_node}"
            )
            _required_text(
                bullet_decision.get("work_classification"),
                f"{bullet_field}.work_classification",
            )
            _required_text(
                bullet_decision.get("standalone_basis"),
                f"{bullet_field}.standalone_basis",
            )
            _required_text(
                bullet_decision.get("center_proposition"),
                f"{bullet_field}.center_proposition",
            )
            selected = _list(
                bullet_decision.get("selected_evidence"),
                f"{bullet_field}.selected_evidence",
            )
            if not selected:
                raise ModelError(f"{bullet_field}.selected_evidence 不能为空")
            evidence_keys: list[str] = []
            has_pending_evidence = False
            for evidence_index, evidence in enumerate(selected):
                evidence_field = (
                    f"{bullet_field}.selected_evidence[{evidence_index}]"
                )
                if not isinstance(evidence, dict):
                    raise ModelError(f"{evidence_field} 必须是对象")
                evidence_keys.append(
                    _required_text(
                        evidence.get("evidence_key"),
                        f"{evidence_field}.evidence_key",
                    )
                )
                source = _required_text(
                    evidence.get("source"), f"{evidence_field}.source"
                )
                if source == PENDING_CONFIRMATION_SOURCE:
                    has_pending_evidence = True
                section_path = _nonempty_string_list(
                    evidence.get("section_path"), f"{evidence_field}.section_path"
                )
                if not section_path:
                    raise ModelError(f"{evidence_field}.section_path 不能为空")
                _required_text(
                    evidence.get("item_anchor"), f"{evidence_field}.item_anchor"
                )
                _required_text(
                    evidence.get("fact_scope"), f"{evidence_field}.fact_scope"
                )
            if has_pending_evidence:
                final_wording = (
                    _optional_text(final_bullet[1].get("label"), f"{bullet_field}.label")
                    + _plain_bullet_body(final_bullet[1], bullet_field)
                )
                if stage == "render":
                    raise ModelError(
                        f"{bullet_field} 含待确认的新增客观事实不得进入正式渲染"
                    )
                if handoff.get("confirmation", {}).get("status") != "draft":
                    raise ModelError(
                        f"{bullet_field} 含待确认事实时 confirmation.status 必须为 draft"
                    )
                if PENDING_CONFIRMATION_MARKER not in final_wording:
                    raise ModelError(
                        f"{bullet_field} 的 pending-confirmation evidence 必须在对应正文标记[待确认]"
                    )
            if len(evidence_keys) != len(set(evidence_keys)):
                raise ModelError(f"{bullet_field}.selected_evidence evidence_key 不能重复")
            must_keep = _nonempty_string_list(
                bullet_decision.get("must_keep_evidence"),
                f"{bullet_field}.must_keep_evidence",
            )
            if not set(must_keep).issubset(evidence_keys):
                raise ModelError(
                    f"{bullet_field}.must_keep_evidence 必须属于 selected_evidence"
                )
            if not isinstance(bullet_decision.get("combination_allowed"), bool):
                raise ModelError(f"{bullet_field}.combination_allowed 必须是布尔值")



def _validate_handoff(model: dict[str, Any], *, stage: str = "render") -> None:
    if stage not in {"preview", "render"}:
        raise ModelError("validation stage 必须是 preview 或 render")
    handoff = model.get("handoff")
    if not isinstance(handoff, dict):
        raise ModelError("handoff 必须是已确认的交接对象")

    content_version = _required_text(
        handoff.get("content_version"), "handoff.content_version"
    )
    _required_text(handoff.get("base_path"), "handoff.base_path")
    base_sha256 = _required_text(handoff.get("base_sha256"), "handoff.base_sha256")
    if not SHA256.fullmatch(base_sha256):
        raise ModelError("handoff.base_sha256 必须是 64 位小写十六进制 SHA-256")

    change_set = _list(handoff.get("change_set"), "handoff.change_set")
    for index, change in enumerate(change_set):
        field = f"handoff.change_set[{index}]"
        if not isinstance(change, dict):
            raise ModelError(f"{field} 必须是对象")
        _required_text(change.get("node"), f"{field}.node")
        action = _required_text(change.get("action"), f"{field}.action")
        if action not in CHANGE_ACTIONS:
            raise ModelError(
                f"{field}.action 必须是 modify、add、delete、merge 或 move"
            )
        _required_text(change.get("reason"), f"{field}.reason")

    locked_nodes = _list(handoff.get("locked_nodes"), "handoff.locked_nodes")
    if not all(isinstance(node, str) and node.strip() for node in locked_nodes):
        raise ModelError("handoff.locked_nodes 只能包含非空节点路径字符串")
    if len(locked_nodes) != len(set(locked_nodes)):
        raise ModelError("handoff.locked_nodes 不能重复")

    confirmation = handoff.get("confirmation")
    if not isinstance(confirmation, dict):
        raise ModelError("handoff.confirmation 必须是用户确认对象")
    status = confirmation.get("status")
    allowed_statuses = {"draft", "confirmed"} if stage == "preview" else {"confirmed"}
    if status not in allowed_statuses:
        if stage == "preview":
            raise ModelError(
                "handoff.confirmation.status 必须是 draft 或 confirmed"
            )
        raise ModelError("handoff.confirmation.status 必须是 confirmed")
    confirmed_version = _required_text(
        confirmation.get("version"), "handoff.confirmation.version"
    )
    if confirmed_version != content_version:
        raise ModelError("handoff.confirmation.version 必须与 content_version 一致")
    _required_text(confirmation.get("source"), "handoff.confirmation.source")
    if status == "confirmed":
        if confirmation.get("confirmed_by") != "user-explicit":
            raise ModelError(
                "handoff.confirmation.confirmed_by 必须为 user-explicit"
            )
        _required_text(
            confirmation.get("source_ref"), "handoff.confirmation.source_ref"
        )
    if status == "confirmed" and confirmation.get("scope") != "complete-current-version":
        raise ModelError(
            "正式渲染必须记录 confirmation.scope: complete-current-version"
        )
    content_origin = _required_text(
        handoff.get("content_origin"), "handoff.content_origin"
    )
    if content_origin not in CONTENT_ORIGINS:
        raise ModelError("handoff.content_origin 必须是 tailored 或 direct-confirmed")
    _validate_deterministic_punctuation(model)
    _validate_global_content_constraints(
        model, handoff, required=content_origin == "tailored"
    )
    _validate_all_experience_bullets(
        model, tailored_mechanics=content_origin == "tailored"
    )
    decisions = handoff.get("tailoring_decisions")
    if content_origin == "tailored" and decisions is None:
        raise ModelError("content_origin: tailored 必须包含 tailoring_decisions")
    if decisions is not None:
        _validate_tailoring_decisions(model, handoff, decisions, stage=stage)
    if stage == "render" and _visible_content_contains_pending_marker(model):
        raise ModelError("正式渲染不得包含未解决的[待确认]标记")
def validate_resume_content(
    model: dict[str, Any], *, stage: str, baseline: dict[str, Any] | None = None
) -> dict[str, str]:
    """Run the shared deterministic content guard for preview or render.

    Semantic W1–W6 review remains with Tailor/Writing/Review. A successful return
    proves only that this function actually ran for the supplied content model.
    """
    if model.get("schema_version") != "resume-model-v1":
        raise ModelError("schema_version 必须是 resume-model-v1")
    _validate_handoff(model, stage=stage)
    if baseline is not None:
        _validate_change_set_against_baseline(model, baseline)
    handoff = model["handoff"]
    return {
        "status": "PASS",
        "stage": stage,
        "content_version": handoff["content_version"],
    }


def _inline(value: Any, *, default_bold: bool = False, field: str) -> str:
    runs: list[Any]
    if isinstance(value, str):
        runs = [{"text": value, "bold": default_bold}]
    elif isinstance(value, list):
        runs = value
    elif isinstance(value, dict) and isinstance(value.get("runs"), list):
        runs = value["runs"]
    else:
        raise ModelError(f"{field} 必须是字符串或 run 数组")

    rendered: list[str] = []
    for index, run in enumerate(runs):
        if not isinstance(run, dict):
            raise ModelError(f"{field}[{index}] 必须是 run 对象")
        text = run.get("text")
        if not isinstance(text, str):
            raise ModelError(f"{field}[{index}].text 必须是字符串")
        escaped = html.escape(text)
        if bool(run.get("bold", default_bold)):
            rendered.append(f"<strong>{escaped}</strong>")
        else:
            rendered.append(escaped)
    return "".join(rendered)


def _photo_data_url(personal: dict[str, Any], model_path: Path) -> str | None:
    data_url = personal.get("photo_data_url")
    if data_url:
        if not isinstance(data_url, str) or not DATA_IMAGE.fullmatch(data_url):
            raise ModelError("personal.photo_data_url 必须是 JPEG、PNG 或 WebP 的 base64 data URL")
        return "".join(data_url.split())

    raw_path = personal.get("photo_path")
    if not raw_path:
        return None
    if not isinstance(raw_path, str):
        raise ModelError("personal.photo_path 必须是路径字符串")
    photo_path = Path(raw_path).expanduser()
    if not photo_path.is_absolute():
        photo_path = (model_path.parent / photo_path).resolve()
    try:
        data = photo_path.read_bytes()
    except OSError as error:
        raise ModelError(f"无法读取照片：{photo_path}") from error
    if len(data) > MAX_PHOTO_BYTES:
        raise ModelError("照片超过 5 MB，未嵌入 HTML")
    mime = mimetypes.guess_type(photo_path.name)[0]
    if mime not in {"image/jpeg", "image/png", "image/webp"}:
        raise ModelError("照片必须是 JPEG、PNG 或 WebP")
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def _render_header(personal: dict[str, Any], model_path: Path) -> str:
    name = _required_text(personal.get("name"), "personal.name")
    lines = _list(personal.get("contact_lines", []), "personal.contact_lines")
    if len(lines) > 4:
        raise ModelError("personal.contact_lines 最多 4 行")
    photo = _photo_data_url(personal, model_path)
    if photo:
        photo_html = (
            '<img class="resume-photo" data-photo-present="true" '
            f'src="{html.escape(photo, quote=True)}" alt="职业照">'
        )
    else:
        photo_html = '<span class="resume-photo resume-photo-empty" data-photo-present="false"></span>'
    contacts = "".join(
        '<p class="contact-line" data-editable="true">'
        f'{html.escape(_optional_text(line, f"personal.contact_lines[{index}]"))}</p>'
        for index, line in enumerate(lines)
    )
    return (
        '<header class="resume-header">'
        f"{photo_html}"
        '<div class="identity-block">'
        f'<h1 class="resume-name" data-editable="true">{html.escape(name)}</h1>'
        f"{contacts}"
        "</div></header>"
    )


def _heading(title: str) -> str:
    return (
        '<div class="section-heading">'
        f'<h2 class="section-title">{html.escape(title)}</h2>'
        '<span class="section-rule" aria-hidden="true"></span>'
        "</div>"
    )


def _render_education(rows: list[Any]) -> str:
    rendered: list[str] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ModelError(f"education[{index}] 必须是对象")
        cells = (
            _inline(row.get("school", ""), default_bold=True, field=f"education[{index}].school"),
            _inline(row.get("program", ""), field=f"education[{index}].program"),
            _inline(row.get("rank", ""), field=f"education[{index}].rank"),
            _inline(row.get("date", ""), field=f"education[{index}].date"),
        )
        rendered.append(
            '<div class="education-row">'
            + "".join(
                f'<div class="education-cell education-cell-{cell_index + 1}" data-editable="true">{cell}</div>'
                for cell_index, cell in enumerate(cells)
            )
            + "</div>"
        )
    return '<div class="education-grid">' + "".join(rendered) + "</div>"


def _render_bullet(item: Any, field: str, owner: str) -> str:
    if not isinstance(item, dict):
        raise ModelError(f"{field} 必须是对象")
    label = _optional_text(item.get("label"), f"{field}.label")
    if "runs" in item:
        body = _inline(item["runs"], field=f"{field}.runs")
    else:
        body = html.escape(_optional_text(item.get("text"), f"{field}.text"))
    label_html = f"<strong>{html.escape(label)}</strong>" if label else ""
    node_id = _optional_text(item.get("node_id"), f"{field}.node_id")
    node_attr = (
        f' data-node-id="{html.escape(node_id, quote=True)}"' if node_id else ""
    )
    return (
        f'<li data-editable="true" data-owner="{html.escape(owner, quote=True)}"{node_attr}>'
        f"{label_html}{body}</li>"
    )


def _render_bullets(items: list[Any], field: str, owner: str) -> str:
    return (
        '<ul class="resume-bullets">'
        + "".join(
            _render_bullet(item, f"{field}[{index}]", owner)
            for index, item in enumerate(items)
        )
        + "</ul>"
    )


def _render_self_summary(value: str) -> str:
    if not value:
        return ""
    return (
        '<p class="self-summary" data-editable="true">'
        f'<strong>自我评价：</strong>{html.escape(value)}</p>'
    )


def _render_entries(items: list[Any], field: str) -> str:
    rendered: list[str] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ModelError(f"{field}[{index}] 必须是对象")
        name = _required_text(item.get("name"), f"{field}[{index}].name")
        middle = _optional_text(item.get("field"), f"{field}[{index}].field")
        date = _optional_text(item.get("date"), f"{field}[{index}].date")
        node_id = _optional_text(item.get("node_id"), f"{field}[{index}].node_id")
        node_attr = (
            f' data-node-id="{html.escape(node_id, quote=True)}"' if node_id else ""
        )
        bullets = _list(item.get("bullets", []), f"{field}[{index}].bullets")
        rendered.append(
            f'<article class="entry" data-source="{html.escape(field, quote=True)}" '
            f'data-entry-owner="{html.escape(name, quote=True)}"{node_attr}>'
            '<div class="entry-heading">'
            f'<div class="entry-name" data-editable="true">{html.escape(name)}</div>'
            f'<div class="entry-field" data-editable="true">{html.escape(middle)}</div>'
            f'<div class="entry-date" data-editable="true">{html.escape(date)}</div>'
            "</div>"
            f'{_render_bullets(bullets, f"{field}[{index}].bullets", name) if bullets else ""}'
            "</article>"
        )
    return "".join(rendered)


def _render_content(
    model: dict[str, Any],
    model_path: Path,
    *,
    baseline: dict[str, Any] | None = None,
) -> str:
    if model.get("schema_version") != "resume-model-v1":
        raise ModelError("schema_version 必须是 resume-model-v1")
    validate_resume_content(model, stage="render", baseline=baseline)
    personal = model.get("personal")
    if not isinstance(personal, dict):
        raise ModelError("personal 必须是对象")
    education = _list(model.get("education"), "education")
    skills = _list(model.get("skills"), "skills")
    practice = _list(model.get("practice"), "practice")
    research = _list(model.get("research"), "research")
    self_summary = _optional_text(model.get("self_summary"), "self_summary")
    order = model.get("section_order", list(SECTION_KEYS))
    if (
        not isinstance(order, list)
        or not all(isinstance(key, str) for key in order)
        or len(order) != len(SECTION_KEYS)
        or set(order) != set(SECTION_KEYS)
    ):
        raise ModelError("section_order 必须完整且不重复地包含 education、skills、practice、research")
    raw_titles = model.get("section_titles", {})
    if not isinstance(raw_titles, dict):
        raise ModelError("section_titles 必须是对象")
    unknown_titles = set(raw_titles) - set(SECTION_KEYS)
    if unknown_titles:
        raise ModelError(f"section_titles 包含未知栏目：{', '.join(sorted(unknown_titles))}")
    titles = {
        key: _required_text(raw_titles.get(key, DEFAULT_SECTION_TITLES[key]), f"section_titles.{key}")
        for key in SECTION_KEYS
    }
    bodies = {
        "education": _render_education(education),
        "skills": (
            _render_bullets(skills, "skills", titles["skills"])
            + _render_self_summary(self_summary)
        ),
        "practice": _render_entries(practice, "practice"),
        "research": _render_entries(research, "research"),
    }
    section_plan = model.get("section_plan")
    if section_plan is not None:
        if not isinstance(section_plan, list) or not section_plan:
            raise ModelError("section_plan 必须是非空数组")
        sources = {
            "education": education,
            "skills": skills,
            "practice": practice,
            "research": research,
        }
        seen = {key: set() for key in SECTION_KEYS}
        planned_sections: list[str] = []
        section_ids: set[str] = set()
        summary_rendered = False
        for section_index, section in enumerate(section_plan):
            field = f"section_plan[{section_index}]"
            if not isinstance(section, dict):
                raise ModelError(f"{field} 必须是对象")
            section_id = _required_text(section.get("id"), f"{field}.id")
            if section_id in section_ids:
                raise ModelError(f"{field}.id 不能重复")
            section_ids.add(section_id)
            title = _required_text(section.get("title"), f"{field}.title")
            blocks = _list(section.get("blocks"), f"{field}.blocks")
            if not blocks:
                raise ModelError(f"{field}.blocks 不能为空")
            rendered_blocks: list[str] = []
            for block_index, block in enumerate(blocks):
                block_field = f"{field}.blocks[{block_index}]"
                if not isinstance(block, dict):
                    raise ModelError(f"{block_field} 必须是对象")
                source = _required_text(block.get("source"), f"{block_field}.source")
                if source not in sources:
                    raise ModelError(f"{block_field}.source 必须是 education、skills、practice 或 research")
                indices = _list(block.get("indices"), f"{block_field}.indices")
                if not indices:
                    raise ModelError(f"{block_field}.indices 不能为空")
                if not all(isinstance(index, int) and not isinstance(index, bool) for index in indices):
                    raise ModelError(f"{block_field}.indices 只能包含整数")
                if len(indices) != len(set(indices)):
                    raise ModelError(f"{block_field}.indices 不能重复")
                if any(index < 0 or index >= len(sources[source]) for index in indices):
                    raise ModelError(f"{block_field}.indices 超出 {source} 范围")
                duplicate = seen[source].intersection(indices)
                if duplicate:
                    raise ModelError(f"{source} 条目不能在 section_plan 中重复使用：{sorted(duplicate)}")
                seen[source].update(indices)
                selected = [sources[source][index] for index in indices]
                if source == "education":
                    rendered_blocks.append(_render_education(selected))
                elif source == "skills":
                    rendered = _render_bullets(selected, "skills", title)
                    if self_summary and seen["skills"] == set(range(len(skills))):
                        rendered += _render_self_summary(self_summary)
                        summary_rendered = True
                    rendered_blocks.append(rendered)
                else:
                    rendered_blocks.append(_render_entries(selected, source))
            planned_sections.append(
                f'<section class="resume-section" data-section="{html.escape(section_id, quote=True)}">'
                f'{_heading(title)}{"".join(rendered_blocks)}</section>'
            )
        for source, items in sources.items():
            missing = set(range(len(items))) - seen[source]
            if missing:
                raise ModelError(f"section_plan 未使用 {source} 条目：{sorted(missing)}")
        if self_summary and not summary_rendered:
            raise ModelError("非空 self_summary 的 section_plan 必须包含 skills block")
        return _render_header(personal, model_path) + "".join(planned_sections)
    sections = "".join(
        f'<section class="resume-section" data-section="{key}">'
        f'{_heading(titles[key])}{bodies[key]}</section>'
        for key in order
    )
    return _render_header(personal, model_path) + sections


def build(
    model_path: Path,
    output_path: Path,
    profile_path: Path,
    template_path: Path,
    *,
    baseline_path: Path | None = None,
) -> None:
    model = _read_json(model_path)
    baseline = _read_json(baseline_path) if baseline_path is not None else None
    profile = _read_json(profile_path)
    if profile.get("profile_version") != "v5-a4-7":
        raise ModelError("Format Profile 必须是 v5-a4-7")
    try:
        template = template_path.read_text(encoding="utf-8")
    except OSError as error:
        raise ModelError(f"无法读取 HTML 母版：{template_path}") from error

    personal = model.get("personal") or {}
    name = _required_text(personal.get("name"), "personal.name")
    title = f"{name} 简历"
    replacements = {
        "__DOCUMENT_TITLE__": html.escape(title),
        "__PROFILE_JSON__": _safe_json(profile),
        "__RESUME_CONTENT__": _render_content(model, model_path, baseline=baseline),
        "__OUTPUT_FILENAME__": _safe_json(output_path.name),
    }
    found = set(TOKENS.findall(template))
    missing = set(replacements) - found
    if missing:
        raise ModelError(f"HTML 母版缺少占位符：{', '.join(sorted(missing))}")
    rendered = TOKENS.sub(lambda match: replacements[match.group(0)], template)
    if TOKENS.search(rendered):
        raise ModelError("HTML 母版仍有未替换占位符")

    output_path = output_path.expanduser().resolve()
    if output_path.suffix.lower() != ".html":
        raise ModelError("输出文件必须使用 .html 扩展名")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = handle.name
            handle.write(rendered)
        os.replace(temporary, output_path)
        temporary = None
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="resume-model-v1 JSON")
    parser.add_argument("--output", required=True, type=Path, help="single HTML output")
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument(
        "--baseline",
        type=Path,
        help="optional confirmed baseline model used for final scope diff",
    )
    args = parser.parse_args()
    try:
        build(
            args.input.expanduser().resolve(),
            args.output,
            args.profile,
            args.template,
            baseline_path=(
                args.baseline.expanduser().resolve() if args.baseline is not None else None
            ),
        )
    except ModelError as error:
        parser.error(str(error))
    print(args.output.expanduser().resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
