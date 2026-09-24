# -*- coding: utf-8 -*-
"""情节线的校验、断线判断，以及给 Agent 的短计划。

节拍是作者挂在章节上的计划，不是正文里已经发生的事实。
"""

from __future__ import annotations

from dataclasses import dataclass

THREAD_STATUSES = ("active", "resolved", "abandoned")
DEFAULT_THREAD_STATUS = "active"
BEAT_KINDS = ("plant", "advance", "payoff")

NAME_MAX_LENGTH = 80
INTENT_MAX_LENGTH = 200
NOTE_MAX_LENGTH = 200

OPEN_THREAD_LIMIT = 12
CHAPTER_BEAT_LIMIT = 12
CONTEXT_TEXT_LIMIT = 80

# 空 0 章表示上一章刚出现过，空 1、2 章多半是故意隔开一场，不打断写作。
# 中间空到 3 章，读者已经连续经过三章没再遇见这条线，作者该决定当前章要不要推进。
# Plottr 的空列是情节线和章节相交处的空白格子，能看出哪一列没有场景卡，但不列出缺失的场景名。
# Aeon Timeline 的叙事视图只排列放进去的事件，两场之间的空是没放事件，不会报出缺了哪一场。
# 这里除了按章计数，还按阅读顺序列出空章名称。写作界面和 Agent 当前章上下文共用这一阈值。
STALE_CHAPTER_GAP = 3

# 卡片默认逐章列出空章。4 章还能看完；从第 5 章起收成「首章 → 末章」，展开后再看全部。
# Agent 当前章上下文也只点出这么多章名，多出来的用「还有 N 章」收住。
GAP_CHAPTER_PREVIEW = 4

# 与写作界面里空标题的章节称呼一致。
UNTITLED_CHAPTER_LABEL = "未命名章节"

PLOT_PLAN_NOTICE = (
    "这些是作者计划的情节线，不是已经写进正文的事实。"
    "写当前章时只遵守本章节拍；未回收的线只说明它还开着，不要提前写出后文。"
    "标了该考虑推进的线，可以在当前章往前推一步，仍然不要写出后文才会发生的事。"
)

CONSIDER_ADVANCE_NOTE = "到当前章已经隔了多章，可以考虑推进，不要写出后文。"

BOARD_VIEWS = ("issues", "open", "quiet", "all")

ISSUE_PAYOFF_WITHOUT_PLANT = "payoff_without_plant"
ISSUE_PAYOFF_BEFORE_PLANT = "payoff_before_plant"
ISSUE_ADVANCE_WITHOUT_PLANT = "advance_without_plant"
ISSUE_RESOLVED_WITHOUT_PAYOFF = "resolved_without_payoff"
ISSUE_PAYOFF_STILL_ACTIVE = "payoff_still_active"
ISSUE_OPEN = "open"


def normalize_thread_status(value: str | None) -> str:
    """校验情节线状态。空值视为进行中。"""
    if value is None or value == "":
        return DEFAULT_THREAD_STATUS
    if value not in THREAD_STATUSES:
        raise ValueError("情节线状态无效")
    return value


def normalize_beat_kind(value: str | None) -> str:
    """校验节拍类型。"""
    if value not in BEAT_KINDS:
        raise ValueError("节拍类型无效")
    return value


def normalize_thread_name(value: str | None) -> str:
    """情节线名称去掉首尾空白，并限制长度。"""
    name = (value or "").strip()
    if not name:
        raise ValueError("情节线名称不能为空")
    if len(name) > NAME_MAX_LENGTH:
        raise ValueError(f"情节线名称超出 {NAME_MAX_LENGTH} 字限制")
    return name


def normalize_intent(value: str | None) -> str:
    """意图收成一行，避免把后文分段写进来。"""
    return _normalize_line(value, INTENT_MAX_LENGTH, "意图")


def normalize_note(value: str | None) -> str:
    """章节备注收成一行。"""
    return _normalize_line(value, NOTE_MAX_LENGTH, "备注")


def _normalize_line(value: str | None, limit: int, label: str) -> str:
    text = " ".join((value or "").replace("\r\n", "\n").replace("\r", "\n").split())
    if len(text) > limit:
        raise ValueError(f"{label}超出 {limit} 字限制")
    return text


