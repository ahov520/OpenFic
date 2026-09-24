# -*- coding: utf-8 -*-
"""对照计划的字面缺口、模型解析，以及过期策略。"""

from app.storage.plan_coverage import (
    BeatInput,
    CoverageGap,
    PlanItem,
    StoredPlanCheck,
    annotate_gap_changes,
    build_plan_items,
    literal_report,
    load_payload,
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


def test_recheck_keeps_still_marks_new_and_does_not_call_a_rewrite_written() -> None:
    """梗概按原句对齐，节拍按线 id 加类型。原文改了是失效，不是不再出现。"""
    previous = (
        _gap("synopsis:0", "synopsis", "门外是林晚棠。", missing=("林晚棠",)),
        _gap("synopsis:1", "synopsis", "沈照发现「铜钥匙」。", missing=("铜钥匙",)),
        _gap(
            "beat:old",
            "beat",
            "灯还亮着",
            missing=("灯还亮着",),
            beat_kind="plant",
            thread_name="铜镜",
            thread_id="thread-1",
        ),
    )
    current = [
        _gap("synopsis:4", "synopsis", "门外是林晚棠。", missing=("林晚棠",)),
        _gap("synopsis:5", "synopsis", "桌上是周明远。", missing=("周明远",)),
        _gap(
            "beat:old",
            "beat",
            "窗还开着",
            missing=("窗还开着",),
            beat_kind="plant",
            thread_name="另一面镜子",
            thread_id="thread-1",
        ),
    ]
    items = [
        PlanItem("synopsis:3", "synopsis", "天亮以前。"),
        PlanItem("synopsis:4", "synopsis", "门外是林晚棠。"),
        PlanItem("synopsis:5", "synopsis", "桌上是周明远。"),
        PlanItem("synopsis:6", "synopsis", "沈照发现「铜钥匙」。"),
        PlanItem(
            "beat:old",
            "beat",
            "窗还开着",
            beat_kind="plant",
            thread_name="另一面镜子",
            thread_id="thread-1",
        ),
    ]
    aligned = annotate_gap_changes(previous, current, items)
    by_text = {gap.plan_text: gap.change for gap in aligned}
    assert by_text["门外是林晚棠。"] == "still"
    assert by_text["桌上是周明远。"] == "new"
    assert by_text["沈照发现「铜钥匙」。"] == "gone"
    assert by_text["窗还开着"] == "still"
    assert "灯还亮着" not in by_text
    assert aligned[0].ref == "synopsis:4"

    rewritten = annotate_gap_changes(
        (_gap("synopsis:0", "synopsis", "门外是林晚棠。", missing=("林晚棠",)),),
        [],
        [PlanItem("synopsis:0", "synopsis", "门口只剩风声。")],
    )
    assert [gap.change for gap in rewritten] == ["invalidated"]
    assert rewritten[0].plan_text == "门外是林晚棠。"

    kind_changed = annotate_gap_changes(
        (
            _gap(
                "beat:old",
                "beat",
                "灯还亮着",
                missing=("灯还亮着",),
                beat_kind="plant",
                thread_id="thread-1",
            ),
        ),
        [
            _gap(
                "beat:old",
                "beat",
                "灯还亮着",
                missing=("灯还亮着",),
                beat_kind="advance",
                thread_id="thread-1",
            )
        ],
        [
            PlanItem(
                "beat:old",
                "beat",
                "灯还亮着",
                beat_kind="advance",
                thread_id="thread-1",
            )
        ],
    )
    assert [(gap.beat_kind, gap.change) for gap in kind_changed] == [
        ("advance", "new"),
        ("plant", "invalidated"),
    ]


def test_closed_rows_are_not_treated_as_the_previous_open_gaps() -> None:
    previous = (
        _gap(
            "synopsis:0",
            "synopsis",
            "门外是林晚棠。",
            missing=("林晚棠",),
            change="gone",
        ),
        _gap(
            "synopsis:1",
            "synopsis",
            "沈照发现「铜钥匙」。",
            missing=("铜钥匙",),
            change="still",
        ),
    )
    items = [
        PlanItem("synopsis:0", "synopsis", "门外是林晚棠。"),
        PlanItem("synopsis:1", "synopsis", "沈照发现「铜钥匙」。"),
    ]
    aligned = annotate_gap_changes(previous, [], items)
    assert [(gap.plan_text, gap.change) for gap in aligned] == [
        ("沈照发现「铜钥匙」。", "gone")
    ]


def test_gap_without_a_thread_id_cannot_be_counted_as_written() -> None:
    previous = (
        _gap(
            "beat:old",
            "beat",
            "灯还亮着",
            missing=("灯还亮着",),
            beat_kind="plant",
            thread_name="铜镜",
        ),
    )
    items = [
        PlanItem(
            "beat:old",
            "beat",
            "灯还亮着",
            beat_kind="plant",
            thread_name="铜镜",
            thread_id="thread-1",
        )
    ]
    aligned = annotate_gap_changes(previous, [], items)
    assert [gap.change for gap in aligned] == ["invalidated"]


def test_old_payload_without_change_still_loads() -> None:
    loaded = load_payload(
        '{"version":1,"gaps":[{"ref":"synopsis:0","origin":"synopsis",'
        '"plan_text":"门外是林晚棠。","basis":"literal","missing":["林晚棠"],'
        '"detail":"","beat_kind":null,"thread_name":null}],"unchecked":[]}'
    )
    assert loaded is not None
    gap = loaded[0][0]
    assert gap.change is None
    assert gap.thread_id is None
    assert gap.missing == ("林晚棠",)


def test_only_gone_gaps_are_not_an_open_failure() -> None:
    stored = StoredPlanCheck(
        fingerprint="same",
        source="literal",
        gaps=(
            _gap(
                "synopsis:0",
                "synopsis",
                "门外是林晚棠。",
                missing=("林晚棠",),
                change="gone",
            ),
        ),
        unchecked=(),
    )
    presented = present_check(stored, fingerprint="same", has_plan=True)
    assert presented.outcome == "clear"
    assert presented.gaps[0].change == "gone"


def _gap(
    ref: str,
    origin: str,
    plan_text: str,
    *,
    missing: tuple[str, ...] = (),
    beat_kind: str | None = None,
    thread_name: str | None = None,
    thread_id: str | None = None,
    change: str | None = None,
) -> CoverageGap:
    return CoverageGap(
        ref=ref,
        origin=origin,
        plan_text=plan_text,
        basis="literal",
        missing=missing,
        beat_kind=beat_kind,
        thread_name=thread_name,
        thread_id=thread_id,
        change=change,
    )
