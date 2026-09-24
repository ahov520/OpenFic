# -*- coding: utf-8 -*-
"""章节卡片字段与上下文注入。"""

import json

import pytest

from app.memory.chapter.context_builder import _build_chapter_list_field, _build_latest_field
from app.storage.chapter_plan import (
    catalog_plan_fields,
    latest_plan_fields,
    normalize_synopsis,
    normalize_writing_status,
)
from app.storage.models.chapter import Chapter


def _chapter(**overrides: object) -> Chapter:
    data = {
        "project_id": "project-1",
        "volume_id": "volume-1",
        "title": "第一章",
        "content": "正文",
        "word_count": 2,
        "order": 1,
    }
    data.update(overrides)
    return Chapter(**data)


def test_normalize_writing_status_defaults_and_rejects() -> None:
    assert normalize_writing_status(None) == "idea"
    assert normalize_writing_status("") == "idea"
    assert normalize_writing_status("revising") == "revising"
    with pytest.raises(ValueError, match="写作状态无效"):
        normalize_writing_status("final")


def test_normalize_synopsis_unifies_newlines_and_limits_length() -> None:
    assert normalize_synopsis(None) == ""
    assert normalize_synopsis("甲\r\n乙\r丙") == "甲\n乙\n丙"
    with pytest.raises(ValueError, match="梗概超出"):
        normalize_synopsis("字" * 2001)


def test_latest_context_includes_author_plan_without_replacing_prose() -> None:
    chapter = _chapter(
        synopsis="  主角发现门后有光。  ",
        writing_status="drafting",
    )

    payload = json.loads(_build_latest_field(chapter, 3).content)

    assert payload["title"] == "第一章"
    assert payload["content"] == "正文"
    assert payload["writing_status"] == "drafting"
    assert payload["author_synopsis"] == "主角发现门后有光。"
    assert latest_plan_fields(chapter)["author_synopsis"] == "主角发现门后有光。"


def test_catalog_omits_empty_synopsis_and_truncates_long_plan() -> None:
    empty = _chapter()
    long_plan = _chapter(synopsis="梗" * 180, writing_status="done")

    assert catalog_plan_fields(empty) == {"writing_status": "idea"}
    catalog = catalog_plan_fields(long_plan)
    assert catalog["writing_status"] == "done"
    assert catalog["author_synopsis"].endswith("…")
    assert len(catalog["author_synopsis"]) == 160

    listed = json.loads(
        _build_chapter_list_field(
            [empty, long_plan],
            {empty.id: 1, long_plan.id: 2},
        ).content
    )
    assert listed[0]["writing_status"] == "idea"
    assert "author_synopsis" not in listed[0]
    assert listed[1]["author_synopsis"].endswith("…")
