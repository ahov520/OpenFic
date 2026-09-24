# -*- coding: utf-8 -*-
"""对照这一章的梗概和节拍，找出正文里还没有依据的计划。

只看挂在当前章上的节拍。后文章节的备注不参与检查。
结果留在章节上；正文、梗概或本章节拍一旦变化，旧结果标成过期，不自动删掉。
没有梗概、也没有本章节拍时，结果是「没有可对照的计划」，不是检查通过。
再次检查时，用梗概原句、或节拍的情节线 id 加类型，对照上一份开口缺口。
对不上的旧句子单独标成失效，不把它算成已经写上。
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime

QUOTE_RE = re.compile(
    r"「([^」\n]{2,40})」"
    r"|『([^』\n]{2,40})』"
    r"|“([^”\n]{2,40})”"
    r"|\"([^\"\n]{2,40})\""
)
LATIN_NAME_RE = re.compile(r"(?<![A-Za-z])[A-Z][a-z]{2,20}(?:\s+[A-Z][a-z]{2,20})?")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？!?])")
NOTE_PUNCT = set("。！？；，、,.!?;：:")
THREAD_NAME_SKIP = frozenset({"主角", "情节", "伏笔", "冲突", "结尾", "开头"})
NAME_BLOCKLIST = frozenset(
    {
        "于是",
        "任何",
        "何必",
        "何时",
        "何处",
        "曾经",
        "理由",
        "张开",
        "陈述",
        "周围",
        "方法",
        "方向",
        "高兴",
        "马上",
        "白天",
        "白色",
        "金色",
        "江湖",
        "黄金",
        "王子",
    }
)
GIVEN_STOP = set("的了着过呢吧吗啊呀嘛得地在把被和与或而也就都还又很到从对向为以让给")
NAME_INTRODUCERS = set("是叫见让把被与跟问找和给对")
# 这些字既是姓，也是日常词的开头。字面检查不把它们当专名，避免把「脚步」「后文」报成缺口。
COLLISION_SURNAMES = frozenset(
    "步后文方高金白马于曾向任何安常乐时成明平全山谷车井左石宁甘武龙叶易古关"
    "相查红东国都从能双闻党边农温别庄连习鱼容终居满广利师冷那简空沙丰盖印宿"
    "幸司景符班秋仲伊宫单应宗莫支"
)
COMPOUND_SURNAMES = (
    "欧阳",
    "司马",
    "上官",
    "诸葛",
    "夏侯",
    "皇甫",
    "尉迟",
    "公孙",
    "慕容",
    "长孙",
    "司徒",
    "司空",
    "东方",
    "赫连",
    "澹台",
    "公冶",
    "宗政",
    "濮阳",
    "淳于",
    "太叔",
    "申屠",
    "仲孙",
    "轩辕",
    "令狐",
    "钟离",
    "宇文",
    "鲜于",
    "闾丘",
)
_SINGLE_SURNAME_CHARS = frozenset(
    "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜"
    "戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳唐罗薛雷"
    "贺倪汤滕殷毕郝邬安常乐于时傅齐康伍余元卜顾孟平黄穆萧尹姚邵汪祁毛"
    "禹狄米贝明臧计伏成戴谈宋茅庞熊纪舒屈项祝董梁杜阮蓝闵席季麻强贾路"
    "娄危江童颜郭梅盛林刁钟徐邱骆高夏蔡田樊胡凌霍虞支柯管卢莫经房裘缪"
    "干解应宗丁宣邓郁单杭洪包诸左石崔吉龚程嵇邢裴陆荣翁荀羊惠甄曲家封"
    "芮羿储靳汲邴糜松井段富巫乌焦巴弓牧山谷车侯宓蓬全郗班仰秋仲伊宫宁"
    "仇栾暴甘厉戎祖武符刘景詹束龙叶幸司韶郜黎蓟薄印宿白怀蒲台从鄂索咸"
    "籍赖卓蔺屠蒙池乔阴胥能苍双闻莘党翟谭贡劳逄姬申扶堵冉宰郦雍桑桂濮"
    "牛寿通边扈燕冀浦尚农温别庄晏柴瞿阎充慕连茹习宦艾鱼容向古易慎戈廖"
    "庾终暨居衡步都耿满弘匡国文寇广禄阙东欧殳沃利蔚越夔隆师巩聂晁勾敖"
    "融冷訾辛阚那简饶空曾沙乜养鞠须丰巢关蒯相查后荆红游竺权逯盖桓"
)
SINGLE_SURNAMES = _SINGLE_SURNAME_CHARS - COLLISION_SURNAMES
PAYLOAD_VERSION = 1
GAP_CHANGE_STILL = "still"
GAP_CHANGE_NEW = "new"
GAP_CHANGE_GONE = "gone"
GAP_CHANGE_INVALIDATED = "invalidated"
GAP_CHANGES = frozenset(
    {
        GAP_CHANGE_STILL,
        GAP_CHANGE_NEW,
        GAP_CHANGE_GONE,
        GAP_CHANGE_INVALIDATED,
    }
)
# 这两类不是这一次的开口缺口。再对照时不把它们当成「上一份还没写上的」。
CLOSED_GAP_CHANGES = frozenset({GAP_CHANGE_GONE, GAP_CHANGE_INVALIDATED})
PROSE_LIMIT = 16000
BECAUSE_LIMIT = 160


@dataclass(frozen=True)
class BeatInput:
    """挂在当前章上的一条节拍，以及它所属线的名称和意图。"""

    id: str
    kind: str
    note: str
    thread_name: str
    intent: str
    thread_id: str = ""


@dataclass(frozen=True)
class PlanItem:
    """可以单独指出的一条计划：梗概里的一句，或这一章的一条节拍。"""

    ref: str
    origin: str
    plan_text: str
    beat_kind: str | None = None
    thread_name: str | None = None
    note: str = ""
    intent: str = ""
    thread_id: str = ""


@dataclass(frozen=True)
class CoverageGap:
    """正文里看不到依据的一条计划。"""

    ref: str
    origin: str
    plan_text: str
    basis: str
    missing: tuple[str, ...] = ()
    detail: str = ""
    beat_kind: str | None = None
    thread_name: str | None = None
    thread_id: str | None = None
    change: str | None = None


@dataclass(frozen=True)
class UncheckedLine:
    """字面检查找不到专名或引号，因此不能判断的计划。"""

    ref: str
    origin: str
    plan_text: str
    beat_kind: str | None = None
    thread_name: str | None = None


@dataclass(frozen=True)
class StoredPlanCheck:
    """已经落在章节上的一次检查。"""

    fingerprint: str
    source: str
    gaps: tuple[CoverageGap, ...]
    unchecked: tuple[UncheckedLine, ...]
    checked_at: datetime | None = None


@dataclass(frozen=True)
class PresentedCheck:
    """读出来给作者看的结果。过期仍保留缺口，但不会把没计划说成通过。"""

    has_plan: bool
    freshness: str
    source: str | None
    outcome: str
    gaps: tuple[CoverageGap, ...]
    unchecked: tuple[UncheckedLine, ...]
    checked_at: datetime | None = None


def normalize_for_search(text: str) -> str:
    """去掉标记和空白后再比对，避免换行把同一个词拆开。"""
    stripped = re.sub(r"<[^>]+>", "", text or "")
    normalized = unicodedata.normalize("NFKC", stripped)
    return "".join(normalized.split()).casefold()


def build_plan_items(synopsis: str, beats: list[BeatInput]) -> list[PlanItem]:
    """梗概按句切开；节拍一条算一条。只使用调用方传入的本章节拍。"""
    items = [
        _synopsis_item(index, sentence)
        for index, sentence in enumerate(_synopsis_sentences(synopsis))
    ]
    ordered = sorted(beats, key=lambda beat: beat.id)
    items.extend(_beat_item(beat) for beat in ordered)
    return items


def plan_fingerprint(content: str, synopsis: str, beats: list[BeatInput]) -> str:
    """正文、梗概、本章节拍的名称、意图、类型和备注一起参与指纹。"""
    payload = {
        "beats": [
            {
                "id": beat.id,
                "intent": beat.intent,
                "kind": beat.kind,
                "note": beat.note,
                "thread_name": beat.thread_name,
            }
            for beat in sorted(beats, key=lambda beat: beat.id)
        ],
        "content": content,
        "synopsis": synopsis,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def has_author_plan(synopsis: str, beats: list[BeatInput]) -> bool:
    return bool(synopsis.strip()) or bool(beats)


def literal_report(
    prose: str,
    items: list[PlanItem],
) -> tuple[list[CoverageGap], list[UncheckedLine]]:
    """专名、引号内短句、节拍上的短备注、情节线名称，在正文中完全未出现才算缺口。"""
    prose_norm = normalize_for_search(prose)
    gaps: list[CoverageGap] = []
    unchecked: list[UncheckedLine] = []
    for item in items:
        anchors = extract_anchors(item)
        if not anchors:
            unchecked.append(
                UncheckedLine(
                    ref=item.ref,
                    origin=item.origin,
                    plan_text=item.plan_text,
                    beat_kind=item.beat_kind,
                    thread_name=item.thread_name,
                )
            )
            continue
        missing = tuple(
            anchor
            for anchor in anchors
            if normalize_for_search(anchor) not in prose_norm
        )
        if not missing:
            continue
        gaps.append(
            CoverageGap(
                ref=item.ref,
                origin=item.origin,
                plan_text=item.plan_text,
                basis="literal",
                missing=missing,
                beat_kind=item.beat_kind,
                thread_name=item.thread_name,
                thread_id=item.thread_id or None,
            )
        )
    return gaps, unchecked


def extract_anchors(item: PlanItem) -> list[str]:
    """从一条计划里抽出可以逐字核对的锚点。"""
    searchable = "\n".join(
        part
        for part in (item.note, item.intent, item.plan_text, item.thread_name or "")
        if part
    )
    anchors: list[str] = []
    anchors.extend(_quoted_phrases(searchable))
    anchors.extend(_proper_names(searchable))
    short_note = _short_label(item.note)
    if short_note:
        anchors.append(short_note)
    thread_name = _thread_anchor(item.thread_name)
    if thread_name:
        anchors.append(thread_name)
    return _prefer_longer(anchors)


def parse_model_gaps(raw: str, items: list[PlanItem]) -> list[CoverageGap] | None:
    """解析模型返回的缺口。对不上计划条目，或说不出计划里的词，就放弃这次模型结果。"""
    payload = _extract_json_object(raw)
    if payload is None:
        return None
    raw_gaps = payload.get("gaps")
    if not isinstance(raw_gaps, list):
        return None
    by_ref = {item.ref: item for item in items}
    accepted: list[CoverageGap] = []
    seen: set[str] = set()
    invalid = 0
    for entry in raw_gaps:
        if not isinstance(entry, dict):
            invalid += 1
            continue
        ref = entry.get("ref")
        because = entry.get("because")
        if not isinstance(ref, str) or not isinstance(because, str):
            invalid += 1
            continue
        item = by_ref.get(ref)
        detail = " ".join(because.split())
        if item is None or ref in seen or not detail or not _cites_plan(detail, item):
            invalid += 1
            continue
        seen.add(ref)
        accepted.append(
            CoverageGap(
                ref=item.ref,
                origin=item.origin,
                plan_text=item.plan_text,
                basis="model",
                detail=detail[:BECAUSE_LIMIT],
                beat_kind=item.beat_kind,
                thread_name=item.thread_name,
                thread_id=item.thread_id or None,
            )
        )
    if raw_gaps and not accepted and invalid:
        return None
    return accepted


def render_check_prompt(prose: str, items: list[PlanItem]) -> list[dict[str, str]]:
    """走现有聊天调用时使用的消息。只放入这一章的计划和正文。"""
    lines: list[str] = []
    for item in items:
        if item.origin == "synopsis":
            lines.append(f"- {item.ref} | 梗概 | {item.plan_text}")
            continue
        kind = {"plant": "埋下", "advance": "推进", "payoff": "回收"}.get(
            item.beat_kind or "",
            item.beat_kind or "",
        )
        note = item.note or "（没有备注）"
        intent = f" | 意图：{item.intent}" if item.intent else ""
        thread = item.thread_name or ""
        lines.append(f"- {item.ref} | {kind} · {thread} | 备注：{note}{intent}")
    system = (
        "你是小说改稿助手。对照作者写给这一章的计划，找出正文里还没有依据的条目。"
        "计划只包括这一章梗概里的句子，以及挂在这一章上的节拍。"
        "节拍意图是整条线的方向，不是后文已经发生的事。"
        "不要因为后文才会回收的内容还没写进这一章就报缺口。"
        "换一种说法也算写到了。只有正文里看不到这件事时才算缺口。"
        "不要评价文笔，不要检查语法，不要编造计划里没有的情节。"
        "只返回 JSON："
        '{"gaps":[{"ref":"synopsis:0","because":"用计划原句里的词说明正文缺了什么"}]}'
        'because 必须带上对应计划里的原词。没有缺口就返回 {"gaps":[]}。'
    )
    user = f"正文：\n{_clip_prose(prose)}\n\n这一章的计划：\n" + "\n".join(lines)
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def annotate_gap_changes(
    previous: tuple[CoverageGap, ...],
    current: list[CoverageGap],
    items: list[PlanItem],
) -> list[CoverageGap]:
    """把上一份开口缺口和这一次的结果对齐。

    梗概用那一句的原文对齐，不用会随插入句子而变的序号。
    节拍用情节线 id 加类型对齐，不用备注或线名。
    对得上且这次仍是缺口：仍未写上。这次才有：新出现。
    计划条目还在、但这次结果里没有这条：不再出现。这不是通过。
    原文改写、删掉或节拍类型变了，对不上当前计划：旧条目失效，不算已经写上。
    上一份里已经标成不再出现或失效的，不参与这一次对照。
    """
    prior = [gap for gap in previous if gap.change not in CLOSED_GAP_CHANGES]
    plan_keys = {key for item in items if (key := _plan_key(item)) is not None}
    current_keys: set[tuple[str, str]] = set()
    for gap in current:
        key = _gap_key(gap)
        if key is not None:
            current_keys.add(key)

    still_keys: set[tuple[str, str]] = set()
    gone: list[CoverageGap] = []
    invalidated: list[CoverageGap] = []
    seen: set[tuple[str, str]] = set()
    for old in prior:
        key = _gap_key(old)
        if key is not None:
            if key in seen:
                continue
            seen.add(key)
        if key is None or key not in plan_keys:
            invalidated.append(_with_change(old, GAP_CHANGE_INVALIDATED))
            continue
        if key in current_keys:
            still_keys.add(key)
            continue
        gone.append(_with_change(old, GAP_CHANGE_GONE))

    annotated: list[CoverageGap] = []
    for gap in current:
        key = _gap_key(gap)
        change = (
            GAP_CHANGE_STILL
            if key is not None and key in still_keys
            else GAP_CHANGE_NEW
        )
        annotated.append(_with_change(gap, change))
    annotated.extend(gone)
    annotated.extend(invalidated)
    return annotated


def dump_payload(gaps: list[CoverageGap], unchecked: list[UncheckedLine]) -> str:
    return json.dumps(
        {
            "version": PAYLOAD_VERSION,
            "gaps": [_gap_dict(gap) for gap in gaps],
            "unchecked": [_line_dict(line) for line in unchecked],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def load_payload(
    raw: str | None,
) -> tuple[tuple[CoverageGap, ...], tuple[UncheckedLine, ...]] | None:
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or payload.get("version") != PAYLOAD_VERSION:
        return None
    gaps_raw = payload.get("gaps")
    unchecked_raw = payload.get("unchecked")
    if not isinstance(gaps_raw, list) or not isinstance(unchecked_raw, list):
        return None
    gaps = tuple(gap for item in gaps_raw if (gap := _gap_from_dict(item)) is not None)
    unchecked = tuple(
        line for item in unchecked_raw if (line := _line_from_dict(item)) is not None
    )
    if len(gaps) != len(gaps_raw) or len(unchecked) != len(unchecked_raw):
        return None
    return gaps, unchecked


def present_check(
    stored: StoredPlanCheck | None,
    *,
    fingerprint: str,
    has_plan: bool,
) -> PresentedCheck:
    """过期策略：旧缺口留着并标成 stale。当前已经没有计划时不展示旧缺口，也不算通过。"""
    if stored is None:
        return PresentedCheck(
            has_plan=has_plan,
            freshness="unchecked",
            source=None,
            outcome="no_plan" if not has_plan else "unchecked",
            gaps=(),
            unchecked=(),
        )
    freshness = "current" if stored.fingerprint == fingerprint else "stale"
    if not has_plan:
        return PresentedCheck(
            has_plan=False,
            freshness=freshness,
            source="empty",
            outcome="no_plan",
            gaps=(),
            unchecked=(),
            checked_at=stored.checked_at,
        )
    if stored.source == "empty":
        return PresentedCheck(
            has_plan=True,
            freshness="stale",
            source="empty",
            outcome="no_plan",
            gaps=(),
            unchecked=(),
            checked_at=stored.checked_at,
        )
    open_gaps = [gap for gap in stored.gaps if gap.change not in CLOSED_GAP_CHANGES]
    outcome = "gaps" if open_gaps else "partial" if stored.unchecked else "clear"
    return PresentedCheck(
        has_plan=True,
        freshness=freshness,
        source=stored.source,
        outcome=outcome,
        gaps=stored.gaps,
        unchecked=stored.unchecked,
        checked_at=stored.checked_at,
    )


def _synopsis_sentences(synopsis: str) -> list[str]:
    text = synopsis.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return []
    sentences: list[str] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        pieces = [piece.strip() for piece in SENTENCE_SPLIT_RE.split(stripped)]
        sentences.extend(piece for piece in pieces if piece)
    return sentences


def _synopsis_item(index: int, sentence: str) -> PlanItem:
    return PlanItem(
        ref=f"synopsis:{index}",
        origin="synopsis",
        plan_text=sentence,
        note=sentence,
    )


def _beat_item(beat: BeatInput) -> PlanItem:
    note = " ".join(beat.note.split())
    intent = " ".join(beat.intent.split())
    parts = [part for part in (note, intent) if part]
    plan_text = " / ".join(parts) if parts else beat.thread_name
    return PlanItem(
        ref=f"beat:{beat.id}",
        origin="beat",
        plan_text=plan_text,
        beat_kind=beat.kind,
        thread_name=beat.thread_name,
        note=note,
        intent=intent,
        thread_id=beat.thread_id,
    )


def _quoted_phrases(text: str) -> list[str]:
    phrases: list[str] = []
    for match in QUOTE_RE.finditer(text):
        phrase = next(group for group in match.groups() if group)
        cleaned = phrase.strip()
        if cleaned:
            phrases.append(cleaned)
    return phrases


def _proper_names(text: str) -> list[str]:
    names = [match.group(0) for match in LATIN_NAME_RE.finditer(text)]
    names.extend(_chinese_names(text))
    return names


def _chinese_names(text: str) -> list[str]:
    names: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        surname = _surname_at(text, index)
        if surname is None or not _starts_name(text, index):
            index += 1
            continue
        given: list[str] = []
        cursor = index + len(surname)
        while cursor < length and len(given) < 2 and _is_given_char(text[cursor]):
            given.append(text[cursor])
            cursor += 1
        if not given:
            index += len(surname)
            continue
        bounded = cursor >= length or not _is_cjk(text[cursor])
        if len(given) == 2 and bounded:
            candidate = surname + "".join(given)
        else:
            candidate = surname + given[0]
        if candidate not in NAME_BLOCKLIST:
            names.append(candidate)
        index += len(surname)
    return names


def _starts_name(text: str, index: int) -> bool:
    """专名从句首、标点，或「是／叫／见」这类字后面开始。"""
    if index == 0:
        return True
    previous = text[index - 1]
    if not _is_cjk(previous):
        return True
    return previous in NAME_INTRODUCERS


def _surname_at(text: str, index: int) -> str | None:
    for surname in COMPOUND_SURNAMES:
        if text.startswith(surname, index):
            return surname
    char = text[index]
    if char in SINGLE_SURNAMES:
        return char
    return None


def _is_given_char(char: str) -> bool:
    return _is_cjk(char) and char not in GIVEN_STOP


def _is_cjk(char: str) -> bool:
    return "\u4e00" <= char <= "\u9fff"


def _short_label(note: str) -> str | None:
    text = " ".join(note.split())
    if not text or not 2 <= len(text) <= 24:
        return None
    if any(char in NOTE_PUNCT for char in text):
        return None
    return text


def _thread_anchor(name: str | None) -> str | None:
    text = " ".join((name or "").split())
    if not text or text in THREAD_NAME_SKIP or not 2 <= len(text) <= 16:
        return None
    return text


def _prefer_longer(anchors: list[str]) -> list[str]:
    unique: list[str] = []
    for anchor in anchors:
        cleaned = anchor.strip()
        if cleaned and cleaned not in unique:
            unique.append(cleaned)
    return [
        anchor
        for anchor in unique
        if not any(anchor != other and anchor in other for other in unique)
    ]


def _cites_plan(detail: str, item: PlanItem) -> bool:
    source = normalize_for_search(item.plan_text)
    target = normalize_for_search(detail)
    if len(source) < 2:
        return len(target) >= 2
    return any(source[index : index + 2] in target for index in range(len(source) - 1))


def _extract_json_object(raw: str) -> dict | None:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    parsed = _loads_object(text)
    if parsed is not None:
        return parsed
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    return _loads_object(text[start : end + 1])


def _loads_object(text: str) -> dict | None:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        try:
            from json_repair import loads as repair_json_loads
        except ImportError:
            return None
        try:
            parsed = repair_json_loads(text)
        except (ValueError, TypeError, json.JSONDecodeError):
            return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _clip_prose(prose: str) -> str:
    if len(prose) <= PROSE_LIMIT:
        return prose
    return prose[:12000] + "\n……（中间略去）……\n" + prose[-4000:]


def _plan_key(item: PlanItem) -> tuple[str, str] | None:
    if item.origin == "synopsis":
        text = normalize_for_search(item.plan_text)
        if not text:
            return None
        return ("synopsis", text)
    if not item.thread_id or not item.beat_kind:
        return None
    return ("beat", f"{item.thread_id}\0{item.beat_kind}")


def _gap_key(gap: CoverageGap) -> tuple[str, str] | None:
    if gap.origin == "synopsis":
        text = normalize_for_search(gap.plan_text)
        if not text:
            return None
        return ("synopsis", text)
    if not gap.thread_id or not gap.beat_kind:
        return None
    return ("beat", f"{gap.thread_id}\0{gap.beat_kind}")


def _with_change(gap: CoverageGap, change: str) -> CoverageGap:
    return CoverageGap(
        ref=gap.ref,
        origin=gap.origin,
        plan_text=gap.plan_text,
        basis=gap.basis,
        missing=gap.missing,
        detail=gap.detail,
        beat_kind=gap.beat_kind,
        thread_name=gap.thread_name,
        thread_id=gap.thread_id,
        change=change,
    )


def _gap_dict(gap: CoverageGap) -> dict[str, object]:
    return {
        "ref": gap.ref,
        "origin": gap.origin,
        "plan_text": gap.plan_text,
        "basis": gap.basis,
        "missing": list(gap.missing),
        "detail": gap.detail,
        "beat_kind": gap.beat_kind,
        "thread_name": gap.thread_name,
        "thread_id": gap.thread_id,
        "change": gap.change,
    }


def _line_dict(line: UncheckedLine) -> dict[str, object]:
    return {
        "ref": line.ref,
        "origin": line.origin,
        "plan_text": line.plan_text,
        "beat_kind": line.beat_kind,
        "thread_name": line.thread_name,
    }


def _gap_from_dict(raw: object) -> CoverageGap | None:
    if not isinstance(raw, dict):
        return None
    ref = raw.get("ref")
    origin = raw.get("origin")
    plan_text = raw.get("plan_text")
    basis = raw.get("basis")
    missing = raw.get("missing")
    detail = raw.get("detail", "")
    if (
        not isinstance(ref, str)
        or origin not in {"synopsis", "beat"}
        or not isinstance(plan_text, str)
        or basis not in {"literal", "model"}
        or not isinstance(missing, list)
        or not all(isinstance(item, str) for item in missing)
        or not isinstance(detail, str)
    ):
        return None
    beat_kind = raw.get("beat_kind")
    thread_name = raw.get("thread_name")
    thread_id = raw.get("thread_id")
    change = raw.get("change")
    if beat_kind is not None and not isinstance(beat_kind, str):
        return None
    if thread_name is not None and not isinstance(thread_name, str):
        return None
    if thread_id is not None and not isinstance(thread_id, str):
        return None
    if change is not None and change not in GAP_CHANGES:
        return None
    return CoverageGap(
        ref=ref,
        origin=origin,
        plan_text=plan_text,
        basis=basis,
        missing=tuple(missing),
        detail=detail,
        beat_kind=beat_kind,
        thread_name=thread_name,
        thread_id=thread_id,
        change=change,
    )


def _line_from_dict(raw: object) -> UncheckedLine | None:
    if not isinstance(raw, dict):
        return None
    ref = raw.get("ref")
    origin = raw.get("origin")
    plan_text = raw.get("plan_text")
    if (
        not isinstance(ref, str)
        or origin not in {"synopsis", "beat"}
        or not isinstance(plan_text, str)
    ):
        return None
    beat_kind = raw.get("beat_kind")
    thread_name = raw.get("thread_name")
    if beat_kind is not None and not isinstance(beat_kind, str):
        return None
    if thread_name is not None and not isinstance(thread_name, str):
        return None
    return UncheckedLine(
        ref=ref,
        origin=origin,
        plan_text=plan_text,
        beat_kind=beat_kind,
        thread_name=thread_name,
    )
