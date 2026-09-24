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
    OPEN_THREAD_LIMIT,
    PLOT_PLAN_NOTICE,
    STALE_CHAPTER_GAP,
    ChapterSpot,
    agent_plot_context,
    assess_plot_threads,
    normalize_beat_kind,
    normalize_intent,
    normalize_thread_name,
    normalize_thread_status,
    reading_order_of,
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

    letter = found["旧信"]
    assert "open" not in letter.issues
    assert letter.issues == ("payoff_still_active",)
    assert letter.last_beat is not None
    assert letter.last_beat.global_order == 3
    assert letter.chapters_since_last is None

    assert found["空线"].issues == ("open",)
    assert found["空线"].last_beat is None
    assert found["空线"].chapters_since_last is None
    assert found["放弃的线"].issues == ()
    assert found["放弃的线"].chapters_since_last is None
    assert found["倒序"].issues == ("payoff_before_plant", "payoff_still_active")
    assert found["倒序"].chapters_since_last is None
    assert found["假回收"].issues == ("resolved_without_payoff",)
    assert found["假回收"].chapters_since_last is None
    assert found["没埋就推"].issues == ("advance_without_plant", "open")
    assert found["没埋就推"].chapters_since_last == 1


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
    assert found["刚过"].chapters_since_last == 0
    assert found["独章"].chapters_since_last is None

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
    assert found["已收"].chapters_since_last is None
    assert found["已收"].issues == ()
    assert found["放弃"].chapters_since_last is None
    assert found["放弃"].issues == ()
    assert found["倒序"].issues == ("payoff_before_plant", "payoff_still_active")
    assert found["倒序"].chapters_since_last is None


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
    )
    assert previous is not None
    just_seen = open_thread(previous, "铜镜")
    assert just_seen["chapters_since"] == 0
    assert "consider_advance" not in just_seen

    below = agent_plot_context(
        current_chapter_id="c4",
        current_global_order=20,
        assessments=assessments,
        reading_order=reading,
    )
    assert below is not None
    below_mirror = open_thread(below, "铜镜")
    assert below_mirror["chapters_since"] == 2
    assert "consider_advance" not in below_mirror
    assert below_mirror["chapters_since"] != by_name["铜镜"].chapters_since_last

    at_threshold = agent_plot_context(
        current_chapter_id="c5",
        current_global_order=21,
        assessments=assessments,
        reading_order=reading,
    )
    assert at_threshold is not None
    stale = open_thread(at_threshold, "铜镜")
    assert stale["chapters_since"] == 3
    assert stale["consider_advance"] == CONSIDER_ADVANCE_NOTE
    later = open_thread(at_threshold, "后文")
    assert later["chapters_since"] == 3
    assert later["consider_advance"] == CONSIDER_ADVANCE_NOTE
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
    assert by_name["已收"].chapters_since_last is None
    assert by_name["已收"].issues == ()

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