def _clip(value: str, limit: int) -> str:
    stripped = value.strip()
    if len(stripped) <= limit:
        return stripped
    return stripped[: limit - 1] + "…"


@dataclass(frozen=True)
class ChapterSpot:
    """断线判断用的章节位置。"""

    id: str
    title: str
    global_order: int
    volume_title: str


@dataclass(frozen=True)
class BeatSpot:
    """挂在某一章上的节拍。"""

    id: str
    thread_id: str
    chapter_id: str
    kind: str
    note: str
    global_order: int
    chapter_title: str
    volume_title: str


@dataclass(frozen=True)
class GapChapter:
    """阅读顺序中的一章空档。label 与总览章节称呼一致：全局序. 标题。"""

    id: str
    label: str


@dataclass(frozen=True)
class ThreadAssessment:
    """一条线在全书里的形状，以及能直接看见的问题。"""

    id: str
    name: str
    intent: str
    status: str
    sort_order: int
    beats: tuple[BeatSpot, ...]
    issues: tuple[str, ...]
    has_plant: bool
    has_payoff: bool
    last_beat: BeatSpot | None
    chapters_since_last: int | None
    gap_chapters: tuple[GapChapter, ...]
    gap_range: str | None


def chapters_between(
    reading_order: list[str], earlier_id: str, later_id: str
) -> int | None:
    """按阅读顺序数两章中间空了几章。

    reading_order 是章节 id，已经按卷序、卷内章节序排好。
    数的是两者之间有几章，不用数据库 id 相减，也不用章节序号相减。
    同一章，或 later 不在 earlier 之后，返回 None（没有空档）。
    紧挨着的下一章返回 0，表示上一章刚出现过。
    """
    try:
        earlier = reading_order.index(earlier_id)
        later = reading_order.index(later_id)
    except ValueError:
        return None
    if later <= earlier:
        return None
    return later - earlier - 1


def reading_order_of(chapters: list[ChapterSpot]) -> list[str]:
    """章节 id 的阅读顺序。global_order 只用来排序，不拿来相减。"""
    ordered = sorted(chapters, key=lambda chapter: (chapter.global_order, chapter.id))
    return [chapter.id for chapter in ordered]


def chapter_display_label(global_order: int, title: str) -> str:
    """与总览里的章节称呼一致：全局阅读序、点、标题。空标题用未命名章节。"""
    name = title.strip() or UNTITLED_CHAPTER_LABEL
    return f"{global_order}. {name}"


def chapters_in_gap(
    chapters: list[ChapterSpot],
    reading_order: list[str],
    earlier_id: str,
    later_id: str,
) -> tuple[GapChapter, ...]:
    """按阅读顺序列出两章中间的章节。不含两端。紧挨着或顺序颠倒时为空。"""
    try:
        earlier = reading_order.index(earlier_id)
        later = reading_order.index(later_id)
    except ValueError:
        return ()
    if later <= earlier + 1:
        return ()
    by_id = {chapter.id: chapter for chapter in chapters}
    found: list[GapChapter] = []
    for chapter_id in reading_order[earlier + 1 : later]:
        chapter = by_id.get(chapter_id)
        if chapter is None:
            continue
        found.append(
            GapChapter(
                id=chapter.id,
                label=chapter_display_label(chapter.global_order, chapter.title),
            )
        )
    return tuple(found)


def gap_range_label(chapters: tuple[GapChapter, ...]) -> str | None:
    """超过预览条数时，卡片默认展示的首尾范围。不超过则返回空，由界面逐章列出。"""
    if len(chapters) <= GAP_CHAPTER_PREVIEW:
        return None
    return f"{chapters[0].label} → {chapters[-1].label}"


@dataclass(frozen=True)
class ThroughChapterGap:
    """参照点为某一章时，这条线到该章为止的空章。结构与总览的空章列表相同。"""

    thread_id: str
    chapters_since: int
    gap_chapters: tuple[GapChapter, ...]
    gap_range: str | None


