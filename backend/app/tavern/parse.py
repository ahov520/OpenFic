"""Parse SillyTavern world books, character cards, and presets for writing."""

from __future__ import annotations

import base64
import io
import json
import re
from dataclasses import dataclass, field
from typing import Literal

from PIL import Image


LORE_SOURCE_WORLD = "sillytavern"
LORE_SOURCE_CARD = "character_card"

_JAILBREAK_MARKERS = (
    "jailbreak",
    "do anything now",
    "dan mode",
    "ignore previous",
    "ignore all previous",
    "without restrictions",
    "忽略之前",
    "忽略以前",
    "无视限制",
    "无审查",
    "不受限制",
    "开发者模式",
    "破限",
    "绕过安全",
)
_STYLE_MARKERS = (
    "文风",
    "人称",
    "对白",
    "对话",
    "视角",
    "白描",
    "句式",
    "防升华",
    "抗升华",
    "第一人称",
    "第三人称",
    "pov",
    "叙事边界",
)
_SKILL_MARKERS = (
    "方法论",
    "写法",
    "场景",
    "如何写",
    "步骤",
    "技巧",
    "活人感",
    "叙事推进",
    "大纲",
)
_DROP_MARKERS = (
    "cot",
    "思维链",
    "chain of thought",
    "<think",
    "自检",
    "检查清单",
    "写完后检查",
    "回头查",
    "{{setvar",
    "{{getvar",
    "{{roll",
    "变量清空",
)
_MACRO_CHAR = re.compile(r"\{\{\s*char\s*\}\}", re.IGNORECASE)
_MACRO_USER = re.compile(r"\{\{\s*user\s*\}\}", re.IGNORECASE)
_MACRO_RANDOM = re.compile(r"\{\{\s*(?:random|roll)\s*:[^}]*\}\}", re.IGNORECASE)
_MACRO_OTHER = re.compile(r"\{\{[^{}]{1,80}\}\}")


@dataclass
class LoreEntryDraft:
    """Normalized lore entry ready to store."""

    uid: int
    name: str
    content: str
    is_enabled: bool
    order: int
    keywords: list[str] = field(default_factory=list)
    is_constant: bool = True
    source: str = LORE_SOURCE_WORLD


@dataclass
class PresetBlock:
    """One preset prompt after classification."""

    block_id: str
    name: str
    content: str
    bucket: Literal["rule", "skill", "discarded"]
    reason: str


@dataclass
class PresetDraft:
    """Classified SillyTavern preset."""

    name: str
    blocks: list[PresetBlock]


@dataclass
class CharacterCardDraft:
    """Writing-facing slice of a character card."""

    name: str
    description: str
    discarded: list[str]
    style_blocks: list[PresetBlock]
    lore_entries: list[LoreEntryDraft]


def rewrite_macros(text: str, *, char_name: str = "", user_name: str = "") -> str:
    """Replace writing macros and strip SillyTavern engine macros."""
    rewritten = _MACRO_CHAR.sub(char_name, text)
    rewritten = _MACRO_USER.sub(user_name, rewritten)
    rewritten = _MACRO_RANDOM.sub("", rewritten)
    rewritten = _MACRO_OTHER.sub("", rewritten)
    return rewritten.strip()


def detect_material_kind(raw: bytes, filename: str) -> Literal["character_card", "worldbook", "preset"]:
    """Guess which tavern material a file is."""
    lowered = filename.lower()
    if lowered.endswith(".png"):
        return "character_card"
    payload = _load_json_object(raw)
    if isinstance(payload, dict) and isinstance(payload.get("prompts"), list):
        return "preset"
    card_data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(payload, dict) and (
        payload.get("spec") in {"chara_card_v2", "chara_card_v3"}
        or isinstance(card_data, dict)
        and "first_mes" in card_data
    ):
        return "character_card"
    if isinstance(payload, dict) and "name" in payload and "description" in payload and "entries" not in payload:
        return "character_card"
    return "worldbook"


def parse_worldbook_bytes(raw: bytes, *, source: str = LORE_SOURCE_WORLD) -> list[LoreEntryDraft]:
    """Parse a SillyTavern world book JSON file."""
    payload = _load_json_object(raw)
    if not isinstance(payload, dict):
        raise ValueError("世界书文件格式无效：顶层必须是对象")
    entries = payload.get("entries")
    drafts = _drafts_from_entries(entries, source=source)
    if not drafts:
        raise ValueError("世界书中没有可导入的条目")
    return drafts


