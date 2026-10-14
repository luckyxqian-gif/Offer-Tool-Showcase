#!/usr/bin/env python3
"""Recover ``resume-model-v1`` from the project's fixed v5 resume HTML.

This is deliberately a renderer-specific extractor, not a general HTML
parser.  It accepts the DOM emitted by ``build_resume_html.py`` and the small
inline edits supported by the v5 editor (text, ``strong``/``b`` and simple
``span`` bold formatting).  Unknown structural markup fails closed so that a
hand-written or unrelated HTML document is not silently mistaken for a
complete resume model.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable


SECTION_KEYS = ("education", "skills", "practice", "research")
DATA_IMAGE = re.compile(
    r"^data:image/(?:jpeg|png|webp);base64,[A-Za-z0-9+/=\s]+$",
    re.IGNORECASE,
)
MAX_LABEL_LENGTH = 30
VOID_ELEMENTS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


class ExtractionError(ValueError):
    """Raised when an HTML file cannot be safely mapped to resume-model-v1."""


class ScopeValidationError(ValueError):
    """Raised when a local HTML edit changes a DOM node outside its allow-list."""


@dataclass
class _Text:
    value: str


@dataclass
class _Element:
    tag: str
    attrs: dict[str, str]
    children: list["_Node"] = field(default_factory=list)


_Node = _Element | _Text


class _V5HtmlParser(HTMLParser):
    """Small tree builder for the tags used by the v5 renderer.

    It intentionally does not implement HTML recovery rules.  The generated
    renderer emits well-formed markup, so accepting mismatched tags would make
    it too easy to lose a user's edit without noticing.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Element("#document", {})
        self._stack: list[_Element] = [self.root]

    @property
    def current(self) -> _Element:
        return self._stack[-1]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        element = _Element(
            tag.lower(),
            {name.lower(): (value or "") for name, value in attrs},
        )
        self.current.children.append(element)
        if element.tag not in VOID_ELEMENTS:
            self._stack.append(element)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.current.children.append(
            _Element(
                tag.lower(),
                {name.lower(): (value or "") for name, value in attrs},
            )
        )

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        if normalized in VOID_ELEMENTS:
            raise ExtractionError(f"v5 HTML 出现不应闭合的标签：{tag}")
        if len(self._stack) == 1 or self._stack[-1].tag != normalized:
            actual = self._stack[-1].tag if len(self._stack) > 1 else "文档根"
            raise ExtractionError(f"HTML 标签不匹配：期望关闭 {actual}，实际为 {tag}")
        self._stack.pop()

    def handle_data(self, data: str) -> None:
        if data:
            self.current.children.append(_Text(data))

    def close(self) -> None:
        super().close()
        if len(self._stack) != 1:
            raise ExtractionError(f"HTML 存在未闭合标签：{self._stack[-1].tag}")


def _parse_document(source: str) -> _Element:
    parser = _V5HtmlParser()
    try:
        parser.feed(source)
        parser.close()
    except ExtractionError:
        raise
    except Exception as error:  # HTMLParser may expose implementation errors.
        raise ExtractionError(f"无法解析 v5 HTML：{error}") from error
    return parser.root


def _classes(node: _Node) -> set[str]:
    if not isinstance(node, _Element):
        return set()
    return {item for item in node.attrs.get("class", "").split() if item}


def _has_class(node: _Node, name: str) -> bool:
    return name in _classes(node)


def _descendants(node: _Element, tag: str | None = None) -> Iterable[_Element]:
    for child in node.children:
        if not isinstance(child, _Element):
            continue
        if tag is None or child.tag == tag:
            yield child
        yield from _descendants(child, tag)


def _significant_children(node: _Element) -> list[_Element]:
    """Return element children and reject non-whitespace structural text."""

    result: list[_Element] = []
    for child in node.children:
        if isinstance(child, _Text):
            if child.value.strip():
                raise ExtractionError(
                    f"v5 结构节点 {node.tag} 含有未预期的正文文本：{child.value[:30]!r}"
                )
            continue
        result.append(child)
    return result