def gaps_through_chapter(
    assessments: list[ThreadAssessment],
    chapters: list[ChapterSpot],
    reading_order: list[str],
    current_chapter_id: str,
) -> list[ThroughChapterGap]:
    """到参照章为止的空章。顺序只来自阅读顺序（卷序 + 卷内序），调用方不要重排。

    最后一次已出现的节拍所在章和参照章之间、没有这条线节拍的章，不含两端。
    参照章本身即使没有这条线，也只是终点，不进列表，与 chapters_between 一致。
    空 0 则列表为空。已回收、已放弃、到参照章已经有回收节拍的不列。
    参照章之后的章和节拍不参与，避免把后文空章算进当前写作决策。
    """
    try:
        current_index = reading_order.index(current_chapter_id)
    except ValueError:
        return []
    position = {chapter_id: index for index, chapter_id in enumerate(reading_order)}
    found: list[ThroughChapterGap] = []
    for thread in assessments:
        if thread.status != "active":
            continue
        visible = [
            beat
            for beat in thread.beats
            if position.get(beat.chapter_id, current_index + 1) <= current_index
        ]
        if not visible or any(beat.kind == "payoff" for beat in visible):
            continue
        last = max(visible, key=lambda beat: (position[beat.chapter_id], beat.id))
        gap = chapters_between(reading_order, last.chapter_id, current_chapter_id)
        if gap is None:
            continue
        gap_chapters = (
            chapters_in_gap(
                chapters, reading_order, last.chapter_id, current_chapter_id
            )
            if gap
            else ()
        )
        found.append(
            ThroughChapterGap(
                thread_id=thread.id,
                chapters_since=gap,
                gap_chapters=gap_chapters,
                gap_range=gap_range_label(gap_chapters),
            )
        )
    return found


def context_gap_names(chapters: tuple[GapChapter, ...]) -> dict[str, object]:
    """Agent 上下文里的空章展示名。最多点出预览条数，其余收成「还有 N 章」。"""
    if not chapters:
        return {}
    shown = [chapter.label for chapter in chapters[:GAP_CHAPTER_PREVIEW]]
    payload: dict[str, object] = {"gap_chapters": shown}
    omitted = len(chapters) - len(shown)
    if omitted:
        payload["gap_more"] = f"还有 {omitted} 章"
    return payload


def assess_plot_threads(
    threads: list[tuple[str, str, str, str, int]],
    beats: list[tuple[str, str, str, str, str]],
    chapters: list[ChapterSpot],
) -> list[ThreadAssessment]:
    """按阅读顺序判断每条线是否断掉。

    threads: (id, name, intent, status, sort_order)
    beats: (id, thread_id, chapter_id, kind, note)
    """
    chapter_by_id = {chapter.id: chapter for chapter in chapters}
    reading_order = reading_order_of(chapters)
    beats_by_thread: dict[str, list[BeatSpot]] = {}
    for beat_id, thread_id, chapter_id, kind, note in beats:
        chapter = chapter_by_id.get(chapter_id)
        if chapter is None or kind not in BEAT_KINDS:
            continue
        beats_by_thread.setdefault(thread_id, []).append(
            BeatSpot(
                id=beat_id,
                thread_id=thread_id,
                chapter_id=chapter_id,
                kind=kind,
                note=note,
                global_order=chapter.global_order,
                chapter_title=chapter.title,
                volume_title=chapter.volume_title,
            )
        )

    assessments: list[ThreadAssessment] = []
    ordered = sorted(threads, key=lambda item: (item[4], item[1], item[0]))
    for thread_id, name, intent, status, sort_order in ordered:
        placed = tuple(
            sorted(
                beats_by_thread.get(thread_id, []),
                key=lambda beat: (beat.global_order, beat.id),
            )
        )
        assessments.append(
            _assess_one(
                thread_id=thread_id,
                name=name,
                intent=intent,
                status=status if status in THREAD_STATUSES else DEFAULT_THREAD_STATUS,
                sort_order=sort_order,
                beats=placed,
                chapters=chapters,
                reading_order=reading_order,
            )
        )
    return assessments


