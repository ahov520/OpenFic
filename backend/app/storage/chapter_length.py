# -*- coding: utf-8 -*-
"""章节字数目标。

目标用来看这一章写短了还是拖了。空值表示不设目标。
不记录写作活动，也不改正文。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# 一章的目标再长也不该超过一部中篇。超过这个数对节奏没有意义。
WORD_COUNT_TARGET_MAX = 100_000

ChapterPace = Literal["none", "short", "met", "over"]


def normalize_word_count_target(value: int | None) -> int | None:
    """校验章节字数目标。None 表示清空。"""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("章节字数目标必须是整数")
    if value < 1 or value > WORD_COUNT_TARGET_MAX:
        raise ValueError(f"章节字数目标需在 1 到 {WORD_COUNT_TARGET_MAX} 之间")
    return value


def read_word_count_target(chapter: object) -> int | None:
    """读取已保存的目标。缺省或非法值视为未设置。"""
    raw = getattr(chapter, "word_count_target", None)
    if isinstance(raw, bool) or not isinstance(raw, int):
        return None
    if raw < 1 or raw > WORD_COUNT_TARGET_MAX:
        return None
    return raw


@dataclass(frozen=True)
class ChapterLengthProgress:
    """已写字数相对目标的差距。written 必须来自现有字数统计。"""

    pace: ChapterPace
    written: int
    target: int | None
    remaining: int
    over: int


def chapter_length_progress(written: int, target: int | None) -> ChapterLengthProgress:
    """比较已写字数和目标。没有目标时不判断长短。"""
    if target is None:
        return ChapterLengthProgress(
            pace="none",
            written=written,
            target=None,
            remaining=0,
            over=0,
        )
    if written < target:
        return ChapterLengthProgress(
            pace="short",
            written=written,
            target=target,
            remaining=target - written,
            over=0,
        )
    if written > target:
        return ChapterLengthProgress(
            pace="over",
            written=written,
            target=target,
            remaining=0,
            over=written - target,
        )
    return ChapterLengthProgress(
        pace="met",
        written=written,
        target=target,
        remaining=0,
        over=0,
    )
