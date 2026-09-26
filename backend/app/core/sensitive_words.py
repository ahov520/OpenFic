# -*- coding: utf-8 -*-
"""敏感词/平台违禁词词库服务。

词表存既有 Setting 键值表（key="sensitive_words"，value 为 JSON 数组），
复用 setting_repo.upsert，零迁移。内置首发词库随包分发于
core/resources/sensitive_words/starting_words.json，首次读取惰性 seed，
重复读取不重复插入（幂等）。

已知长期成本：平台违禁规则持续漂移，内置首发词库只是通用类目示例
（非任何平台官方词表），实际使用应按目标平台规则通过导入/整表更新维护。
单用户本地场景写频率低，Setting 单行 JSON 足够；词表上万或多人并发
时再迁独立表（迁移机制支持编号续加）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.repos import setting_repo

SETTING_KEY_SENSITIVE_WORDS = "sensitive_words"
STARTING_WORDS_RESOURCE = Path(__file__).parent / "resources" / "sensitive_words" / "starting_words.json"

MAX_WORD_LENGTH = 50
MAX_SOURCE_LENGTH = 100

# 资源文件每进程只读一次；内容随包分发、运行期不变
_STARTING_WORDS_CACHE: list[dict[str, str]] | None = None


class SensitiveWordError(ValueError):
    """敏感词导入/更新参数无效。"""


def load_starting_words() -> list[dict[str, str]]:
    """读取随包分发的内置首发词库（惰性缓存）。"""
    global _STARTING_WORDS_CACHE
    if _STARTING_WORDS_CACHE is None:
        raw = json.loads(STARTING_WORDS_RESOURCE.read_text(encoding="utf-8"))
        words = raw.get("words", []) if isinstance(raw, dict) else raw
        _STARTING_WORDS_CACHE = [
            {"word": str(entry.get("word", "")), "source": str(entry.get("source", ""))}
            for entry in words
            if isinstance(entry, dict)
        ]
    return list(_STARTING_WORDS_CACHE)


def normalize_words(
    raw_words: Iterable[dict[str, Any]],
) -> tuple[list[dict[str, str]], dict[str, int]]:
    """校验、去重并归一化词条。

    - word 去首尾空白，非空且不超过 MAX_WORD_LENGTH；
    - source 可选，超过 MAX_SOURCE_LENGTH 截断；
    - 按精确 word 去重（首个来源优先）。

    Returns:
        (归一化词条列表, 统计 {accepted, duplicates, invalid})。
    """
    words: list[dict[str, str]] = []
    seen: set[str] = set()
    duplicates = 0
    invalid = 0

    for entry in raw_words:
        if not isinstance(entry, dict):
            invalid += 1
            continue
        word = str(entry.get("word", "")).strip()
        # 词内含「|」会破坏 TXT 行格式的「词|来源」无歧义往返，按非法拒绝
        if not word or len(word) > MAX_WORD_LENGTH or "|" in word:
            invalid += 1
            continue
        if word in seen:
            duplicates += 1
            continue
        seen.add(word)
        source = str(entry.get("source", "")).strip()[:MAX_SOURCE_LENGTH]
        words.append({"word": word, "source": source})

    stats = {"accepted": len(words), "duplicates": duplicates, "invalid": invalid}
    return words, stats


def parse_import_content(content: str, export_format: str) -> list[dict[str, str]]:
    """解析导入内容为原始词条（word/source 字符串），不做长度校验。"""
    if export_format == "json":
        return _parse_json_content(content)
    if export_format == "txt":
        return _parse_txt_content(content)
    raise SensitiveWordError(f"导入格式无效: {export_format}")


def _parse_txt_content(content: str) -> list[dict[str, str]]:
    """TXT 格式：每行一词，可选「词|来源」备注（最后一个 | 之后为来源）。"""
    entries: list[dict[str, str]] = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if "|" in stripped:
            word, _sep, source = stripped.rpartition("|")
            entries.append({"word": word.strip(), "source": source.strip()})
        else:
            entries.append({"word": stripped, "source": ""})
    return entries


def _parse_json_content(content: str) -> list[dict[str, str]]:
    """JSON 格式：词条数组，元素为字符串或 {word, source?} 对象。"""
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise SensitiveWordError("JSON 内容无法解析") from exc
    if isinstance(parsed, dict):
        parsed = parsed.get("words", [])
    if not isinstance(parsed, list):
        raise SensitiveWordError("JSON 内容应为词条数组")
    entries: list[dict[str, str]] = []
    for entry in parsed:
        if isinstance(entry, str):
            entries.append({"word": entry, "source": ""})
        elif isinstance(entry, dict):
            entries.append(
                {"word": str(entry.get("word", "")), "source": str(entry.get("source", ""))}
            )
        else:
            entries.append({"word": "", "source": ""})
    return entries


def words_to_txt(words: Iterable[dict[str, str]]) -> str:
    """导出为 TXT：每行一词，带来源时用「词|来源」。"""
    lines = [
        f"{entry['word']}|{entry['source']}" if entry.get("source") else entry["word"]
        for entry in words
    ]
    return "\n".join(lines)


def words_to_json(words: Iterable[dict[str, str]]) -> str:
    """导出为 JSON 词条数组。"""
    return json.dumps(list(words), ensure_ascii=False, indent=2)


async def get_words(session: AsyncSession) -> list[dict[str, str]]:
    """读取词表；Setting 缺失时惰性 seed 内置首发词库（幂等）。"""
    setting = await setting_repo.get_by_key(session, SETTING_KEY_SENSITIVE_WORDS)
    if setting is None:
        words, _stats = normalize_words(load_starting_words())
        await setting_repo.upsert(session, SETTING_KEY_SENSITIVE_WORDS, json.dumps(words, ensure_ascii=False))
        return words
    return _decode_setting_value(setting.value)


async def save_words(
    session: AsyncSession,
    words: list[dict[str, str]],
    *,
    normalized: bool = False,
) -> list[dict[str, str]]:
    """整表覆盖保存词表。

    normalized=True 表示调用方已完成归一化（router 路径），跳过重复归一化。
    """
    if not normalized:
        words, _stats = normalize_words(words)
    await setting_repo.upsert(
        session, SETTING_KEY_SENSITIVE_WORDS, json.dumps(words, ensure_ascii=False)
    )
    return words


def _decode_setting_value(value: str) -> list[dict[str, str]]:
    try:
        parsed = json.loads(value) if value else []
    except json.JSONDecodeError:
        return []
    words, _stats = normalize_words(parsed if isinstance(parsed, list) else [])
    return words