def _assess_one(
    *,
    thread_id: str,
    name: str,
    intent: str,
    status: str,
    sort_order: int,
    beats: tuple[BeatSpot, ...],
    chapters: list[ChapterSpot],
    reading_order: list[str],
) -> ThreadAssessment:
    plant_orders = [beat.global_order for beat in beats if beat.kind == "plant"]
    advance_orders = [beat.global_order for beat in beats if beat.kind == "advance"]
    payoff_orders = [beat.global_order for beat in beats if beat.kind == "payoff"]
    first_plant = min(plant_orders) if plant_orders else None
    has_plant = first_plant is not None
    has_payoff = bool(payoff_orders)

    def lacks_plant_by(order: int) -> bool:
        return first_plant is None or first_plant > order

    issues: list[str] = []
    if any(lacks_plant_by(order) for order in payoff_orders):
        if first_plant is None:
            issues.append(ISSUE_PAYOFF_WITHOUT_PLANT)
        else:
            issues.append(ISSUE_PAYOFF_BEFORE_PLANT)
    if any(lacks_plant_by(order) for order in advance_orders):
        issues.append(ISSUE_ADVANCE_WITHOUT_PLANT)
    if status == "resolved" and not has_payoff:
        issues.append(ISSUE_RESOLVED_WITHOUT_PAYOFF)
    if status == "active" and has_payoff:
        issues.append(ISSUE_PAYOFF_STILL_ACTIVE)
    if status == "active" and not has_payoff:
        issues.append(ISSUE_OPEN)

    last_beat = beats[-1] if beats else None
    # 已回收、已放弃，或已经有回收节拍的线，不标成凉了，也不列空章。
    # 最后一次节拍就在全书最后一章时也没有空档。
    # 空章是最后一次节拍所在章和全书最后一章之间的章节，不含这两端。
    # 空 0 时列表为空。顺序只来自阅读顺序，不用数据库 id。
    chapters_since_last = None
    gap_chapters: tuple[GapChapter, ...] = ()
    if (
        status == "active"
        and not has_payoff
        and last_beat is not None
        and reading_order
    ):
        end_id = reading_order[-1]
        chapters_since_last = chapters_between(
            reading_order, last_beat.chapter_id, end_id
        )
        if chapters_since_last:
            gap_chapters = chapters_in_gap(
                chapters, reading_order, last_beat.chapter_id, end_id
            )

    return ThreadAssessment(
        id=thread_id,
        name=name,
        intent=intent,
        status=status,
        sort_order=sort_order,
        beats=beats,
        issues=tuple(issues),
        has_plant=has_plant,
        has_payoff=has_payoff,
        last_beat=last_beat,
        chapters_since_last=chapters_since_last,
        gap_chapters=gap_chapters,
        gap_range=gap_range_label(gap_chapters),
    )


def board_problem_rank(issues: tuple[str, ...]) -> int:
    """结构对不上的线最前，未回收其次。没有问题的线排在后面。"""
    if ISSUE_PAYOFF_WITHOUT_PLANT in issues or ISSUE_PAYOFF_BEFORE_PLANT in issues:
        return 0
    if ISSUE_OPEN in issues:
        return 1
    if issues:
        return 2
    return 3


def select_board_threads(
    assessments: list[ThreadAssessment],
    view: str = "issues",
) -> list[ThreadAssessment]:
    """总览挑哪些线、按什么顺序。

    issues（默认）：留下所有标了问题的线，有结构问题的排在前面。
    只有「未回收」、没有结构错误的线也在这份名单里，隔很久不会被挡在外面。
    同一档里隔得越久越靠前。
    quiet：只留能量出空档的未回收线，隔得最久在前。已回收、已放弃不在这里。
    open：未回收。all：全部。后两种仍是有问题的优先，然后按空档。
    """
    if view not in BOARD_VIEWS:
        raise ValueError("情节线总览范围无效")
    if view == "quiet":
        chosen = [item for item in assessments if item.chapters_since_last is not None]
    elif view == "open":
        chosen = [item for item in assessments if ISSUE_OPEN in item.issues]
    elif view == "all":
        chosen = list(assessments)
    else:
        chosen = [item for item in assessments if item.issues]

    def sort_key(item: ThreadAssessment) -> tuple[object, ...]:
        gap = item.chapters_since_last
        # None 表示没有可比较的空档，排在有数字的后面。
        gap_rank = -(gap if gap is not None else -1)
        if view == "quiet":
            return (gap_rank, item.sort_order, item.name, item.id)
        return (
            board_problem_rank(item.issues),
            gap_rank,
            item.sort_order,
            item.name,
            item.id,
        )

    return sorted(chosen, key=sort_key)


