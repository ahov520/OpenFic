# -*- coding: utf-8 -*-
"""情节线的断线判断、存储，以及给 Agent 的短计划。"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError
from app.storage.models.chapter import Chapter
from app.storage.models.project import Project
from app.storage.models.volume import Volume
from app.storage.plot_threads import (
    CONSIDER_ADVANCE_NOTE,
    GAP_CHAPTER_PREVIEW,
    OPEN_THREAD_LIMIT,
    PLOT_PLAN_NOTICE,
    STALE_CHAPTER_GAP,
    ChapterSpot,
    agent_plot_context,
    assess_plot_threads,
    gaps_through_chapter,
    normalize_beat_kind,
    normalize_intent,
    normalize_thread_name,
    normalize_thread_status,
    reading_order_of,
    open_planted_names_by_chapter,
    select_board_threads,
)
from app.storage.services import plot_thread_service


def _spot(chapter_id: str, order: int, title: str) -> ChapterSpot:
    return ChapterSpot(
        id=chapter_id,
        title=title,
        global_order=order,
        volume_title="第一卷",
    )


def _assess(
    threads: list[tuple[str, str, str, str, int]],
    beats: list[tuple[str, str, str, str, str]],
):
    chapters = [_spot("c1", 1, "夜航"), _spot("c2", 2, "旧伤"), _spot("c3", 3, "对上")]
    return {item.name: item for item in assess_plot_threads(threads, beats, chapters)}


def test_normalize_thread_fields() -> None:
    assert normalize_thread_status(None) == "active"
    assert normalize_thread_status("abandoned") == "abandoned"
    assert normalize_thread_name("  铜镜  ") == "铜镜"
    assert normalize_intent("灯还亮着。\n后文再收") == "灯还亮着。 后文再收"
    assert normalize_beat_kind("payoff") == "payoff"
    with pytest.raises(ValueError):
        normalize_thread_status("done")
    with pytest.raises(ValueError):
        normalize_thread_name("  ")
    with pytest.raises(ValueError):
        normalize_beat_kind("hint")
    with pytest.raises(ValueError):
        normalize_intent("意" * 201)


def test_open_thread_and_structural_problems() -> None:
    threads = [
        ("t-open", "铜镜", "灯要在后文对上", "active", 1),
        ("t-payoff", "旧信", "信要被读到", "active", 2),
        ("t-bare", "空线", "还没想好", "active", 3),
        ("t-drop", "放弃的线", "不再用", "abandoned", 4),
        ("t-early", "倒序", "先收后埋", "active", 5),
        ("t-marked", "假回收", "作者标了回收", "resolved", 6),
        ("t-advance", "没埋就推", "推进缺埋下", "active", 7),
    ]
    beats = [
        ("b1", "t-open", "c1", "plant", "灯还亮着"),
        ("b2", "t-open", "c2", "advance", "有人提起镜子"),
        ("b3", "t-payoff", "c1", "plant", "信压在灯下"),
        ("b4", "t-payoff", "c3", "payoff", "信被读完"),
        ("b5", "t-early", "c2", "payoff", "提前说破"),
        ("b6", "t-early", "c3", "plant", "这才埋下"),
        ("b7", "t-advance", "c1", "advance", "直接往前推"),
        ("b8", "t-drop", "c1", "plant", "后来不用了"),
    ]

    found = _assess(threads, beats)
    mirror = found["铜镜"]
    assert mirror.issues == ("open",)
    assert mirror.last_beat is not None
    assert mirror.last_beat.chapter_title == "旧伤"
    assert mirror.last_beat.kind == "advance"
    assert mirror.has_plant is True
    assert mirror.has_payoff is False
    assert mirror.chapters_since_last == 0
    assert mirror.gap_chapters == ()
    assert mirror.gap_range is None

    letter = found["旧信"]
    assert "open" not in letter.issues
    assert letter.issues == ("payoff_still_active",)
    assert letter.last_beat is not None
    assert letter.last_beat.global_order == 3
    assert letter.chapters_since_last is None
    assert letter.gap_chapters == ()

    assert found["空线"].issues == ("open",)
    assert found["空线"].last_beat is None
    assert found["空线"].chapters_since_last is None
    assert found["空线"].gap_chapters == ()
    assert found["放弃的线"].issues == ()
    assert found["放弃的线"].chapters_since_last is None
    assert found["放弃的线"].gap_chapters == ()
    assert found["倒序"].issues == ("payoff_before_plant", "payoff_still_active")
    assert found["倒序"].chapters_since_last is None
    assert found["倒序"].gap_chapters == ()
    assert found["假回收"].issues == ("resolved_without_payoff",)
    assert found["假回收"].chapters_since_last is None
    assert found["假回收"].gap_chapters == ()
    assert found["没埋就推"].issues == ("advance_without_plant", "open")
    assert found["没埋就推"].chapters_since_last == 1
    assert [chapter.id for chapter in found["没埋就推"].gap_chapters] == ["c2"]
    assert found["没埋就推"].gap_chapters[0].label == "2. 旧伤"


def test_gap_counts_chapters_between_not_order_numbers() -> None:
    """global_order 可以不连续。空档按排好的章节个数算，不拿序号相减。"""
    chapters = [
        _spot("c-end", 200, "结局"),
        _spot("c-plant", 1, "埋下"),
        _spot("c-mid", 40, "中间"),
    ]
    assert reading_order_of(chapters) == ["c-plant", "c-mid", "c-end"]
    found = {
        item.name: item
        for item in assess_plot_threads(
            [
                ("t-open", "铜镜", "还没收", "active", 1),
                ("t-near", "刚过", "上一章才见", "active", 2),
                ("t-only", "独章", "就这一章", "active", 3),
            ],
            [
                ("b1", "t-open", "c-plant", "plant", "灯"),
                ("b2", "t-near", "c-mid", "plant", "刚提起"),
                ("b3", "t-only", "c-end", "plant", "结局才出现"),
            ],
            chapters,
        )
    }
    assert found["铜镜"].chapters_since_last == 1
    assert [chapter.id for chapter in found["铜镜"].gap_chapters] == ["c-mid"]
    assert found["铜镜"].gap_chapters[0].label == "40. 中间"
    assert found["刚过"].chapters_since_last == 0
    assert found["刚过"].gap_chapters == ()
    assert found["独章"].chapters_since_last is None
    assert found["独章"].gap_chapters == ()

    alone = assess_plot_threads(
        [("t1", "只有一章", "埋在这里", "active", 1)],
        [("b1", "t1", "solo", "plant", "灯")],
        [_spot("solo", 9, "仅有")],
    )[0]
    assert alone.chapters_since_last is None


def test_resolved_and_abandoned_are_not_marked_cold() -> None:
    chapters = [_spot("c1", 1, "埋下"), _spot("c2", 2, "空"), _spot("c3", 3, "结局")]
    found = {
        item.name: item
        for item in assess_plot_threads(
            [
                ("t-open", "还开着", "没收", "active", 1),
                ("t-done", "已收", "收完了", "resolved", 2),
                ("t-drop", "放弃", "不用了", "abandoned", 3),
                ("t-early", "倒序", "先收后埋", "active", 4),
            ],
            [
                ("b1", "t-open", "c1", "plant", "灯"),
                ("b2", "t-done", "c1", "plant", "埋"),
                ("b3", "t-done", "c1", "payoff", "收"),
                ("b4", "t-drop", "c1", "plant", "后来不用"),
                ("b5", "t-early", "c2", "payoff", "提前说破"),
                ("b6", "t-early", "c3", "plant", "这才埋下"),
            ],
            chapters,
        )
    }
    assert found["还开着"].chapters_since_last == 1
    assert [chapter.label for chapter in found["还开着"].gap_chapters] == ["2. 空"]
    assert found["已收"].chapters_since_last is None
    assert found["已收"].issues == ()
    assert found["已收"].gap_chapters == ()
    assert found["放弃"].chapters_since_last is None
    assert found["放弃"].issues == ()
    assert found["放弃"].gap_chapters == ()
    assert found["倒序"].issues == ("payoff_before_plant", "payoff_still_active")
    assert found["倒序"].chapters_since_last is None
    assert found["倒序"].gap_chapters == ()


def test_gap_chapters_skip_last_beat_and_follow_reading_order() -> None:
    """最后一次出现的那一章不进空档。中间后来又推进过的章，也不算在它前面的空章里。"""
    chapters = [
        _spot("c5", 5, "结局"),
        _spot("c1", 1, "埋下"),
        _spot("c4", 4, "空二"),
        _spot("c2", 2, "  "),
        _spot("c3", 3, "推进"),
    ]
    found = {
        item.name: item
        for item in assess_plot_threads(
            [
                ("t-open", "铜镜", "还没收", "active", 1),
                ("t-near", "刚过", "结局前一章", "active", 2),
                ("t-done", "已收", "收完了", "resolved", 3),
            ],
            [
                ("b1", "t-open", "c1", "plant", "灯"),
                ("b2", "t-open", "c3", "advance", "又提起"),
                ("b3", "t-near", "c4", "plant", "刚出现"),
                ("b4", "t-done", "c1", "plant", "埋"),
                ("b5", "t-done", "c2", "payoff", "收"),
            ],
            chapters,
        )
    }
    mirror = found["铜镜"]
    assert mirror.chapters_since_last == 1
    assert [chapter.id for chapter in mirror.gap_chapters] == ["c4"]
    assert mirror.gap_chapters[0].label == "4. 空二"
    assert "c1" not in [chapter.id for chapter in mirror.gap_chapters]
    assert "c3" not in [chapter.id for chapter in mirror.gap_chapters]
    assert "c5" not in [chapter.id for chapter in mirror.gap_chapters]
    assert found["刚过"].chapters_since_last == 0
    assert found["刚过"].gap_chapters == ()
    assert found["已收"].gap_chapters == ()

    blank = assess_plot_threads(
        [("t1", "空标题", "还没收", "active", 1)],
        [("b1", "t1", "c1", "plant", "灯")],
        [_spot("c1", 1, "埋下"), _spot("c2", 2, "  "), _spot("c3", 3, "结局")],
    )[0]
    assert blank.gap_chapters[0].label == "2. 未命名章节"


def test_gap_chapters_use_volume_order_not_ids() -> None:
    """id 按字母会把后卷排到前面。空章仍按卷序，不含作为终点的卷末。"""
    chapters = [
        ChapterSpot(
            id="z-later", title="后卷章", global_order=2, volume_title="第二卷"
        ),
        ChapterSpot(
            id="a-early", title="前卷章", global_order=1, volume_title="第一卷"
        ),
        ChapterSpot(id="m-end", title="卷末", global_order=3, volume_title="第二卷"),
    ]
    assert reading_order_of(chapters) == ["a-early", "z-later", "m-end"]
    found = assess_plot_threads(
        [("t1", "铜镜", "还没收", "active", 1)],
        [("b1", "t1", "a-early", "plant", "灯")],
        chapters,
    )[0]
    assert found.chapters_since_last == 1
    assert [(chapter.id, chapter.label) for chapter in found.gap_chapters] == [
        ("z-later", "2. 后卷章")
    ]
    assert found.gap_range is None


def test_gap_range_collapses_only_after_four_chapters() -> None:
    """不超过 4 章逐章列出；第 5 章起默认收成首尾范围，完整名单仍按阅读顺序留着。"""
    assert GAP_CHAPTER_PREVIEW == 4

    def opened(count: int):
        chapters = [
            _spot(f"c{index}", index, f"第{index}章") for index in range(1, count + 1)
        ]
        return assess_plot_threads(
            [("t1", "铜镜", "还没收", "active", 1)],
            [("b1", "t1", "c1", "plant", "灯")],
            chapters,
        )[0]

    within = opened(6)
    assert within.chapters_since_last == 4
    assert len(within.gap_chapters) == 4
    assert [chapter.label for chapter in within.gap_chapters] == [
        "2. 第2章",
        "3. 第3章",
        "4. 第4章",
        "5. 第5章",
    ]
    assert within.gap_chapters[0].id == "c2"
    assert within.gap_chapters[-1].id != "c6"
    assert within.gap_range is None

    beyond = opened(7)
    assert beyond.chapters_since_last == 5
    assert [chapter.id for chapter in beyond.gap_chapters] == [
        "c2",
        "c3",
        "c4",
        "c5",
        "c6",
    ]
    assert beyond.gap_range == "2. 第2章 → 6. 第6章"
    assert "c1" not in beyond.gap_range
    assert "c7" not in beyond.gap_range


def test_default_board_keeps_long_gap_threads_without_structural_issues() -> None:
    """默认先看有问题的线。只隔得久、没有结构错误的未回收线仍在这份名单里。"""
    chapters = [
        _spot("c1", 1, "埋下"),
        _spot("c2", 10, "二"),
        _spot("c3", 11, "三"),
        _spot("c4", 90, "四"),
        _spot("c5", 200, "结局"),
    ]
    assessments = assess_plot_threads(
        [
            ("t-cold", "凉了", "隔很久但没写错", "active", 1),
            ("t-fresh", "刚出现", "上一章才见", "active", 2),
            ("t-bare", "没埋就推", "推进缺埋下", "active", 3),
            ("t-early", "倒序", "先收后埋", "active", 4),
            ("t-done", "已收", "收完了", "resolved", 5),
            ("t-drop", "放弃", "不用了", "abandoned", 6),
            ("t-fake", "标了回收", "没有回收节拍", "resolved", 7),
        ],
        [
            ("b1", "t-cold", "c1", "plant", "灯"),
            ("b2", "t-fresh", "c4", "plant", "刚提起"),
            ("b3", "t-bare", "c1", "advance", "直接往前推"),
            ("b4", "t-early", "c2", "payoff", "提前说破"),
            ("b5", "t-early", "c3", "plant", "这才埋下"),
            ("b6", "t-done", "c1", "plant", "埋"),
            ("b7", "t-done", "c2", "payoff", "收"),
            ("b8", "t-drop", "c1", "plant", "后来不用"),
        ],
        chapters,
    )
    by_name = {item.name: item for item in assessments}
    assert by_name["凉了"].issues == ("open",)
    assert by_name["凉了"].chapters_since_last == 3
    assert by_name["刚出现"].chapters_since_last == 0
    assert by_name["已收"].chapters_since_last is None

    default_names = [item.name for item in select_board_threads(assessments, "issues")]
    assert default_names == ["倒序", "凉了", "没埋就推", "刚出现", "标了回收"]
    assert "已收" not in default_names
    assert "放弃" not in default_names
    assert default_names.index("倒序") < default_names.index("凉了")
    assert default_names.index("凉了") < default_names.index("刚出现")

    quiet_names = [item.name for item in select_board_threads(assessments, "quiet")]
    assert quiet_names == ["凉了", "没埋就推", "刚出现"]


def test_agent_context_gap_differs_from_book_end_around_threshold() -> None:
    chapters = [
        _spot("c1", 1, "埋下"),
        _spot("c2", 8, "二"),
        _spot("c3", 9, "三"),
        _spot("c4", 20, "四"),
        _spot("c5", 21, "五"),
        _spot("c6", 100, "结局"),
    ]
    reading = reading_order_of(chapters)
    assessments = assess_plot_threads(
        [
            ("t1", "铜镜", "还没收", "active", 1),
            ("t2", "后文", "以后才收", "active", 2),
            ("t3", "已收", "收完了", "resolved", 3),
        ],
        [
            ("b1", "t1", "c1", "plant", "灯还亮着"),
            ("b2", "t2", "c1", "plant", "先埋下"),
            ("b3", "t2", "c6", "payoff", "镜子里是凶手"),
            ("b4", "t3", "c1", "plant", "埋"),
            ("b5", "t3", "c2", "payoff", "收"),
        ],
        chapters,
    )
    by_name = {item.name: item for item in assessments}
    assert by_name["铜镜"].chapters_since_last == 4
    assert by_name["后文"].chapters_since_last is None
    assert STALE_CHAPTER_GAP == 3

    def open_thread(payload: dict[str, object], name: str) -> dict[str, object]:
        found = next(item for item in payload["open_threads"] if item["thread"] == name)
        assert isinstance(found, dict)
        return found

    previous = agent_plot_context(
        current_chapter_id="c2",
        current_global_order=8,
        assessments=assessments,
        reading_order=reading,
        chapters=chapters,
    )
    assert previous is not None
    just_seen = open_thread(previous, "铜镜")
    assert just_seen["chapters_since"] == 0
    assert "consider_advance" not in just_seen
    assert "gap_chapters" not in just_seen

    below = agent_plot_context(
        current_chapter_id="c4",
        current_global_order=20,
        assessments=assessments,
        reading_order=reading,
        chapters=chapters,
    )
    assert below is not None
    below_mirror = open_thread(below, "铜镜")
    assert below_mirror["chapters_since"] == 2
    assert "consider_advance" not in below_mirror
    assert below_mirror["chapters_since"] != by_name["铜镜"].chapters_since_last
    assert below_mirror["gap_chapters"] == ["8. 二", "9. 三"]
    assert "gap_more" not in below_mirror
    assert "20. 四" not in below_mirror["gap_chapters"]
    assert "21. 五" not in below_mirror["gap_chapters"]
    assert "100. 结局" not in below_mirror["gap_chapters"]

    at_threshold = agent_plot_context(
        current_chapter_id="c5",
        current_global_order=21,
        assessments=assessments,
        reading_order=reading,
        chapters=chapters,
    )
    assert at_threshold is not None
    stale = open_thread(at_threshold, "铜镜")
    assert stale["chapters_since"] == 3
    assert stale["consider_advance"] == CONSIDER_ADVANCE_NOTE
    assert stale["gap_chapters"] == ["8. 二", "9. 三", "20. 四"]
    assert "100. 结局" not in stale["gap_chapters"]
    assert "1. 埋下" not in stale["gap_chapters"]
    later = open_thread(at_threshold, "后文")
    assert later["chapters_since"] == 3
    assert later["consider_advance"] == CONSIDER_ADVANCE_NOTE
    assert later["gap_chapters"] == ["8. 二", "9. 三", "20. 四"]
    rendered = str(at_threshold)
    assert "镜子里是凶手" not in rendered
    assert "已收" not in rendered
    assert "收完了" not in rendered

    on_the_beat = agent_plot_context(
        current_chapter_id="c1",
        current_global_order=1,
        assessments=assessments,
        reading_order=reading,
    )
    assert on_the_beat is not None
    planted_here = open_thread(on_the_beat, "铜镜")
    assert "chapters_since" not in planted_here
    assert "consider_advance" not in planted_here


def test_gaps_through_chapter_stop_before_current_and_follow_inserts() -> None:
    """到当前章的空章不含两端和后文，和数到全书末的名单不同；插章后名单变。"""
    chapters = [
        _spot("late", 4, "当前"),
        _spot("after", 5, "后文"),
        _spot("end", 6, "结局"),
        _spot("planted", 1, "埋下"),
        _spot("gap-a", 2, "空甲"),
        _spot("gap-b", 3, "空乙"),
    ]
    reading = reading_order_of(chapters)
    threads = [
        ("t1", "铜镜", "还没收", "active", 1),
        ("t2", "已收", "收完了", "resolved", 2),
        ("t3", "放弃", "不用了", "abandoned", 3),
        ("t4", "早收", "中途收了", "active", 4),
        ("t5", "后文才收", "结局才收", "active", 5),
    ]
    beats = [
        ("b1", "t1", "planted", "plant", "灯"),
        ("b2", "t2", "planted", "plant", "埋"),
        ("b3", "t2", "gap-a", "payoff", "收"),
        ("b4", "t3", "planted", "plant", "弃"),
        ("b5", "t4", "planted", "plant", "埋"),
        ("b6", "t4", "gap-a", "payoff", "本章说破"),
        ("b7", "t5", "planted", "plant", "先埋下"),
        ("b8", "t5", "end", "payoff", "镜子里是凶手"),
    ]
    assessments = assess_plot_threads(threads, beats, chapters)
    by_name = {item.name: item for item in assessments}
    book_ids = [chapter.id for chapter in by_name["铜镜"].gap_chapters]
    assert book_ids == ["gap-a", "gap-b", "late", "after"]
    assert by_name["后文才收"].gap_chapters == ()

    through = {
        item.thread_id: item
        for item in gaps_through_chapter(assessments, chapters, reading, "late")
    }
    mirror = through["t1"]
    assert mirror.chapters_since == 2
    assert [chapter.id for chapter in mirror.gap_chapters] == ["gap-a", "gap-b"]
    assert [chapter.label for chapter in mirror.gap_chapters] == ["2. 空甲", "3. 空乙"]
    assert mirror.gap_range is None
    assert "planted" not in [chapter.id for chapter in mirror.gap_chapters]
    assert "late" not in [chapter.id for chapter in mirror.gap_chapters]
    assert "after" not in [chapter.id for chapter in mirror.gap_chapters]
    assert "end" not in [chapter.id for chapter in mirror.gap_chapters]
    assert [chapter.id for chapter in mirror.gap_chapters] != book_ids
    later_payoff = through["t5"]
    assert [chapter.id for chapter in later_payoff.gap_chapters] == ["gap-a", "gap-b"]
    assert "t2" not in through
    assert "t3" not in through
    assert "t4" not in through

    adjacent = {
        item.thread_id: item
        for item in gaps_through_chapter(assessments, chapters, reading, "gap-a")
    }
    assert adjacent["t1"].chapters_since == 0
    assert adjacent["t1"].gap_chapters == ()
    assert adjacent["t1"].gap_range is None
    assert "t4" not in adjacent

    widened = [
        _spot("planted", 1, "埋下"),
        _spot("inserted", 2, "插章"),
        _spot("gap-a", 3, "空甲"),
        _spot("gap-b", 4, "空乙"),
        _spot("late", 5, "当前"),
        _spot("after", 6, "后文"),
        _spot("end", 7, "结局"),
    ]
    widened_reading = reading_order_of(widened)
    widened_assessments = assess_plot_threads(threads, beats, widened)
    widened_through = {
        item.thread_id: item
        for item in gaps_through_chapter(
            widened_assessments, widened, widened_reading, "late"
        )
    }
    assert [chapter.id for chapter in widened_through["t1"].gap_chapters] == [
        "inserted",
        "gap-a",
        "gap-b",
    ]
    assert [chapter.label for chapter in widened_through["t1"].gap_chapters] == [
        "2. 插章",
        "3. 空甲",
        "4. 空乙",
    ]
    assert "after" not in [chapter.id for chapter in widened_through["t1"].gap_chapters]


def test_agent_context_limits_gap_names_and_hides_later_chapters() -> None:
    chapters = [
        _spot(f"c{index}", index, title)
        for index, title in enumerate(
            ("埋下", "二", "三", "四", "五", "六", "当前", "后文密章"),
            start=1,
        )
    ]
    reading = reading_order_of(chapters)
    assessments = assess_plot_threads(
        [("t1", "铜镜", "还没收", "active", 1)],
        [
            ("b1", "t1", "c1", "plant", "灯还亮着"),
            ("b2", "t1", "c8", "payoff", "镜子里是凶手"),
        ],
        chapters,
    )
    assert assessments[0].gap_chapters == ()
    payload = agent_plot_context(
        current_chapter_id="c7",
        current_global_order=7,
        assessments=assessments,
        reading_order=reading,
        chapters=chapters,
    )
    assert payload is not None
    mirror = next(item for item in payload["open_threads"] if item["thread"] == "铜镜")
    assert mirror["chapters_since"] == 5
    assert mirror["gap_chapters"] == ["2. 二", "3. 三", "4. 四", "5. 五"]
    assert mirror["gap_more"] == "还有 1 章"
    assert "6. 六" not in mirror["gap_chapters"]
    assert "7. 当前" not in mirror["gap_chapters"]
    assert "1. 埋下" not in mirror["gap_chapters"]
    rendered = str(payload)
    assert "后文密章" not in rendered
    assert "镜子里是凶手" not in rendered


def test_payoff_without_any_plant() -> None:
    found = _assess(
        [("t1", "直接收", "没有埋", "resolved", 1)],
        [("b1", "t1", "c2", "payoff", "忽然说破")],
    )
    assert found["直接收"].issues == ("payoff_without_plant",)


def test_agent_context_hides_future_notes_and_limits_length() -> None:
    chapters = [_spot("c1", 1, "夜航"), _spot("c3", 3, "对上")]
    long_intent = "意" * 100
    assessments = assess_plot_threads(
        [
            ("t1", "铜镜", long_intent, "active", 1),
            ("t2", "后文才出现", "现在不该看见", "active", 2),
            ("t3", "已经收了", "本章回收", "active", 3),
        ],
        [
            ("b1", "t1", "c1", "plant", "灯还亮着"),
            ("b2", "t1", "c3", "payoff", "镜子里是凶手"),
            ("b3", "t2", "c3", "plant", "未来的埋下"),
            ("b4", "t3", "c1", "payoff", "本章说破"),
        ],
        chapters,
    )

    early = agent_plot_context(
        current_chapter_id="c1",
        current_global_order=1,
        assessments=assessments,
    )
    assert early is not None
    rendered = str(early)
    assert PLOT_PLAN_NOTICE in rendered
    assert "镜子里是凶手" not in rendered
    assert "未来的埋下" not in rendered
    assert "后文才出现" not in rendered
    beats = early["chapter_beats"]
    assert isinstance(beats, list)
    kinds = {item["thread"]: item["kind"] for item in beats}
    assert kinds == {"铜镜": "plant", "已经收了": "payoff"}
    open_names = [item["thread"] for item in early["open_threads"]]
    assert open_names == ["铜镜"]
    mirror = early["open_threads"][0]
    assert mirror["last_kind"] == "plant"
    assert mirror["last_order"] == 1
    assert mirror["intent"].endswith("…")
    assert len(mirror["intent"]) == 80

    later = agent_plot_context(
        current_chapter_id="c3",
        current_global_order=3,
        assessments=assessments,
    )
    assert later is not None
    later_open = [item["thread"] for item in later["open_threads"]]
    assert "铜镜" not in later_open
    assert "后文才出现" in later_open
    assert "镜子里是凶手" in str(later["chapter_beats"])


def test_agent_context_omits_extra_open_threads() -> None:
    threads = [
        (f"t{index}", f"线{index}", "还没收", "active", index)
        for index in range(OPEN_THREAD_LIMIT + 3)
    ]
    beats = [
        (f"b{index}", f"t{index}", "c1", "plant", "")
        for index in range(OPEN_THREAD_LIMIT + 3)
    ]
    assessments = assess_plot_threads(
        threads,
        beats,
        [_spot("c1", 1, "夜航")],
    )
    payload = agent_plot_context(
        current_chapter_id="c1",
        current_global_order=1,
        assessments=assessments,
    )
    assert payload is not None
    assert len(payload["open_threads"]) == OPEN_THREAD_LIMIT
    assert payload["open_omitted"] == 3
    assert len(payload["chapter_beats"]) == 12


def test_agent_context_is_empty_without_relevant_threads() -> None:
    assessments = assess_plot_threads(
        [("t1", "已收", "完了", "resolved", 1)],
        [("b1", "t1", "c1", "plant", "埋"), ("b2", "t1", "c1", "payoff", "收")],
        [_spot("c2", 2, "另一章")],
    )
    assert (
        agent_plot_context(
            current_chapter_id="c2",
            current_global_order=2,
            assessments=assessments,
        )
        is None
    )


async def _project_with_chapters(
    session: AsyncSession,
) -> tuple[Project, list[Chapter]]:
    project = Project(title="长篇", description="")
    session.add(project)
    await session.flush()
    volume = Volume(project_id=project.id, title="第一卷", order=1)
    session.add(volume)
    await session.flush()
    chapters = []
    for order, title in ((1, "夜航"), (2, "对上")):
        chapter = Chapter(
            project_id=project.id,
            volume_id=volume.id,
            title=title,
            content="正文",
            order=order,
            word_count=2,
        )
        session.add(chapter)
        chapters.append(chapter)
    await session.flush()
    return project, chapters


@pytest.mark.asyncio
async def test_thread_beats_roundtrip_and_reject_duplicate(
    session: AsyncSession,
) -> None:
    project, chapters = await _project_with_chapters(session)
    thread = await plot_thread_service.create_thread(
        session,
        project.id,
        name="铜镜",
        intent="灯要在后文对上",
    )
    await plot_thread_service.create_beat(
        session,
        thread.id,
        chapter_id=chapters[0].id,
        kind="plant",
        note="灯还亮着",
    )
    await plot_thread_service.create_beat(
        session,
        thread.id,
        chapter_id=chapters[1].id,
        kind="payoff",
        note="镜子里是凶手",
    )

    board = await plot_thread_service.get_board(session, project.id)
    assert len(board.threads) == 1
    assessment = board.threads[0].assessment
    assert assessment.has_plant is True
    assert assessment.has_payoff is True
    assert assessment.issues == ("payoff_still_active",)
    assert [beat.kind for beat in assessment.beats] == ["plant", "payoff"]

    with pytest.raises(ConflictError):
        await plot_thread_service.create_beat(
            session,
            thread.id,
            chapter_id=chapters[0].id,
            kind="advance",
            note="重复",
        )

    updated = await plot_thread_service.update_thread(
        session, thread.id, status="resolved"
    )
    assert updated.status == "resolved"
    resolved = await plot_thread_service.get_board(session, project.id)
    assert resolved.threads[0].assessment.issues == ()

    await plot_thread_service.delete_thread(session, thread.id)
    empty = await plot_thread_service.get_board(session, project.id)
    assert empty.threads == []
    assert empty.beats == {}


def _chapter(project_id: str, volume_id: str, title: str, order: int) -> Chapter:
    return Chapter(
        project_id=project_id,
        volume_id=volume_id,
        title=title,
        content="正文",
        order=order,
        word_count=2,
    )


@pytest.mark.asyncio
async def test_gap_follows_reading_order_when_chapters_are_inserted(
    session: AsyncSession,
) -> None:
    """空档按卷序和卷内章节序数。空卷不计，插进中间的章要算上。"""
    project = Project(title="长篇", description="")
    session.add(project)
    await session.flush()
    first = Volume(project_id=project.id, title="第一卷", order=1)
    empty_volume = Volume(project_id=project.id, title="空卷", order=2)
    last_volume = Volume(project_id=project.id, title="第三卷", order=3)
    session.add(first)
    session.add(empty_volume)
    session.add(last_volume)
    await session.flush()
    planted = _chapter(project.id, first.id, "埋下", 1)
    # 卷内序号跳到 5，不能拿它和结局章的 order=1 相减。
    later = _chapter(project.id, first.id, "后文", 5)
    ending = _chapter(project.id, last_volume.id, "卷末", 1)
    session.add(planted)
    session.add(later)
    session.add(ending)
    await session.flush()

    thread = await plot_thread_service.create_thread(
        session, project.id, name="铜镜", intent="还没收"
    )
    await plot_thread_service.create_beat(
        session, thread.id, chapter_id=planted.id, kind="plant", note="灯"
    )
    resolved = await plot_thread_service.create_thread(
        session, project.id, name="已收", intent="收完了", status="resolved"
    )
    await plot_thread_service.create_beat(
        session, resolved.id, chapter_id=planted.id, kind="plant", note="埋"
    )
    await plot_thread_service.create_beat(
        session, resolved.id, chapter_id=later.id, kind="payoff", note="收"
    )

    board = await plot_thread_service.get_board(session, project.id)
    by_name = {item.thread.name: item.assessment for item in board.threads}
    assert [chapter.title for chapter in board.chapters] == ["埋下", "后文", "卷末"]
    assert by_name["铜镜"].chapters_since_last == 1
    assert [chapter.id for chapter in by_name["铜镜"].gap_chapters] == [later.id]
    assert by_name["铜镜"].gap_chapters[0].label == "2. 后文"
    assert by_name["已收"].chapters_since_last is None
    assert by_name["已收"].issues == ()
    assert by_name["已收"].gap_chapters == ()

    inserted = _chapter(project.id, first.id, "插章", 3)
    session.add(inserted)
    await session.flush()
    widened = await plot_thread_service.get_board(session, project.id)
    mirror = next(
        item.assessment for item in widened.threads if item.thread.name == "铜镜"
    )
    assert [chapter.title for chapter in widened.chapters] == [
        "埋下",
        "插章",
        "后文",
        "卷末",
    ]
    assert mirror.chapters_since_last == 2
    assert [chapter.label for chapter in mirror.gap_chapters] == ["2. 插章", "3. 后文"]
    assert [chapter.id for chapter in mirror.gap_chapters] == [inserted.id, later.id]
    resolved_after = next(
        item.assessment for item in widened.threads if item.thread.name == "已收"
    )
    assert resolved_after.gap_chapters == ()

    solo = Project(title="短篇", description="")
    session.add(solo)
    await session.flush()
    solo_volume = Volume(project_id=solo.id, title="仅一卷", order=1)
    session.add(solo_volume)
    await session.flush()
    only = _chapter(solo.id, solo_volume.id, "仅有", 4)
    session.add(only)
    await session.flush()
    solo_thread = await plot_thread_service.create_thread(
        session, solo.id, name="只有一章", intent="埋在这里"
    )
    await plot_thread_service.create_beat(
        session, solo_thread.id, chapter_id=only.id, kind="plant", note="灯"
    )
    solo_board = await plot_thread_service.get_board(session, solo.id)
    assert solo_board.threads[0].assessment.chapters_since_last is None
    assert solo_board.threads[0].assessment.gap_chapters == ()


def test_open_planted_names_follow_this_chapter_until_payoff() -> None:
    """这一章埋下且全书未回收才进名单。回收、别章埋下、只推进、已放弃都不进。"""
    chapters = [
        _spot("c1", 1, "夜航"),
        _spot("c2", 2, "旧伤"),
        _spot("c3", 3, "对上"),
    ]
    threads = [
        ("t-scar", "伤疤", "", "active", 0),
        ("t-mirror", "铜镜", "灯要在后文对上", "active", 1),
        ("t-letter", "旧信", "", "active", 2),
        ("t-drop", "弃线", "", "abandoned", 3),
        ("t-push", "只推进", "", "active", 4),
        ("t-marked", "假回收", "", "resolved", 5),
    ]
    beats = [
        ("b-scar", "t-scar", "c1", "plant", "露出来"),
        ("b-mirror", "t-mirror", "c1", "plant", "灯还亮着"),
        ("b-letter", "t-letter", "c2", "plant", "信压在灯下"),
        ("b-drop", "t-drop", "c1", "plant", "后来不用了"),
        ("b-push", "t-push", "c1", "advance", "直接往前推"),
        ("b-marked", "t-marked", "c1", "plant", "作者标了回收但没有节拍"),
    ]
    found = open_planted_names_by_chapter(assess_plot_threads(threads, beats, chapters))
    assert found["c1"] == ["伤疤", "铜镜", "假回收"]
    assert found["c2"] == ["旧信"]
    assert "c3" not in found
    assert "弃线" not in found["c1"]
    assert "只推进" not in found["c1"]

    paid = [*beats, ("b-pay", "t-mirror", "c3", "payoff", "镜子里是凶手")]
    after = open_planted_names_by_chapter(assess_plot_threads(threads, paid, chapters))
    assert after["c1"] == ["伤疤", "假回收"]
    assert "铜镜" not in after["c1"]
    assert after["c2"] == ["旧信"]
    assert "c3" not in after
