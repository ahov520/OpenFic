# -*- coding: utf-8 -*-
"""上一章结尾按字数口径取末尾，不取开头。"""

import pytest

from app.storage.chapter_ending import (
    PREVIOUS_ENDING_UNIT_LIMIT,
    count_units,
    tail_by_units,
)
from app.storage.services.chapter_service import _count_words


@pytest.mark.parametrize(
    "text",
    [
        "",
        "  \n",
        "你好。",
        "Hello, world",
        "门口。灯灭了。",
        "A  B\nC",
        "第1章 The end.",
    ],
)
def test_count_units_matches_chapter_word_count(text: str) -> None:
    assert count_units(text) == _count_words(text)


def test_tail_is_the_ending_not_the_opening() -> None:
    opening = "开头独有的句子在这里。"
    ending = "青鸟停在最后。"
    text = f"{opening}{'垫' * 200}{ending}"

    excerpt = tail_by_units(text)

    assert PREVIOUS_ENDING_UNIT_LIMIT == 100
    assert excerpt is not None
    assert count_units(excerpt) == PREVIOUS_ENDING_UNIT_LIMIT
    assert excerpt.endswith(ending)
    assert opening not in excerpt
    assert text.rstrip().endswith(excerpt)


def test_tail_keeps_the_last_english_words() -> None:
    words = ["alpha", "beta", *[f"w{i}" for i in range(120)], "omega-end"]
    excerpt = tail_by_units(" ".join(words), limit=3)

    assert excerpt == "w118 w119 omega-end"
    assert excerpt is not None
    assert not excerpt.startswith("alpha")


def test_short_or_empty_text() -> None:
    assert tail_by_units("") is None
    assert tail_by_units(" \n\t ") is None
    assert tail_by_units("只有一句。") == "只有一句。"