def agent_plot_context(
    *,
    current_chapter_id: str,
    current_global_order: int,
    assessments: list[ThreadAssessment],
    reading_order: list[str] | None = None,
    chapters: list[ChapterSpot] | None = None,
) -> dict[str, object] | None:
    """当前章能看见的计划：本章节拍，以及到这一章为止还没收的线。

    后文章节上的备注不放进来，避免把还没写到的回收泄进正文。
    chapters_since 数的是最后一次已出现的节拍到当前章中间空了几章，
    不是到全书最后一章。达到 STALE_CHAPTER_GAP 才提示考虑推进。
    已经提到空档时，补上到当前章为止的空章展示名，不含当前章之后的章。
    """
    named_gaps: dict[str, ThroughChapterGap] = {}
    if chapters is not None and reading_order:
        named_gaps = {
            item.thread_id: item
            for item in gaps_through_chapter(
                assessments,
                chapters,
                reading_order,
                current_chapter_id,
            )
        }
    chapter_beats: list[dict[str, str]] = []
    open_threads: list[tuple[tuple[int, int, int, str], dict[str, object]]] = []

    for thread in assessments:
        for beat in thread.beats:
            if beat.chapter_id != current_chapter_id:
                continue
            entry: dict[str, str] = {
                "thread": thread.name,
                "status": thread.status,
                "kind": beat.kind,
            }
            intent = _clip(thread.intent, CONTEXT_TEXT_LIMIT)
            note = _clip(beat.note, CONTEXT_TEXT_LIMIT)
            if intent:
                entry["intent"] = intent
            if note:
                entry["note"] = note
            chapter_beats.append(entry)

        if thread.status != "active":
            continue
        visible = [
            beat for beat in thread.beats if beat.global_order <= current_global_order
        ]
        if not visible:
            continue
        paid_off = any(beat.kind == "payoff" for beat in visible)
        if paid_off:
            continue
        last = visible[-1] if visible else None
        summary: dict[str, object] = {"thread": thread.name}
        intent = _clip(thread.intent, CONTEXT_TEXT_LIMIT)
        if intent:
            summary["intent"] = intent
        if last is not None:
            summary["last_order"] = last.global_order
            summary["last_title"] = last.chapter_title
            summary["last_kind"] = last.kind
        on_chapter = (
            0 if any(beat.chapter_id == current_chapter_id for beat in visible) else 1
        )
        gap = None
        if last is not None and reading_order:
            gap = chapters_between(reading_order, last.chapter_id, current_chapter_id)
        if gap is not None:
            summary["chapters_since"] = gap
            if gap >= STALE_CHAPTER_GAP:
                summary["consider_advance"] = CONSIDER_ADVANCE_NOTE
            named = named_gaps.get(thread.id)
            if named is not None and named.chapters_since == gap:
                summary.update(context_gap_names(named.gap_chapters))
        gap_rank = -(gap if gap is not None else -1)
        open_threads.append(
            (
                (on_chapter, gap_rank, thread.sort_order, thread.name),
                summary,
            )
        )

    if not chapter_beats and not open_threads:
        return None

    chapter_beats = chapter_beats[:CHAPTER_BEAT_LIMIT]
    open_threads.sort(key=lambda item: item[0])
    omitted = max(0, len(open_threads) - OPEN_THREAD_LIMIT)
    payload: dict[str, object] = {
        "notice": PLOT_PLAN_NOTICE,
        "chapter_beats": chapter_beats,
        "open_threads": [item[1] for item in open_threads[:OPEN_THREAD_LIMIT]],
    }
    if omitted:
        payload["open_omitted"] = omitted
    return payload
