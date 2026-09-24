from textwrap import dedent

from pydantic import BaseModel, Field

from app.agent_runtime.tools.base import AgentTool
from app.agent_runtime.tools.impls.chapter.refs import (
    ChapterRef,
    VolumeRef,
    resolve_chapter_from_list,
    resolve_volume_from_list,
)
from app.agent_runtime.tools.registry import ToolRegistry
from app.storage.chapter_plan import read_chapter_plan
from app.storage.database import create_session
from app.storage.repos import chapter_repo, volume_repo


class ReadChapterInput(BaseModel):
    volume_ref: VolumeRef = Field(description="目标卷")
    chapter_ref: ChapterRef = Field(description="卷内的目标章节")


class ReadChapterOutput(BaseModel):
    order: int
    title: str
    content: str
    word_count: int
    synopsis: str
    writing_status: str


def format_chapter_content_with_line_numbers(content: str) -> str:
    if not content:
        return ""
    return "\n".join(
        f"{line_number}|{line}"
        for line_number, line in enumerate(content.splitlines(), start=1)
    )


@ToolRegistry.register
class ReadChapterTool(AgentTool):
    name: str = "read_chapter"
    description: str = dedent("""\
        读取指定卷内章节的完整内容
        必须使用volume_ref指定目标卷，并使用chapter_ref指定目标章节
        返回的content是按章节内从1开始的行号格式化后的结果，原始内容不含行号标记
        每个原始换行都会拆分为单独一行，并添加行号标记，格式为 `行号|内容`
        synopsis 是作者写好的章节梗概，writing_status 是写作进度。写正文或续写时遵守梗概，不要把梗概当成已经写过的正文
    """)
    access_level: str = "readonly"
    args_schema: type[BaseModel] = ReadChapterInput

    async def _execute(self, volume_ref: dict, chapter_ref: dict) -> str:
        volume = VolumeRef.model_validate(volume_ref)
        ref = ChapterRef.model_validate(chapter_ref)
        session = await create_session()
        try:
            volumes = await volume_repo.list_by_project(session, self.project_id)
            resolved_volume = resolve_volume_from_list(volumes, volume)
            matched = await chapter_repo.get_by_volume_ref(
                session,
                resolved_volume.id,
                ref_type=ref.type,
                ref_value=ref.value,
            )
            match = resolve_chapter_from_list([matched] if matched is not None else [], ref)
            synopsis, writing_status = read_chapter_plan(match)
            return ReadChapterOutput(
                order=match.order,
                title=match.title,
                content=format_chapter_content_with_line_numbers(match.content),
                word_count=match.word_count,
                synopsis=synopsis,
                writing_status=writing_status,
            ).model_dump_json()
        finally:
            await session.close()
