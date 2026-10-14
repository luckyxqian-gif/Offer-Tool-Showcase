#!/usr/bin/env python3
"""Extract a resume-model-v1 JSON document from a DOCX resume.

This extractor intentionally handles only the structure used by the confirmed
v5 resume template.  It does not rewrite resume content or infer missing
facts.  The only output containing personal data is the path supplied with
``--output``.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import mimetypes
import posixpath
import re
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile


W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
CT = "{http://schemas.openxmlformats.org/package/2006/content-types}"

SECTION_NAMES = {
    "教育背景": "education",
    "奖项技能": "skills",
    "法律实践": "practice",
    "科研成果": "research",
}
SUPPORTED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_CONTACT_LINES = 4
MAX_BOLD_LABEL_LENGTH = 30


class ExtractionError(ValueError):
    """An input DOCX cannot be converted without inventing content."""


def _parse_xml(archive: ZipFile, member: str) -> ET.Element:
    try:
        data = archive.read(member)
    except KeyError as error:
        raise ExtractionError(f"DOCX 缺少必需文件：{member}") from error
    try:
        return ET.fromstring(data)
    except ET.ParseError as error:
        raise ExtractionError(f"DOCX XML 无法解析：{member}: {error}") from error


def _is_bold(run: ET.Element) -> bool:
    properties = run.find(W + "rPr")
    if properties is None:
        return False
    bold = properties.find(W + "b")
    if bold is None:
        bold = properties.find(W + "bCs")
    if bold is None:
        return False
    value = bold.get(W + "val")
    if value is None:
        return True
    return value.lower() not in {"0", "false", "off", "none", "no"}


def _append_run(runs: list[dict[str, Any]], text: str, bold: bool) -> None:
    if not text:
        return
    if runs and bool(runs[-1]["bold"]) == bold:
        runs[-1]["text"] += text
        return
    runs.append({"text": text, "bold": bold})


def _read_run(run: ET.Element) -> list[dict[str, Any]]:
    bold = _is_bold(run)
    result: list[dict[str, Any]] = []
    for child in run:
        if child.tag == W + "rPr":
            continue
        if child.tag in {W + "t", W + "delText", W + "instrText"}:
            _append_run(result, child.text or "", bold)
        elif child.tag == W + "tab":
            _append_run(result, "\t", bold)
        elif child.tag in {W + "br", W + "cr"}:
            _append_run(result, "\n", bold)
        elif child.tag == W + "noBreakHyphen":
            _append_run(result, "\u2011", bold)
    return result


def _paragraph_runs(paragraph: ET.Element) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for run in paragraph.iter(W + "r"):
        for item in _read_run(run):
            _append_run(result, item["text"], bool(item["bold"]))
    return result


def _table_rows(table: ET.Element) -> list[list[list[dict[str, Any]]]]:
    rows: list[list[list[dict[str, Any]]]] = []
    for row in table.findall("./" + W + "tr"):
        cells: list[list[dict[str, Any]]] = []
        for cell in row.findall("./" + W + "tc"):
            paragraphs = list(cell.iter(W + "p"))
            cell_runs: list[dict[str, Any]] = []
            for index, paragraph in enumerate(paragraphs):
                if index:
                    _append_run(cell_runs, "\n", False)
                for item in _paragraph_runs(paragraph):
                    _append_run(cell_runs, item["text"], bool(item["bold"]))
            cells.append(cell_runs)
        rows.append(cells)
    return rows


def _body_blocks(root: ET.Element) -> Iterable[tuple[str, Any]]:
    body = root.find(W + "body")
    if body is None:
        raise ExtractionError("DOCX 缺少 w:body")
    for child in body:
        if child.tag == W + "p":
            yield "paragraph", _paragraph_runs(child)
        elif child.tag == W + "tbl":
            yield "table", _table_rows(child)


def _runs_text(runs: Iterable[dict[str, Any]]) -> str:
    return "".join(str(item.get("text", "")) for item in runs)


def _copy_runs(runs: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"text": str(item.get("text", "")), "bold": bool(item.get("bold", False))}
        for item in runs
        if item.get("text", "")
    ]


def _trim_runs(runs: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    result = _copy_runs(runs)
    while result and not result[0]["text"]:
        result.pop(0)
    while result and not result[-1]["text"]:
        result.pop()
    if result:
        result[0]["text"] = result[0]["text"].lstrip()
        result[-1]["text"] = result[-1]["text"].rstrip()
    return [item for item in result if item["text"]]


def _split_runs(runs: Iterable[dict[str, Any]], delimiter: str) -> list[list[dict[str, Any]]]:
    segments: list[list[dict[str, Any]]] = [[]]
    for run in runs:
        text = str(run.get("text", ""))
        bold = bool(run.get("bold", False))
        parts = text.split(delimiter)
        for index, part in enumerate(parts):
            if part:
                _append_run(segments[-1], part, bold)
            if index < len(parts) - 1:
                segments.append([])
    return segments


def _split_runs_at(runs: Iterable[dict[str, Any]], position: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
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
        if remaining > 0:
            _append_run(left, text[:remaining], bold)
            _append_run(right, text[remaining:], bold)
            remaining = 0
        else:
            _append_run(right, text, bold)
    return left, right


def _plain_field(runs: Iterable[dict[str, Any]]) -> str:
    return _runs_text(runs).replace("\n", " ").strip()


def _normalise_heading(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _normalise_name(text: str) -> str:
    value = " ".join(text.split())
    value = re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])", "", value)
    if not value:
        raise ExtractionError("无法从 DOCX 头部提取姓名")
    return value


def _remove_bullet_marker(runs: Iterable[dict[str, Any]]) -> list[dict[str, Any]] | None:
    result = _copy_runs(runs)
    while result:
        result[0]["text"] = result[0]["text"].lstrip()
        if result[0]["text"]:
            break
        result.pop(0)
    if not result or not result[0]["text"].startswith("•"):
        return None
    result[0]["text"] = result[0]["text"][1:]
    while result:
        result[0]["text"] = result[0]["text"].lstrip()
        if result[0]["text"]:
            break
        result.pop(0)
    return _trim_runs(result)


def _split_label(payload: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    text = _runs_text(payload)
    colon_positions = [position for position in (text.find("："), text.find(":")) if position >= 0]
    if colon_positions:
        position = min(colon_positions) + 1
        label_runs, body_runs = _split_runs_at(payload, position)
        return _plain_field(label_runs), _trim_runs(body_runs)

    prefix: list[dict[str, Any]] = []
    consumed = 0
    for run in payload:
        if not bool(run.get("bold", False)):
            break
        prefix.append(run)
        consumed += len(str(run.get("text", "")))
    if prefix and 0 < consumed <= MAX_BOLD_LABEL_LENGTH and consumed < len(text):
        _, body_runs = _split_runs_at(payload, consumed)
        body_runs = _trim_runs(body_runs)
        if body_runs:
            return _plain_field(prefix), body_runs
    return "", _trim_runs(payload)


def _bullet_item(runs: list[dict[str, Any]]) -> dict[str, Any] | None:
    payload = _remove_bullet_marker(runs)
    if payload is None:
        return None
    label, body_runs = _split_label(payload)
    item: dict[str, Any] = {
        "label": label,
        "text": _plain_field(body_runs),
    }
    if any(bool(run.get("bold", False)) for run in body_runs):
        item["runs"] = body_runs
    return item


def _education_rows(rows: list[list[list[dict[str, Any]]]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row_index, cells in enumerate(rows):
        if not any(_plain_field(cell) for cell in cells):
            continue
        if len(cells) != 4:
            raise ExtractionError(
                f"教育背景第 {row_index + 1} 行有 {len(cells)} 列；仅支持固定四列表格"
            )
        result.append(
            {
                "school": _trim_runs(cells[0]),
                "program": _trim_runs(cells[1]),
                "rank": _trim_runs(cells[2]),
                "date": _trim_runs(cells[3]),
            }
        )
    return result


def _title_fields(runs: list[dict[str, Any]], section: str, paragraph_index: int) -> dict[str, Any]:
    fields = _split_runs(_trim_runs(runs), "\t")
    if len(fields) != 3:
        raise ExtractionError(
            f"{section}第 {paragraph_index + 1} 个标题行应包含 3 个 w:tab 字段，实际为 {len(fields) - 1} 个制表分隔"
        )
    values = [_plain_field(field) for field in fields]
    if not values[0]:
        raise ExtractionError(f"{section}标题行缺少名称")
    return {"name": values[0], "field": values[1], "date": values[2], "bullets": []}


def _normalise_mime(value: str | None) -> str | None:
    if not value:
        return None
    value = value.lower()
    if value == "image/jpg":
        return "image/jpeg"
    return value if value in SUPPORTED_IMAGE_TYPES else None


def _content_types(archive: ZipFile) -> tuple[dict[str, str], dict[str, str]]:
    try:
        root = _parse_xml(archive, "[Content_Types].xml")
    except ExtractionError:
        return {}, {}
    defaults: dict[str, str] = {}
    overrides: dict[str, str] = {}
    for item in root.findall(CT + "Default"):
        extension = item.get("Extension")
        content_type = _normalise_mime(item.get("ContentType"))
        if extension and content_type:
            defaults[extension.lower().lstrip(".")] = content_type
    for item in root.findall(CT + "Override"):
        part_name = item.get("PartName")
        content_type = _normalise_mime(item.get("ContentType"))
        if part_name and content_type:
            overrides[part_name.lstrip("/")] = content_type
    return defaults, overrides


def _member_mime(member: str, defaults: dict[str, str], overrides: dict[str, str]) -> str | None:
    if member in overrides:
        return overrides[member]
    extension = Path(member).suffix.lower().lstrip(".")
    content_type = defaults.get(extension)
    if content_type:
        return content_type
    return _normalise_mime(mimetypes.guess_type(member)[0])


def _resolve_target(target: str) -> str:
    target = target.replace("\\", "/")
    if target.startswith("/"):
        return target.lstrip("/")
    return posixpath.normpath(posixpath.join("word", target))


def _relationships(archive: ZipFile) -> dict[str, str]:
    try:
        root = _parse_xml(archive, "word/_rels/document.xml.rels")
    except ExtractionError:
        return {}
    return {
        item.get("Id"): _resolve_target(item.get("Target"))
        for item in root.findall(REL + "Relationship")
        if item.get("Id") and item.get("Target") and item.get("TargetMode") != "External"
    }


def _photo_data_url(archive: ZipFile, document_root: ET.Element) -> str | None:
    defaults, overrides = _content_types(archive)
    relationships = _relationships(archive)
    candidates: list[str] = []
    for blip in document_root.iter(A + "blip"):
        relationship_id = blip.get(R + "embed")
        if relationship_id and relationship_id in relationships:
            candidates.append(relationships[relationship_id])
    candidates.extend(
        member
        for member in sorted(archive.namelist())
        if member.startswith("word/media/")
    )
    seen: set[str] = set()
    for member in candidates:
        if member in seen or member not in archive.namelist():
            continue
        seen.add(member)
        mime = _member_mime(member, defaults, overrides)
        if mime not in SUPPORTED_IMAGE_TYPES:
            continue
        data = archive.read(member)
        return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
    return None


def _extract_from_archive(archive: ZipFile) -> dict[str, Any]:
    document_root = _parse_xml(archive, "word/document.xml")
    blocks = list(_body_blocks(document_root))

    heading_positions: list[tuple[int, str]] = []
    for index, (kind, value) in enumerate(blocks):
        if kind != "paragraph":
            continue
        text = _plain_field(_trim_runs(value))
        section = SECTION_NAMES.get(_normalise_heading(text))
        if section:
            heading_positions.append((index, section))
    if not heading_positions:
        raise ExtractionError("DOCX 中未找到固定栏目标题：教育背景、奖项技能、法律实践、科研成果")

    first_heading = min(index for index, _ in heading_positions)
    header_values = [
        _plain_field(_trim_runs(value))
        for index, (kind, value) in enumerate(blocks[:first_heading])
        if kind == "paragraph" and _plain_field(_trim_runs(value))
    ]
    if not header_values:
        raise ExtractionError("DOCX 头部缺少姓名段落")
    name = _normalise_name(header_values[0])
    contact_lines = header_values[1:]
    if len(contact_lines) > MAX_CONTACT_LINES:
        raise ExtractionError(f"DOCX 头部联系方式超过 {MAX_CONTACT_LINES} 行，未擅自合并")

    model: dict[str, Any] = {
        "schema_version": "resume-model-v1",
        "personal": {"name": name, "contact_lines": contact_lines},
        "education": [],
        "skills": [],
        "practice": [],
        "research": [],
        "self_summary": "",
    }
    photo = _photo_data_url(archive, document_root)
    if photo:
        model["personal"]["photo_data_url"] = photo

    current_section: str | None = None
    seen_sections: set[str] = set()
    current_entry: dict[str, Any] | None = None
    for block_index, (kind, value) in enumerate(blocks):
        if kind == "paragraph":
            runs = value
            text = _plain_field(_trim_runs(runs))
            if not text:
                continue
            section = SECTION_NAMES.get(_normalise_heading(text))
            if section:
                if section in seen_sections:
                    raise ExtractionError(f"DOCX 重复出现栏目标题：{text}")
                seen_sections.add(section)
                current_section = section
                current_entry = None
                continue
            if current_section is None:
                continue
            if current_section == "education":
                raise ExtractionError(f"教育背景栏目出现未放入表格的正文：{text}")
            if current_section == "skills":
                item = _bullet_item(runs)
                if item is None:
                    raise ExtractionError(f"奖项技能栏目出现非字面量 • 开头的段落：{text}")
                model["skills"].append(item)
                continue

            item = _bullet_item(runs)
            if item is not None:
                if current_entry is None:
                    raise ExtractionError(f"{text[:20]}：bullet 前缺少公司或项目标题行")
                current_entry["bullets"].append(item)
                continue
            current_entry = _title_fields(runs, "法律实践" if current_section == "practice" else "科研成果", block_index)
            model[current_section].append(current_entry)
            continue

        if current_section != "education":
            raise ExtractionError("固定栏目之外或教育背景之外出现表格，无法安全映射")
        model["education"].extend(_education_rows(value))

    missing_sections = [
        SECTION_NAMES[name]
        for name in SECTION_NAMES
        if SECTION_NAMES[name] not in seen_sections
    ]
    if missing_sections:
        labels = "、".join(name for name, section in SECTION_NAMES.items() if section in missing_sections)
        raise ExtractionError(f"DOCX 缺少固定栏目标题：{labels}")
    return model


def extract(input_path: Path, output_path: Path) -> None:
    input_path = input_path.expanduser().resolve()
    if not input_path.exists():
        raise ExtractionError(f"找不到输入 DOCX：{input_path}")
    if not input_path.is_file():
        raise ExtractionError(f"输入路径不是文件：{input_path}")
    try:
        with ZipFile(input_path) as archive:
            model = _extract_from_archive(archive)
    except BadZipFile as error:
        raise ExtractionError(f"输入文件不是有效 DOCX/ZIP：{input_path}") from error
    except OSError as error:
        raise ExtractionError(f"无法读取输入 DOCX：{input_path}: {error}") from error

    digest = hashlib.sha256(input_path.read_bytes()).hexdigest()
    content_version = f"recovered-{digest[:12]}"
    model["handoff"] = {
        "content_version": content_version,
        "base_path": str(input_path),
        "base_sha256": digest,
        "change_set": [],
        "locked_nodes": [],
        "confirmation": {
            "status": "recovered",
            "version": content_version,
            "source": "fixed-v5-docx-extractor",
        },
    }

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
    parser.add_argument("--input", required=True, type=Path, help="输入 DOCX 文件")
    parser.add_argument("--output", required=True, type=Path, help="输出 resume-model-v1 JSON 文件")
    args = parser.parse_args()
    try:
        extract(args.input.expanduser().resolve(), args.output)
    except ExtractionError as error:
        parser.error(str(error))
    print(args.output.expanduser().resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
