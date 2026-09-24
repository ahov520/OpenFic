"""Chapter turns keep a short task card ahead of keyed lore."""

from app.tavern.lore import LoreCandidate, render_writing_turn


def test_writing_turn_puts_task_ahead_of_setting() -> None:
    content = render_writing_turn(
        characters=[("林晚", "说话冷淡")],
        lore_entries=[
            LoreCandidate(
                name="常驻",
                content="灵气复苏",
                order=1,
                is_constant=True,
                keywords=(),
            )
        ],
        user_request="写青云宗开门",
        open_todos=["进行中：落地潜入单元", "待办：先不要写"],
    )
    assert content is not None
    assert content.index("<chapter_task>") < content.index("<setting>")
    assert "写青云宗开门" in content
    assert "落地潜入单元" in content
    assert "灵气复苏" in content
    assert "后面的不能覆盖前面的" in content


def test_writing_turn_clips_long_steps_and_skips_empty_turn() -> None:
    content = render_writing_turn(
        characters=[],
        lore_entries=[],
        user_request="",
        open_todos=["步骤" * 300, "第二条"],
    )
    assert content is not None
    assert "..." in content
    assert len(content) < 2500
    assert render_writing_turn(characters=[], lore_entries=[], user_request="  ", open_todos=[]) is None


def test_builtin_writing_prompts_keep_handoff_boundaries() -> None:
    from app.prompts.loader import load_prompt_chain

    writer = "\n".join(entry.content for entry in load_prompt_chain("builtin-agent--writer") or [])
    plan = "\n".join(entry.content for entry in load_prompt_chain("builtin-agent--plan") or [])
    composer = "\n".join(entry.content for entry in load_prompt_chain("builtin-agent--composer") or [])
    reviewer = "\n".join(entry.content for entry in load_prompt_chain("builtin-agent--reviewer") or [])

    assert "你只写正文和章节标题" in writer
    assert "【须守】" in writer
    assert "不要把整本书读进来" in writer
    assert "大约 1800-2200 字只是默认节奏" in writer

    assert "四件事不要混在一次委派里" in plan
    assert "章节全名" in plan

    assert "【钩子】" in composer
    assert "【禁写】" in composer

    assert "你不写正文" in reviewer
    assert "不要用「每段必须少于 60 字」否决" in reviewer
    assert "裸时间词" in reviewer
    assert "引用：「不超过四十字的原句」" in reviewer
    assert "1800-2200字的范围内" not in reviewer
