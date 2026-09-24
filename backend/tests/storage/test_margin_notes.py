# -*- coding: utf-8 -*-
"""旁注锚点：对得上才给出位置，对不上就不要指向另一句。"""

from app.storage.margin_notes import (
    MARGIN_NOTE_NOTICE,
    agent_margin_payload,
    locate_anchor,
    normalize_anchor,
)
from app.storage.models.margin_note import ChapterMarginNote


def test_unique_sentence_stays_found_when_surrounding_text_changes() -> None:
    original = "走廊很暗。他推开门。灯还亮着。"
    edited = "走廊里只剩风声。他推开门。灯已经灭了。"
    hit = locate_anchor(edited, "他推开门。", "走廊很暗。", "灯还亮着。")
    assert hit.aligned is True
    assert edited[hit.start : hit.end] == "他推开门。"
    assert original != edited


def test_missing_sentence_is_misaligned_without_a_position() -> None:
    hit = locate_anchor("他关上了门。", "他推开门。", "走廊很暗。", "灯还亮着。")
    assert hit.aligned is False
    assert hit.start is None
    assert hit.end is None


def test_duplicate_sentence_uses_context_and_refuses_the_other_copy() -> None:
    content = "他推开门。灯还亮着。他推开门。外面在下雨。"
    first = locate_anchor(content, "他推开门。", "", "灯还亮着。")
    second = locate_anchor(content, "他推开门。", "灯还亮着。", "外面在下雨。")
    assert content[first.start : first.end] == "他推开门。"
    assert first.start == 0
    assert second.start == content.rfind("他推开门。")
    assert first.start != second.start


def test_duplicate_sentence_without_matching_context_is_not_highlighted() -> None:
    content = "他推开门。灯还亮着。他推开门。外面在下雨。"
    hit = locate_anchor(content, "他推开门。", "原先的前文。", "原先的后文。")
    assert hit.aligned is False
    assert hit.start is None


def test_empty_selection_is_rejected() -> None:
    try:
        normalize_anchor("   \n")
    except ValueError as error:
        assert "选中" in str(error)
    else:
        raise AssertionError("空选区应该被拒绝")


def test_agent_payload_keeps_open_notes_out_of_a_body_field() -> None:
    notes = [
        ChapterMarginNote(
            project_id="p",
            chapter_id="c",
            anchor_text="他推开门。",
            body="这句先别删，动机不清楚。",
            status="open",
        ),
        ChapterMarginNote(
            project_id="p",
            chapter_id="c",
            anchor_text="灯还亮着。",
            body="已经改过，划掉。",
            status="struck",
        ),
    ]
    payload = agent_margin_payload(notes)
    assert payload is not None
    assert payload["notice"] == MARGIN_NOTE_NOTICE
    assert "不是正文" in str(payload["notice"])
    assert payload["notes"] == [
        {"anchor": "他推开门。", "note": "这句先别删，动机不清楚。"}
    ]
    assert "content" not in payload
    assert agent_margin_payload([notes[1]]) is None
