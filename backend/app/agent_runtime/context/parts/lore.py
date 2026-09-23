"""Inject constant lore and keyword hits into writer and plan context."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.agent_runtime.context.errors import ContextBuildError
from app.agent_runtime.context.types import ContextMessage
from app.agent_runtime.graph.state import AgentRuntimeState
from app.agent_runtime.persistence.model import PlanTodoRecord
from app.agent_runtime.persistence.plan_repo import get_plan_by_session, list_todos_by_plan
from app.storage.models.chapter import Chapter
from app.storage.models.character import Character
from app.storage.repos import character_repo, world_info_entry_repo, world_info_repo
from app.tavern.lore import LoreCandidate, keywords_from_json, render_setting_pack, select_lore_entries


WRITING_AGENTS = {"writer", "plan"}
_RECENT_CHAPTER_LIMIT = 8


async def build_lore_pack(
    state: AgentRuntimeState,
    agent_name: str,
    db_session: AsyncSession,
) -> ContextMessage | None:
    """Build the setting fragment for writing agents."""
    if agent_name not in WRITING_AGENTS:
        return None
    project_id = state.get("project_id")
    if not project_id:
        return None
    try:
        characters = await character_repo.list_all_by_project(db_session, project_id)
        haystack = await _writing_haystack(db_session, state, project_id)
        lore_entries = await _project_lore(db_session, project_id)
    except Exception as exc:
        raise ContextBuildError("lore", "failed to load writing materials", cause=exc) from exc

    selected = select_lore_entries(lore_entries, haystack)
    content = render_setting_pack(
        characters=_ordered_characters(characters),
        lore_entries=selected,
    )
    if content is None:
        return None
    return ContextMessage(role="system", content=content, metadata={"part": "lore"})


def _ordered_characters(characters: list[Character]) -> list[tuple[str, str]]:
    ordered = sorted(characters, key=lambda item: (not item.is_favorited, item.name))
    return [(item.name, item.description) for item in ordered if item.description.strip()]


async def _project_lore(db_session: AsyncSession, project_id: str) -> list[LoreCandidate]:
    world_info = await world_info_repo.get_by_project_id(db_session, project_id)
    if world_info is None:
        return []
    entries = await world_info_entry_repo.list_enabled_by_world_info(db_session, world_info.id)
    return [
        LoreCandidate(
            name=entry.name,
            content=entry.content,
            order=entry.order,
            is_constant=entry.is_constant,
            keywords=keywords_from_json(entry.keywords_json),
        )
        for entry in entries
    ]


async def _writing_haystack(
    db_session: AsyncSession,
    state: AgentRuntimeState,
    project_id: str,
) -> str:
    parts = [state.get("user_request") or ""]
    session_id = state.get("session_id")
    if session_id:
        plan = await get_plan_by_session(db_session, session_id)
        if plan is not None:
            todos = await list_todos_by_plan(db_session, plan.id)
            parts.extend(_todo_text(todo) for todo in todos)
    titles = await db_session.execute(
        select(Chapter.title)
        .where(col(Chapter.project_id) == project_id)
        .order_by(col(Chapter.updated_at).desc())
        .limit(_RECENT_CHAPTER_LIMIT)
    )
    parts.extend(title for title in titles.scalars().all() if isinstance(title, str))
    return "\n".join(part for part in parts if part)


def _todo_text(todo: PlanTodoRecord) -> str:
    return todo.content or ""
