# -*- coding: utf-8 -*-
"""对照计划的字面缺口、模型解析，以及过期策略。"""

from app.storage.plan_coverage import (
    BeatInput,
    StoredPlanCheck,
    build_plan_items,
    literal_report,
    parse_model_gaps,
    plan_fingerprint,
    present_check,
    render_check_prompt,
)


def _beats() -> list[BeatInput]:
    return [
        BeatInput(
            id="beat-now",
            kind="plant",
            note="灯还亮着",
            thread_name="铜镜",
            intent="灯要在后文对上",
        )
    ]


def test_literal_check_names_the_missing_half_of_the_synopsis() -> None:
    synopsis = "沈照推开门，发现「铜钥匙」。\n门外是林晚棠。"
    items = build_plan_items(synopsis, [])
    gaps, unchecked = literal_report("沈照推开门，屋里很静。", items)

    assert unchecked == []
    assert [gap.ref for gap in gaps] == ["synopsis:0", "synopsis:1"]
    assert gaps[0].plan_text == "沈照推开门，发现「铜钥匙」。"
    assert gaps[0].missing == ("铜钥匙",)
    assert gaps[0].basis == "literal"
    assert gaps[1].plan_text == "门外是林晚棠。"
    assert gaps[1].missing == ("林晚棠",)


def test_literal_check_ignores_anchors_already_in_the_prose() -> None:
    items = build_plan_items("她发现「铜钥匙」。", [])
    gaps, unchecked = literal_report("她把铜钥匙放回抽屉。", items)
    assert gaps == []
    assert unchecked == []


def test_sentence_without_anchor_is_not_a_pass() -> None:
    items = build_plan_items("结尾停在脚步声。", [])
    gaps, unchecked = literal_report("屋里很静。", items)
    assert gaps == []
    assert [line.plan_text for line in unchecked] == ["结尾停在脚步声。"]


def test_literal_check_uses_only_this_chapters_beat() -> None:
    later = BeatInput(
        id="beat-later",
        kind="payoff",
        note="镜子里是凶手",
        thread_name="铜镜",
        intent="灯要在后文对上",
    )
    items = build_plan_items("", _beats())
    assert [item.ref for item in items] == ["beat:beat-now"]
    gaps, unchecked = literal_report("沈照推开门。", items)
    assert unchecked == []
    assert gaps[0].ref == "beat:beat-now"
    assert "灯还亮着" in gaps[0].missing
    assert "铜镜" in gaps[0].missing
    assert "凶手" not in gaps[0].missing
    prompt = render_check_prompt("沈照推开门。", items)
    assert "镜子里是凶手" not in prompt[1]["content"]
    assert later.note not in prompt[1]["content"]


def test_future_intent_is_not_a_literal_gap_when_the_beat_is_on_the_page() -> None:
    items = build_plan_items("", _beats())
    gaps, unchecked = literal_report("铜镜里灯还亮着。", items)
    assert gaps == []
    assert unchecked == []


def test_model_gap_must_cite_the_plan_line() -> None:
    items = build_plan_items("门外是林晚棠。", [])
    parsed = parse_model_gaps(
        '{"gaps":[{"ref":"synopsis:0","because":"梗概写了林晚棠，正文没有这个人"}]}',
        items,
    )
    assert parsed is not None
    assert parsed[0].basis == "model"
    assert parsed[0].plan_text == "门外是林晚棠。"
    assert parsed[0].detail.startswith("梗概写了林晚棠")

    vague = parse_model_gaps(
        '{"gaps":[{"ref":"synopsis:0","because":"不够好"}]}', items
    )
    assert vague is None
    unknown = parse_model_gaps(
        '{"gaps":[{"ref":"beat:later","because":"镜子里是凶手"}]}',
        items,
    )
    assert unknown is None
    clear = parse_model_gaps('{"gaps":[]}', items)
    assert clear == []


def test_changed_prose_or_plan_marks_the_saved_check_stale() -> None:
    beats = _beats()
    synopsis = "沈照推开门。"
    content = "沈照推开门。铜镜里灯还亮着。"
    fingerprint = plan_fingerprint(content, synopsis, beats)
    stored = StoredPlanCheck(
        fingerprint=fingerprint,
        source="literal",
        gaps=literal_report(content, build_plan_items(synopsis, beats))[0],
        unchecked=(),
    )
    current = present_check(stored, fingerprint=fingerprint, has_plan=True)
    assert current.freshness == "current"
    assert current.outcome == "clear"

    changed = plan_fingerprint(content + "门外是林晚棠。", synopsis, beats)
    stale = present_check(stored, fingerprint=changed, has_plan=True)
    assert stale.freshness == "stale"
    assert stale.outcome == "clear"
    assert stale.gaps == stored.gaps

    note_changed = plan_fingerprint(
        content,
        synopsis,
        [BeatInput("beat-now", "plant", "换了备注", "铜镜", "灯要在后文对上")],
    )
    assert note_changed != fingerprint


def test_missing_plan_is_not_reported_as_clear() -> None:
    stored = StoredPlanCheck(
        fingerprint="old",
        source="literal",
        gaps=literal_report("正文", build_plan_items("门外是林晚棠。", []))[0],
        unchecked=(),
    )
    presented = present_check(stored, fingerprint="new", has_plan=False)
    assert presented.outcome == "no_plan"
    assert presented.gaps == ()
    assert presented.freshness == "stale"

    never = present_check(None, fingerprint="x", has_plan=False)
    assert never.outcome == "no_plan"
    assert never.freshness == "unchecked"
    assert never.source is None