def _append_run(runs: list[dict[str, Any]], text: str, bold: bool) -> None:
    if not text:
        return
    if runs and bool(runs[-1]["bold"]) == bold:
        runs[-1]["text"] += text
    else:
        runs.append({"text": text, "bold": bold})


def _trim_runs(runs: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    result = [
        {"text": str(run.get("text", "")), "bold": bool(run.get("bold", False))}
        for run in runs
        if str(run.get("text", ""))
    ]
    if result:
        result[0]["text"] = result[0]["text"].lstrip()
        result[-1]["text"] = result[-1]["text"].rstrip()
    return [run for run in result if run["text"]]


def _split_runs_at(
    runs: Iterable[dict[str, Any]], position: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    left: list[dict[str, Any]] = []
    right: list[dict[str, Any]] = []
    remaining = max(0, position)
    for run in runs:
        text = str(run.get("text", ""))
        bold = bool(run.get("bold", False))
        if remaining >= len(text):
            _append_run(left, text, bold)
            remaining -= len(text)
            continue
        if remaining:
            _append_run(left, text[:remaining], bold)
            _append_run(right, text[remaining:], bold)
            remaining = 0
        else:
            _append_run(right, text, bold)
    return left, right


def _runs_text(runs: Iterable[dict[str, Any]]) -> str:
    return "".join(str(run.get("text", "")) for run in runs)


def _style_is_bold(node: _Element) -> bool:
    style = re.sub(r"\s+", "", node.attrs.get("style", "").lower())
    if re.search(r"(?:^|;)font-weight:(?:bold|[6-9]00)(?:;|$)", style):
        return True
    classes = _classes(node)
    return bool(classes.intersection({"bold", "font-bold"}))


def _inline_runs(node: _Element, *, field: str, inherited_bold: bool = False) -> list[dict[str, Any]]:
    """Read allowed inline formatting while preserving the bold runs."""

    result: list[dict[str, Any]] = []

    def visit(current: _Node, bold: bool) -> None:
        if isinstance(current, _Text):
            _append_run(result, current.value, bold)
            return

        tag = current.tag
        if tag in {"strong", "b"}:
            for child in current.children:
                visit(child, True)
            return
        if tag == "span":
            next_bold = bold or _style_is_bold(current)
            for child in current.children:
                visit(child, next_bold)
            return
        if tag == "br":
            _append_run(result, "\n", bold)
            return
        if tag in {"div", "p"}:
            # Browsers may insert div/p wrappers after a contenteditable paste
            # or Enter.  They are accepted only inside a text-bearing node and
            # represented as line breaks, not treated as arbitrary HTML.
            if result and not result[-1]["text"].endswith("\n"):
                _append_run(result, "\n", False)
            for child in current.children:
                visit(child, bold)
            if result and not result[-1]["text"].endswith("\n"):
                _append_run(result, "\n", False)
            return
        raise ExtractionError(f"{field} 含有未支持的内联标签：<{tag}>")

    for child in node.children:
        visit(child, inherited_bold)
    return _trim_runs(result)


def _plain_field(runs: Iterable[dict[str, Any]]) -> str:
    return _runs_text(runs).strip()


def _field_text(node: _Element, field: str, *, required: bool = False) -> str:
    value = _plain_field(_inline_runs(node, field=field))
    if required and not value:
        raise ExtractionError(f"{field} 不能为空")
    return value


def _runs_or_text(runs: list[dict[str, Any]]) -> str | list[dict[str, Any]]:
    # Strings keep the normal model compact.  A run array is needed only when
    # the user made an explicit inline formatting choice that must survive a
    # future rebuild.
    if any(bool(run.get("bold")) for run in runs):
        return runs
    return _plain_field(runs)


def _strip_literal_bullet(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    text = _runs_text(runs)
    position = len(text) - len(text.lstrip())
    if position < len(text) and text[position] == "•":
        left, right = _split_runs_at(runs, position + 1)
        del left
        return _trim_runs(right)
    return runs


def _split_label(runs: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    runs = _trim_runs(runs)
    if not runs or not bool(runs[0].get("bold")):
        return "", runs

    text = _runs_text(runs)
    colon_positions = [position for position in (text.find("："), text.find(":")) if position >= 0]
    if colon_positions:
        position = min(colon_positions) + 1
        label_runs, body_runs = _split_runs_at(runs, position)
        return _plain_field(label_runs), _trim_runs(body_runs)

    first_bold_length = 0
    for run in runs:
        if not bool(run.get("bold")):
            break
        first_bold_length += len(str(run.get("text", "")))
    if 0 < first_bold_length <= MAX_LABEL_LENGTH and first_bold_length < len(text):
        label_runs, body_runs = _split_runs_at(runs, first_bold_length)
        body_runs = _trim_runs(body_runs)
        if body_runs:
            return _plain_field(label_runs), body_runs
    return "", runs


def _bullet_item(node: _Element, field: str) -> dict[str, Any]:
    if node.tag != "li":
        raise ExtractionError(f"{field} 不是 li")
    runs = _strip_literal_bullet(_trim_runs(_inline_runs(node, field=field)))
    label, body_runs = _split_label(runs)
    item: dict[str, Any] = {"label": label, "text": _plain_field(body_runs)}
    node_id = node.attrs.get("data-node-id", "").strip()
    if node_id:
        item["node_id"] = node_id
    if any(bool(run.get("bold")) for run in body_runs):
        item["runs"] = body_runs
    return item


def _bullet_list(node: _Element, field: str) -> list[dict[str, Any]]:
    if node.tag != "ul" or not _has_class(node, "resume-bullets"):
        raise ExtractionError(f"{field} 不是 v5 resume-bullets 列表")
    children = _significant_children(node)
    if any(child.tag != "li" for child in children):
        raise ExtractionError(f"{field} 只能包含 li")
    return [_bullet_item(child, f"{field}[{index}]") for index, child in enumerate(children)]


def _inline_self_summary(node: _Element) -> str:
    if node.tag != "p" or not _has_class(node, "self-summary"):
        raise ExtractionError("自我评价不是受支持的内联 self-summary")
    runs = _trim_runs(_inline_runs(node, field="self_summary"))
    label, body_runs = _split_label(runs)
    if label not in {"自我评价：", "自我评价:"}:
        raise ExtractionError("奖项与技能下的自我评价必须使用“自我评价：”标签")
    return _plain_field(_trim_runs(body_runs))


def _education_grid(node: _Element) -> list[dict[str, Any]]:
    if node.tag != "div" or not _has_class(node, "education-grid"):
        raise ExtractionError("不是 v5 education-grid")
    rows: list[dict[str, Any]] = []
    for row_index, row in enumerate(_significant_children(node)):
        if row.tag != "div" or not _has_class(row, "education-row"):
            raise ExtractionError(f"教育背景第 {row_index + 1} 行不是 education-row")
        cells = _significant_children(row)
        if len(cells) != 4 or any(
            cell.tag != "div" or not _has_class(cell, f"education-cell-{index + 1}")
            for index, cell in enumerate(cells)
        ):
            raise ExtractionError(f"教育背景第 {row_index + 1} 行不是固定四列")
        names = ("school", "program", "rank", "date")
        rows.append(
            {
                name: _runs_or_text(
                    _inline_runs(cell, field=f"education[{row_index}].{name}")
                )
                for name, cell in zip(names, cells)
            }
        )
    return rows


def _entry(node: _Element, fallback_source: str, entry_index: int) -> tuple[str, dict[str, Any]]:
    if node.tag != "article" or not _has_class(node, "entry"):
        raise ExtractionError("不是 v5 entry")
    source = node.attrs.get("data-source", "").strip().lower() or fallback_source
    if source not in {"practice", "research"}:
        raise ExtractionError(
            f"第 {entry_index + 1} 个经历条目的 data-source 无法识别：{source!r}"
        )

    children = _significant_children(node)
    headings = [child for child in children if _has_class(child, "entry-heading")]
    if len(headings) != 1 or children[0] is not headings[0]:
        raise ExtractionError(f"{source}[{entry_index}] 缺少唯一的 entry-heading")
    heading_children = _significant_children(headings[0])
    fields: dict[str, _Element] = {}
    for name in ("entry-name", "entry-field", "entry-date"):
        matches = [child for child in heading_children if _has_class(child, name)]
        if len(matches) != 1:
            raise ExtractionError(f"{source}[{entry_index}] 缺少唯一的 {name}")
        fields[name] = matches[0]
    if any(child not in fields.values() for child in heading_children):
        raise ExtractionError(f"{source}[{entry_index}] 的 entry-heading 出现未支持节点")

    bullets: list[dict[str, Any]] = []
    for child in children[1:]:
        if child.tag != "ul" or not _has_class(child, "resume-bullets"):
            raise ExtractionError(f"{source}[{entry_index}] 出现未支持的正文节点：<{child.tag}>")
        if bullets:
            raise ExtractionError(f"{source}[{entry_index}] 出现重复的 bullet 列表")
        bullets = _bullet_list(child, f"{source}[{entry_index}].bullets")

    item = {
        "name": _field_text(fields["entry-name"], f"{source}[{entry_index}].name", required=True),
        "field": _field_text(fields["entry-field"], f"{source}[{entry_index}].field"),
        "date": _field_text(fields["entry-date"], f"{source}[{entry_index}].date"),
        "bullets": bullets,
    }
    node_id = node.attrs.get("data-node-id", "").strip()
    if node_id:
        item["node_id"] = node_id
    return source, item


def _photo(main_header: _Element) -> str | None:
    photos = [child for child in _significant_children(main_header) if _has_class(child, "resume-photo")]
    if len(photos) != 1:
        raise ExtractionError("页眉缺少唯一的 resume-photo")
    photo = photos[0]
    present = photo.attrs.get("data-photo-present", "").lower() == "true"
    if not present or _has_class(photo, "resume-photo-empty"):
        return None
    if photo.tag != "img":
        raise ExtractionError("有照片时 resume-photo 必须是 img")
    source = "".join(photo.attrs.get("src", "").split())
    if not DATA_IMAGE.fullmatch(source):
        raise ExtractionError("照片不是受支持的 JPEG、PNG 或 WebP data URL")
    return source


def _header(main: _Element) -> dict[str, Any]:
    headers = [child for child in _significant_children(main) if _has_class(child, "resume-header")]
    if len(headers) != 1:
        raise ExtractionError("resume-sheet 缺少唯一页眉")
    header = headers[0]
    header_children = _significant_children(header)
    identity = [child for child in header_children if _has_class(child, "identity-block")]
    if len(identity) != 1:
        raise ExtractionError("页眉缺少唯一 identity-block")
    photos = [child for child in header_children if _has_class(child, "resume-photo")]
    if len(photos) != 1 or any(
        child is not photos[0] and child is not identity[0] for child in header_children
    ):
        raise ExtractionError("页眉的照片/身份区结构不符合 v5")
    identity_children = _significant_children(identity[0])
    names = [child for child in identity_children if _has_class(child, "resume-name")]
    if len(names) != 1:
        raise ExtractionError("页眉缺少唯一 resume-name")
    contact_nodes = [child for child in identity_children if _has_class(child, "contact-line")]
    if len(contact_nodes) > 4:
        raise ExtractionError("联系方式超过 4 行，未擅自合并")
    unexpected = [
        child
        for child in identity_children
        if child is not names[0] and child not in contact_nodes
    ]
    if unexpected:
        raise ExtractionError(f"页眉身份区出现未支持节点：<{unexpected[0].tag}>")
    result: dict[str, Any] = {
        "name": _field_text(names[0], "personal.name", required=True),
        "contact_lines": [
            _field_text(node, f"personal.contact_lines[{index}]")
            for index, node in enumerate(contact_nodes)
        ],
    }
    photo = _photo(header)
    if photo:
        result["photo_data_url"] = photo
    return result


def _section(node: _Element, section_index: int) -> tuple[str, str, list[tuple[str, list[Any]]]]:
    if node.tag != "section" or not _has_class(node, "resume-section"):
        raise ExtractionError(f"第 {section_index + 1} 个栏目不是 resume-section")
    section_id = node.attrs.get("data-section", "").strip()
    if not section_id:
        raise ExtractionError(f"第 {section_index + 1} 个栏目缺少 data-section")
    children = _significant_children(node)
    headings = [child for child in children if _has_class(child, "section-heading")]
    if len(headings) != 1 or children[0] is not headings[0]:
        raise ExtractionError(f"栏目 {section_id} 缺少唯一的 section-heading")
    heading_children = _significant_children(headings[0])
    titles = [child for child in heading_children if _has_class(child, "section-title")]
    rules = [child for child in heading_children if _has_class(child, "section-rule")]
    if len(titles) != 1 or len(rules) != 1:
        raise ExtractionError(f"栏目 {section_id} 的标题/横线结构不符合 v5")
    if any(
        child is not titles[0] and child is not rules[0] for child in heading_children
    ):
        raise ExtractionError(f"栏目 {section_id} 的 section-heading 出现未支持节点")
    title = _field_text(titles[0], f"section_plan[{section_index}].title", required=True)

    fallback_source = section_id.lower() if section_id.lower() in SECTION_KEYS else ""
    blocks: list[tuple[str, list[Any]]] = []
    for body_index, child in enumerate(children[1:]):
        if child.tag == "div" and _has_class(child, "education-grid"):
            blocks.append(("education", _education_grid(child)))
        elif child.tag == "ul" and _has_class(child, "resume-bullets"):
            blocks.append(("skills", _bullet_list(child, f"skills block {body_index}")))
        elif child.tag == "p" and _has_class(child, "self-summary"):
            continue
        elif child.tag == "article" and _has_class(child, "entry"):
            source, item = _entry(child, fallback_source, body_index)
            if blocks and blocks[-1][0] == source:
                blocks[-1][1].append(item)
            else:
                blocks.append((source, [item]))
        else:
            raise ExtractionError(f"栏目 {section_id} 出现未支持的节点：<{child.tag}>")
    return section_id, title, blocks


def _extract_source(source: str) -> dict[str, Any]:
    document = _parse_document(source)
    mains = [node for node in _descendants(document, "main") if node.attrs.get("id") == "resume-sheet"]
    if len(mains) != 1 or not _has_class(mains[0], "resume-sheet"):
        raise ExtractionError("HTML 中未找到唯一的固定 v5 resume-sheet")
    main = mains[0]
    children = _significant_children(main)
    model: dict[str, Any] = {
        "schema_version": "resume-model-v1",
        "personal": _header(main),
        "education": [],
        "skills": [],
        "practice": [],
        "research": [],
        "self_summary": "",
    }
    section_nodes = [child for child in children if child.tag == "section"]
    if len(section_nodes) != len(children) - 1:
        raise ExtractionError("resume-sheet 只能包含页眉和栏目")
    if not section_nodes:
        raise ExtractionError("resume-sheet 缺少栏目")

    legacy_summary_nodes = [
        node for node in section_nodes if node.attrs.get("data-section") == "self-summary"
    ]
    if len(legacy_summary_nodes) > 1:
        raise ExtractionError("自我评价栏目不能重复")
    content_section_nodes = [
        node for node in section_nodes if node not in legacy_summary_nodes
    ]
    inline_summary_nodes = [
        node
        for section in content_section_nodes
        for node in _descendants(section)
        if node.tag == "p" and _has_class(node, "self-summary")
    ]
    if len(inline_summary_nodes) > 1 or (
        legacy_summary_nodes and inline_summary_nodes
    ):
        raise ExtractionError("自我评价不能重复")
    if legacy_summary_nodes:
        summary_node = legacy_summary_nodes[0]
        summary_values = [
            node for node in _descendants(summary_node)
            if node.tag == "p" and _has_class(node, "self-summary")
        ]
        if len(summary_values) != 1:
            raise ExtractionError("自我评价栏目必须包含唯一 self-summary 正文")
        model["self_summary"] = _field_text(
            summary_values[0], "self_summary", required=False
        )
    elif inline_summary_nodes:
        model["self_summary"] = _inline_self_summary(inline_summary_nodes[0])
    section_nodes = content_section_nodes

    sections = [_section(node, index) for index, node in enumerate(section_nodes)]
    section_ids = [item[0] for item in sections]
    if len(set(section_ids)) != len(section_ids):
        raise ExtractionError("栏目 data-section 不能重复")

    normal = (
        len(sections) == len(SECTION_KEYS)
        and set(section_ids) == set(SECTION_KEYS)
        and all(
            all(source == section_id for source, _items in blocks)
            for section_id, _title, blocks in sections
        )
    )
    if normal:
        titles: dict[str, str] = {}
        for section_id, title, blocks in sections:
            titles[section_id] = title
            for source_name, items in blocks:
                model[source_name].extend(items)
        model["section_order"] = section_ids
        model["section_titles"] = titles
        return model

    # A section_plan is needed when the user/model displayed different fact
    # types together or used a custom section id.  Top-level arrays remain
    # typed, while blocks preserve exactly what was displayed and in what
    # order.
    plan: list[dict[str, Any]] = []
    for section_id, title, blocks in sections:
        if not blocks:
            raise ExtractionError(
                f"自定义/混合栏目 {section_id} 为空，无法安全恢复 section_plan"
            )
        plan_blocks: list[dict[str, Any]] = []
        for source_name, items in blocks:
            start = len(model[source_name])
            model[source_name].extend(items)
            plan_blocks.append(
                {"source": source_name, "indices": list(range(start, start + len(items)))}
            )
        plan.append({"id": section_id, "title": title, "blocks": plan_blocks})
    model["section_plan"] = plan
    return model


def extract_html(source: str) -> dict[str, Any]:
    """Return a model from an already-read fixed-v5 HTML string."""

    model = _extract_source(source)
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    model["handoff"] = _recovered_handoff("<in-memory-html>", digest)
    return model


def _scope_snapshot(model: dict[str, Any]) -> dict[str, Any]:
    """Flatten supported v5 content, including structure and bold runs."""

    snapshot: dict[str, Any] = {}

    def visit(value: Any, path: str) -> None:
        if isinstance(value, dict):
            snapshot[f"{path}.__keys__"] = tuple(sorted(value))
            for key in sorted(value):
                visit(value[key], f"{path}.{key}" if path else key)
            return
        if isinstance(value, list):
            snapshot[f"{path}.__length__"] = len(value)
            for index, item in enumerate(value):
                visit(item, f"{path}[{index}]")
            return
        snapshot[path] = value

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
            visit(model[key], key)
    for section in ("practice", "research"):
        entries = model.get(section, [])
        snapshot[f"{section}.__length__"] = len(entries)
        snapshot[f"{section}.__order__"] = tuple(
            entry.get("node_id") if isinstance(entry, dict) else None
            for entry in entries
        )
        for entry_index, entry in enumerate(entries):
            entry_id = entry.get("node_id") or f"{section}[{entry_index}]"
            entry_path = entry_id
            snapshot[f"{entry_path}.__keys__"] = tuple(sorted(entry))
            for field in ("node_id", "name", "field", "date"):
                if field in entry:
                    visit(entry[field], f"{entry_path}.{field}")
            bullets = entry.get("bullets", [])
            snapshot[f"{entry_path}.bullets.__length__"] = len(bullets)
            snapshot[f"{entry_path}.bullets.__order__"] = tuple(
                bullet.get("node_id") if isinstance(bullet, dict) else None
                for bullet in bullets
            )
            for bullet_index, bullet in enumerate(bullets):
                bullet_id = bullet.get("node_id") or f"{entry_path}.bullets[{bullet_index}]"
                visit(bullet, bullet_id)
    return snapshot


def _scope_covers(path: str, allowed_nodes: set[str]) -> bool:
    return any(
        path == node or path.startswith(f"{node}.") or path.startswith(f"{node}[")
        for node in allowed_nodes
    )


def compare_html_scope(
    baseline_source: str,
    current_source: str,
    *,
    allowed_nodes: set[str],
    global_content_constraints: list[dict[str, Any]],
) -> dict[str, Any]:
    """Verify that a fixed-v5 local edit changed only named content nodes.

    Experience paths prefer renderer ``data-node-id`` values, for example
    ``practice.entry-1.bullet-2``; fields without stable IDs use model paths such
    as ``education[0].date``. Text, structure,
    dates, numbers and inline bold are compared because all are represented in
    the projection.  This is a validator only; it never rewrites either HTML.
    """

    if not allowed_nodes or not all(
        isinstance(node, str) and node.strip() for node in allowed_nodes
    ):
        raise ScopeValidationError("局部修改必须提供至少一个非空授权 DOM 节点")
    baseline_model = _extract_source(baseline_source)
    current_model = _extract_source(current_source)
    baseline = _scope_snapshot(baseline_model)
    current = _scope_snapshot(current_model)
    changed = sorted(
        path
        for path in set(baseline) | set(current)
        if baseline.get(path) != current.get(path)
    )
    unauthorized = [path for path in changed if not _scope_covers(path, allowed_nodes)]
    if unauthorized:
        raise ScopeValidationError(
            "未授权 DOM 节点发生漂移：" + "、".join(unauthorized[:8])
        )
    current_text = "\n".join(
        value for value in current.values() if isinstance(value, str)
    )
    current_nodes = {
        entry.get("node_id")
        for section in ("practice", "research")
        for entry in current_model.get(section, [])
        if isinstance(entry, dict) and entry.get("node_id")
    }
    current_nodes.update(
        bullet.get("node_id")
        for section in ("practice", "research")
        for entry in current_model.get(section, [])
        if isinstance(entry, dict)
        for bullet in entry.get("bullets", [])
        if isinstance(bullet, dict) and bullet.get("node_id")
    )
    for constraint in global_content_constraints:
        if not isinstance(constraint, dict) or constraint.get("status") != "active":
            continue
        constraint_id = constraint.get("constraint_id", "<unknown>")
        locator = constraint.get("mechanical_locator") or {}
        node_id = locator.get("node_id")
        if node_id and node_id in current_nodes:
            raise ScopeValidationError(
                f"全局删除约束 {constraint_id} 检测到节点复活：{node_id}"
            )
        for forbidden in locator.get("forbidden_texts", []):
            if isinstance(forbidden, str) and forbidden and forbidden in current_text:
                raise ScopeValidationError(
                    f"全局删除约束 {constraint_id} 检测到内容复活：{forbidden}"
                )
    return {"status": "PASS", "changed_nodes": changed}


def _recovered_handoff(base_path: str, digest: str) -> dict[str, Any]:
    """Mark extracted content as recovered, never as user-confirmed."""

    content_version = f"recovered-{digest[:12]}"
    return {
        "content_version": content_version,
        "base_path": base_path,
        "base_sha256": digest,
        "change_set": [],
        "locked_nodes": [],
        "confirmation": {
            "status": "recovered",
            "version": content_version,
            "source": "fixed-v5-html-extractor",
        },
    }


def extract(input_path: Path, output_path: Path) -> None:
    """Extract a fixed-v5 HTML file to a task-local JSON model."""

    input_path = input_path.expanduser().resolve()
    if not input_path.exists() or not input_path.is_file():
        raise ExtractionError(f"找不到输入 HTML：{input_path}")
    try:
        source = input_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise ExtractionError(f"无法读取输入 HTML：{input_path}: {error}") from error
    model = _extract_source(source)
    digest = hashlib.sha256(input_path.read_bytes()).hexdigest()
    model["handoff"] = _recovered_handoff(str(input_path), digest)
    output_path = output_path.expanduser().resolve()
    if output_path.suffix.lower() != ".json":
        raise ExtractionError("输出文件必须使用 .json 扩展名")
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(model, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as error:
        raise ExtractionError(f"无法写入输出 JSON：{output_path}: {error}") from error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="输入固定 v5 HTML")
    parser.add_argument("--output", required=True, type=Path, help="输出 resume-model-v1 JSON")
    args = parser.parse_args()
    try:
        extract(args.input, args.output)
    except ExtractionError as error:
        parser.error(str(error))
    print(args.output.expanduser().resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
