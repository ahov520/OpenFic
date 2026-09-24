# -*- coding: utf-8 -*-
"""章节字数目标：校验、进度，以及当前章节上下文。"""

import json

import pytest

from app.memory.chapter.context_builder import _build_chapter_list_field, _build_latest_field
from app.storage.chapter_length import (
    WORD_COUNT_TARGET_MAX,
    chapter_length_progress,
    normalize_word_count_target,
)
from app.storage.chapter_plan import catalog_plan_fields
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


def test_normalize_word_count_target_clears_and_rejects_absurd_values() -> None:
    assert normalize_word_count_target(None) is None
    assert normalize_word_count_target(1) == 1
    assert normalize_word_count_target(WORD_COUNT_TARGET_MAX) == WORD_COUNT_TARGET_MAX
    with pytest.raises(ValueError, match="1 到"):
        normalize_word_count_target(0)
    with pytest.raises(ValueError, match="1 到"):
        normalize_word_count_target(WORD_COUNT_TARGET_MAX + 1)
    with pytest.raises(ValueError, match="整数"):
        normalize_word_count_target(True)  # type: ignore[arg-type]


def test_progress_follows_written_count_against_the_same_target() -> None:
    assert chapter_length_progress(0, None).pace == "none"

    short = chapter_length_progress(4, 8)
    assert short.pace == "short"
    assert short.remaining == 4
    assert short.over == 0

    met = chapter_length_progress(8, 8)
    assert met.pace == "met"
    assert met.remaining == 0

    over = chapter_length_progress(11, 8)
    assert over.pace == "over"
    assert over.over == 3
    assert over.target == 8


def test_current_chapter_context_includes_target_without_adding_it_to_catalog() -> None:
    chapter = _chapter(word_count=4, word_count_target=8, content="门后有光")

    payload = json.loads(_build_latest_field(chapter, 1).content)
    assert payload["word_count"] == 4
    assert payload["word_count_target"] == 8
    assert payload["content"] == "门后有光"

    unset = json.loads(_build_latest_field(_chapter(), 1).content)
    assert "word_count_target" not in unset

    assert "word_count_target" not in catalog_plan_fields(chapter)
    listed = json.loads(
        _build_chapter_list_field([chapter], {chapter.id: 1}).content
    )
    assert "word_count_target" not in listed[0]
