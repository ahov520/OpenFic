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

PLOT_PLAN_NOTICE = (
    "这些是作者计划的情节线，不是已经写进正文的事实。"
    "写当前章时只遵守本章节拍；未回收的线只说明它还开着，不要提前写出后文。"
)

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
        last_beat=beats[-1] if beats else None,
    )


def agent_plot_context(
    *,
    current_chapter_id: str,
    current_global_order: int,
    assessments: list[ThreadAssessment],
) -> dict[str, object] | None:
    """当前章能看见的计划：本章节拍，以及到这一章为止还没收的线。

    后文章节上的备注不放进来，避免把还没写到的回收泄进正文。
    """
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
        last_order = last.global_order if last is not None else -1
        open_threads.append(
            (
                (on_chapter, -last_order, thread.sort_order, thread.name),
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
