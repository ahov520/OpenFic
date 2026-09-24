# -*- coding: utf-8 -*-
"""情节线的断线判断、存储，以及给 Agent 的短计划。"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError
from app.storage.models.chapter import Chapter
from app.storage.models.project import Project
from app.storage.models.volume import Volume
from app.storage.plot_threads import (
    OPEN_THREAD_LIMIT,
    PLOT_PLAN_NOTICE,
    ChapterSpot,
    agent_plot_context,
    assess_plot_threads,
    normalize_beat_kind,
    normalize_intent,
    normalize_thread_name,
    normalize_thread_status,
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

    letter = found["旧信"]
    assert "open" not in letter.issues
    assert letter.issues == ("payoff_still_active",)
    assert letter.last_beat is not None
    assert letter.last_beat.global_order == 3

    assert found["空线"].issues == ("open",)
    assert found["空线"].last_beat is None
    assert found["放弃的线"].issues == ()
    assert found["倒序"].issues == ("payoff_before_plant", "payoff_still_active")
    assert found["假回收"].issues == ("resolved_without_payoff",)
    assert found["没埋就推"].issues == ("advance_without_plant", "open")


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