def parse_character_card_bytes(
    raw: bytes,
    *,
    filename: str = "",
    user_name: str = "",
) -> CharacterCardDraft:
    """Parse a character card JSON or PNG into writing fields."""
    card = _load_character_card(raw, filename)
    data = card.get("data") if isinstance(card.get("data"), dict) else card
    if not isinstance(data, dict):
        raise ValueError("角色卡格式无效")

    name = _clean_text(data.get("name")) or "未命名角色"
    description = _compose_description(data)
    discarded: list[str] = []
    if _clean_text(data.get("first_mes")) or _nonempty_list(data.get("alternate_greetings")):
        discarded.append("开场白")
    if _has_regex(data):
        discarded.append("正则与界面脚本")
    if _has_tavern_scripts(data):
        discarded.append("酒馆脚本与变量")

    style_blocks: list[PresetBlock] = []
    for field_name, label in (
        ("system_prompt", "卡内系统提示"),
        ("post_history_instructions", "卡内后置提示"),
    ):
        content = rewrite_macros(_clean_text(data.get(field_name)), char_name=name, user_name=user_name)
        if not content:
            continue
        block = _classify_block(block_id=f"card-{field_name}", name=label, content=content)
        if block.bucket == "discarded":
            discarded.append(f"{label}（{block.reason}）")
            continue
        if block.bucket == "skill":
            block = PresetBlock(
                block_id=block.block_id,
                name=block.name,
                content=block.content,
                bucket="rule",
                reason="卡内短说明并入文风规则",
            )
        style_blocks.append(block)

    book = data.get("character_book")
    raw_entries = book.get("entries") if isinstance(book, dict) else None
    lore_entries = _drafts_from_entries(raw_entries, source=LORE_SOURCE_CARD)
    return CharacterCardDraft(
        name=name,
        description=description,
        discarded=discarded,
        style_blocks=style_blocks,
        lore_entries=lore_entries,
    )


def parse_preset_bytes(
    raw: bytes,
    *,
    char_name: str = "",
    user_name: str = "",
) -> PresetDraft:
    """Parse a SillyTavern preset and classify each enabled prompt."""
    payload = _load_json_object(raw)
    if not isinstance(payload, dict):
        raise ValueError("预设文件格式无效：缺少 prompts 数组")
    prompts = payload.get("prompts")
    if not isinstance(prompts, list):
        raise ValueError("预设文件格式无效：缺少 prompts 数组")

    enabled = _enabled_identifiers(payload)
    blocks: list[PresetBlock] = []
    for index, prompt in enumerate(prompts):
        if not isinstance(prompt, dict):
            continue
        if prompt.get("marker") is True:
            continue
        identifier = _clean_text(prompt.get("identifier")) or f"prompt-{index}"
        if enabled is not None and identifier not in enabled:
            continue
        if enabled is None and prompt.get("enabled") is False:
            continue
        name = _clean_text(prompt.get("name")) or identifier
        content = rewrite_macros(
            _clean_text(prompt.get("content")),
            char_name=char_name,
            user_name=user_name,
        )
        if not content:
            continue
        blocks.append(_classify_block(block_id=identifier, name=name, content=content))
    if not blocks:
        raise ValueError("预设中没有可导入的提示词块")
    preset_name = _clean_text(payload.get("name")) or "未命名预设"
    return PresetDraft(name=preset_name, blocks=blocks)


def _classify_block(*, block_id: str, name: str, content: str) -> PresetBlock:
    haystack = f"{name}\n{content}".casefold()
    if _looks_like_separator(content) or any(marker in haystack for marker in _DROP_MARKERS):
        return PresetBlock(block_id, name, content, "discarded", "机制模拟或自检，不进入写作上下文")
    if any(marker in haystack for marker in _JAILBREAK_MARKERS):
        return PresetBlock(block_id, name, content, "discarded", "身份绕过或破限，不导入")
    style_hit = any(marker in haystack for marker in _STYLE_MARKERS)
    skill_hit = any(marker in haystack for marker in _SKILL_MARKERS)
    if style_hit and (not skill_hit or len(content) < 500):
        return PresetBlock(block_id, name, content, "rule", "文风或叙事边界")
    if skill_hit or len(content) > 600:
        return PresetBlock(block_id, name, content, "skill", "动笔前的方法论或场景写法")
    return PresetBlock(block_id, name, content, "discarded", "未归入文风或方法论")


def _looks_like_separator(content: str) -> bool:
    stripped = content.strip()
    if len(stripped) < 20 and not any(char.isalnum() for char in stripped):
        return True
    return stripped in {"---", "===", "***"}


def _drafts_from_entries(raw_entries: object, *, source: str) -> list[LoreEntryDraft]:
    rows: list[tuple[object, dict]] = []
    if isinstance(raw_entries, dict):
        for key, value in raw_entries.items():
            if isinstance(value, dict):
                rows.append((key, value))
    elif isinstance(raw_entries, list):
        for index, value in enumerate(raw_entries):
            if isinstance(value, dict):
                rows.append((index, value))

    drafts: list[LoreEntryDraft] = []
    for fallback_key, raw_entry in rows:
        content = raw_entry.get("content")
        content_text = content if isinstance(content, str) else ""
        if not content_text.strip():
            continue
        uid = _read_uid(raw_entry.get("uid"), fallback_key, len(drafts))
        comment = raw_entry.get("comment") or raw_entry.get("name")
        name = comment.strip()[:200] if isinstance(comment, str) and comment.strip() else f"条目 {uid}"
        keywords = _read_keywords(raw_entry)
        constant_flag = raw_entry.get("constant")
        is_constant = bool(constant_flag) if constant_flag is not None else False
        if not keywords:
            is_constant = True
        enabled = raw_entry.get("enabled")
        if enabled is None:
            enabled = not bool(raw_entry.get("disable", False))
        order_value = raw_entry.get("insertion_order", raw_entry.get("order"))
        order = order_value if isinstance(order_value, int) else uid + 1
        drafts.append(
            LoreEntryDraft(
                uid=uid,
                name=name,
                content=content_text,
                is_enabled=bool(enabled),
                order=order,
                keywords=keywords,
                is_constant=is_constant,
                source=source,
            )
        )
    drafts.sort(key=lambda entry: (entry.order, entry.uid))
    return drafts


