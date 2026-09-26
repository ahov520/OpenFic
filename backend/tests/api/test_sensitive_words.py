# -*- coding: utf-8 -*-
"""敏感词词库 API 测试：惰性 seed 幂等、导入解析去重容错、整表更新、导出。"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.sensitive_words import (
    SETTING_KEY_SENSITIVE_WORDS,
    load_starting_words,
    normalize_words,
    parse_import_content,
    words_to_txt,
)
from app.storage.repos import setting_repo


def test_parse_txt_lines_with_source_and_blank_lines() -> None:
    content = "赌博\n枪支|通用类目示例\n\n  洗钱 | 来源B  \n"
    entries = parse_import_content(content, "txt")
    assert entries == [
        {"word": "赌博", "source": ""},
        {"word": "枪支", "source": "通用类目示例"},
        {"word": "洗钱", "source": "来源B"},
    ]


def test_parse_json_strings_and_objects() -> None:
    content = '{"words": ["赌博", {"word": "枪支", "source": "来源A"}]}'
    entries = parse_import_content(content, "json")
    assert entries == [
        {"word": "赌博", "source": ""},
        {"word": "枪支", "source": "来源A"},
    ]


def test_parse_invalid_json_raises_sensitive_word_error() -> None:
    from app.core.sensitive_words import SensitiveWordError

    with pytest.raises(SensitiveWordError):
        parse_import_content("{broken", "json")


def test_normalize_words_dedupes_and_tolerates_invalid() -> None:
    raw = [
        {"word": "赌博", "source": "来源A"},
        {"word": "  赌博  ", "source": "来源B"},  # 去重：首个来源优先
        {"word": "", "source": "空词"},  # 非法：空词
        {"word": "  ", "source": ""},  # 非法：纯空白
        {"word": "长" * 51, "source": ""},  # 非法：超长
        "不是字典",  # 非法：类型
        {"word": "枪支", "source": "通用类目示例"},
    ]
    words, stats = normalize_words(raw)
    assert words == [
        {"word": "赌博", "source": "来源A"},
        {"word": "枪支", "source": "通用类目示例"},
    ]
    assert stats == {"accepted": 2, "duplicates": 1, "invalid": 4}


def test_words_to_txt_includes_source_annotation() -> None:
    words = [
        {"word": "赌博", "source": "通用类目示例"},
        {"word": "枪支", "source": ""},
    ]
    assert words_to_txt(words) == "赌博|通用类目示例\n枪支"


def test_words_containing_pipe_separator_are_rejected() -> None:
    """词内含「|」会破坏 TXT「词|来源」无歧义往返，按非法拒绝。"""
    words, stats = normalize_words(
        [{"word": "违|禁词", "source": ""}, {"word": "正常词", "source": ""}]
    )
    assert words == [{"word": "正常词", "source": ""}]
    assert stats["invalid"] == 1


def test_starting_words_resource_is_valid_and_idempotent() -> None:
    words = load_starting_words()
    assert len(words) >= 20
    assert all(entry["word"] and entry["source"] for entry in words)
    # 随包资源应当幂等可重读
    assert load_starting_words() == words


@pytest.mark.asyncio
async def test_get_words_seeds_starting_list_once(
    client: AsyncClient, session: AsyncSession
) -> None:
    """首次读取惰性 seed 内置首发词库；重复读不重复插入。"""
    first = await client.get("/api/v1/sensitive-words")
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["count"] == len(load_starting_words())
    assert {"word": "赌博", "source": "通用类目示例"} in first_body["words"]

    setting = await setting_repo.get_by_key(session, SETTING_KEY_SENSITIVE_WORDS)
    assert setting is not None
    stored_words = setting.value

    second = await client.get("/api/v1/sensitive-words")
    assert second.status_code == 200
    assert second.json() == first_body

    setting_after = await setting_repo.get_by_key(session, SETTING_KEY_SENSITIVE_WORDS)
    assert setting_after is not None
    # 重复读取不重复插入：存储值保持原样
    assert setting_after.value == stored_words


@pytest.mark.asyncio
async def test_update_replaces_whole_table_and_get_does_not_reseed(
    client: AsyncClient, session: AsyncSession
) -> None:
    """整表更新覆盖词表；用户清空后重复 GET 也不重新 seed。"""
    update = await client.put(
        "/api/v1/sensitive-words",
        json={"words": [{"word": "自定义词", "source": "手工维护"}]},
    )
    assert update.status_code == 200
    assert update.json()["words"] == [{"word": "自定义词", "source": "手工维护"}]

    again = await client.get("/api/v1/sensitive-words")
    assert again.json()["words"] == [{"word": "自定义词", "source": "手工维护"}]

    setting = await setting_repo.get_by_key(session, SETTING_KEY_SENSITIVE_WORDS)
    assert setting is not None
    assert setting.value == '[{"word": "自定义词", "source": "手工维护"}]'


@pytest.mark.asyncio
async def test_import_merges_and_reports_stats(client: AsyncClient) -> None:
    """导入与现有词表按词去重合并，返回接受/重复/非法统计。"""
    await client.put(
        "/api/v1/sensitive-words",
        json={"words": [{"word": "赌博", "source": "来源A"}]},
    )

    response = await client.post(
        "/api/v1/sensitive-words/import",
        json={
            "content": "赌博|重复来源\n枪支|通用类目示例\n\n" + "长" * 51,
            "format": "txt",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["stats"]["accepted"] == 1
    assert body["stats"]["duplicates"] == 1
    assert body["stats"]["invalid"] >= 1
    assert {"word": "赌博", "source": "来源A"} in body["words"]
    assert {"word": "枪支", "source": "通用类目示例"} in body["words"]


@pytest.mark.asyncio
async def test_export_txt_round_trip_preserves_source(client: AsyncClient) -> None:
    """TXT 导出→导入往返：词与来源保持一致（最后一个 | 之后为来源）。"""
    await client.put(
        "/api/v1/sensitive-words",
        json={"words": [{"word": "赌博", "source": "通用类目示例"}]},
    )
    exported = await client.get("/api/v1/sensitive-words/export?format=txt")
    content = exported.json()["content"]
    assert content == "赌博|通用类目示例"

    imported = await client.post(
        "/api/v1/sensitive-words/import",
        json={"content": content, "format": "txt"},
    )
    assert imported.status_code == 200
    body = imported.json()
    assert body["stats"]["duplicates"] == 1  # 与现有词表完全一致，无新增
    assert body["words"] == [{"word": "赌博", "source": "通用类目示例"}]


@pytest.mark.asyncio
async def test_export_txt_and_json_round_trip(client: AsyncClient) -> None:
    await client.put(
        "/api/v1/sensitive-words",
        json={"words": [{"word": "赌博", "source": "通用类目示例"}, {"word": "枪支"}]},
    )

    txt = await client.get("/api/v1/sensitive-words/export?format=txt")
    assert txt.status_code == 200
    assert txt.json()["filename"] == "sensitive-words.txt"
    assert txt.json()["content"] == "赌博|通用类目示例\n枪支"

    json_export = await client.get("/api/v1/sensitive-words/export?format=json")
    assert json_export.status_code == 200
    assert json_export.json()["filename"] == "sensitive-words.json"

    # 导出内容可直接再导入（往返一致）
    round_trip = await client.post(
        "/api/v1/sensitive-words/import",
        json={"content": json_export.json()["content"], "format": "json"},
    )
    assert round_trip.status_code == 200
    assert round_trip.json()["count"] == 2