def _read_keywords(raw_entry: dict) -> list[str]:
    values: list[str] = []
    for field_name in ("key", "keys", "keysecondary", "secondary_keys"):
        raw = raw_entry.get(field_name)
        if isinstance(raw, str) and raw.strip():
            values.append(raw.strip())
        elif isinstance(raw, list):
            values.extend(item.strip() for item in raw if isinstance(item, str) and item.strip())
    return json.loads(dump_keywords_inline(values))


def dump_keywords_inline(keywords: list[str]) -> str:
    from app.tavern.keywords import dump_keywords

    return dump_keywords(keywords)


def _read_uid(raw_uid: object, fallback_key: object, index: int) -> int:
    if isinstance(raw_uid, int) and not isinstance(raw_uid, bool):
        return raw_uid
    if isinstance(fallback_key, int) and not isinstance(fallback_key, bool):
        return fallback_key
    try:
        return int(fallback_key)  # ty: ignore[invalid-argument-type]
    except (TypeError, ValueError):
        return index


def _compose_description(data: dict) -> str:
    sections: list[str] = []
    description = _clean_text(data.get("description"))
    if description:
        sections.append(description)
    personality = _clean_text(data.get("personality"))
    if personality:
        sections.append(f"## 性格\n{personality}")
    scenario = _clean_text(data.get("scenario"))
    if scenario:
        sections.append(f"## 场景\n{scenario}")
    example = _clean_text(data.get("mes_example"))
    if example:
        sections.append(f"## 说话样本\n{example}")
    return "\n\n".join(sections)


def _load_character_card(raw: bytes, filename: str) -> dict:
    if filename.lower().endswith(".png") or raw.startswith(b"\x89PNG"):
        encoded = _png_card_text(raw)
        if not encoded:
            raise ValueError("PNG 中没有角色卡数据")
        try:
            decoded = base64.b64decode(encoded)
            payload = json.loads(decoded)
        except (ValueError, json.JSONDecodeError) as exc:
            raise ValueError("角色卡 PNG 无法解析") from exc
        if not isinstance(payload, dict):
            raise ValueError("角色卡格式无效")
        return payload
    payload = _load_json_object(raw)
    if not isinstance(payload, dict):
        raise ValueError("角色卡文件格式无效：顶层必须是对象")
    return payload


def _png_card_text(raw: bytes) -> str:
    image = Image.open(io.BytesIO(raw))
    chunks: dict[str, str] = {}
    text = getattr(image, "text", None)
    if isinstance(text, dict):
        chunks.update({str(key): str(value) for key, value in text.items()})
    info = image.info if isinstance(image.info, dict) else {}
    for key, value in info.items():
        if isinstance(value, str):
            chunks.setdefault(str(key), value)
    for key in ("ccv3", "chara"):
        if chunks.get(key):
            return chunks[key].strip()
    return ""


def _load_json_object(raw: bytes) -> object:
    try:
        return json.loads(raw.decode("utf-8-sig"))
    except UnicodeDecodeError as exc:
        raise ValueError("文件编码无效，请使用 UTF-8 编码的 JSON 文件") from exc
    except json.JSONDecodeError as exc:
        raise ValueError("JSON 解析失败，请检查导出文件格式") from exc


def _enabled_identifiers(payload: dict) -> set[str] | None:
    prompt_order = payload.get("prompt_order")
    if not isinstance(prompt_order, list) or not prompt_order:
        return None
    first = prompt_order[0]
    if not isinstance(first, dict) or not isinstance(first.get("order"), list):
        return None
    enabled: set[str] = set()
    for item in first["order"]:
        if isinstance(item, dict) and item.get("enabled") is not False:
            identifier = item.get("identifier")
            if isinstance(identifier, str) and identifier:
                enabled.add(identifier)
    return enabled


def _clean_text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _nonempty_list(value: object) -> bool:
    return isinstance(value, list) and any(isinstance(item, str) and item.strip() for item in value)


def _has_regex(data: dict) -> bool:
    extensions = data.get("extensions")
    if isinstance(extensions, dict) and extensions.get("regex_scripts"):
        return True
    return bool(data.get("regex_scripts"))


def _has_tavern_scripts(data: dict) -> bool:
    extensions = data.get("extensions")
    if not isinstance(extensions, dict):
        return False
    helper = extensions.get("tavern_helper")
    if isinstance(helper, dict) and (helper.get("scripts") or helper.get("variables")):
        return True
    return bool(extensions.get("tavern_helper"))
