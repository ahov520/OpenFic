# -*- coding: utf-8 -*-
"""整项目备份/恢复测试：zip 导出、round-trip 还原、白名单红线与任务三态钩子。"""

import io
import json
import zipfile
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from app.agent_runtime.persistence.model import AgentDefinitionRecord
from app.background.events.publisher import BackgroundEventPublisher
from app.background.jobs import service as background_service
from app.background.jobs.constants import JOB_TYPE_PROJECT_BACKUP
from app.background.jobs.models import BackgroundJob
from app.background.runtime.context import JobContext
from app.background.runtime.dispatcher import dispatch_job
from app.background.runtime.registry import get_job_registry
from app.memory.chapter.summary_service import is_long_term_summary_stale
from app.project_backup import service as project_backup_service
from app.storage.models.character import Character
from app.storage.models.chapter import Chapter
from app.storage.models.chapter_summary import ChapterSummary
from app.storage.models.margin_note import ChapterMarginNote
from app.storage.models.note import Note, NoteCategory
from app.storage.models.plot_thread import PlotBeat, PlotThread
from app.storage.models.project import Project
from app.storage.models.volume import Volume
from app.storage.models.world_info import WorldInfo
from app.storage.models.world_info_entry import WorldInfoEntry
from app.storage.plan_coverage import CoverageGap, dump_payload
from app.storage.repos import (
    agent_definition_repo,
    chapter_repo,
    chapter_summary_repo,
    character_repo,
    margin_note_repo,
    note_category_repo,
    note_repo,
    plot_beat_repo,
    plot_thread_repo,
    project_repo,
    volume_repo,
    world_info_entry_repo,
    world_info_repo,
)


OLD_CH1_CONTENT = "第一章正文：雨夜，主角推门。灯还亮着，他没有回头。"
OLD_CH2_CONTENT = "第二章正文：门后是一条向下的长廊。"
ANCHOR_TEXT = "主角推门。"


async def _seed_full_project(session, *, cover_path: str | None = None) -> Project:
    """建一个含全部 12 类实体的样例项目。

    章节字数 600 > 摘要最小字数阈值，保证长程摘要窗口有效；
    两章都有 ready 章节摘要，长程窗口才能完整构建。
    """
    project = Project(
        title="备份测试小说",
        description="含全部实体的样例",
        word_count=120,
        chapter_count=2,
        cover_path=cover_path,
    )
    await project_repo.create(session, project)

    volume_a = Volume(project_id=project.id, title="第一卷", order=0, chapter_count=1)
    await volume_repo.create(session, volume_a)
    volume_b = Volume(project_id=project.id, title="第二卷", order=1, chapter_count=1)
    await volume_repo.create(session, volume_b)

    thread = PlotThread(project_id=project.id, name="回家线", intent="贯穿全书的回家伏笔", sort_order=0)
    await plot_thread_repo.create(session, thread)

    chapter_one = Chapter(
        project_id=project.id,
        volume_id=volume_a.id,
        title="第一章",
        content=OLD_CH1_CONTENT,
        synopsis="主角雨夜回家。",
        word_count=600,
        order=0,
        plan_check_fingerprint="fingerprint-1",
        plan_check_source="literal",
        plan_check_payload=dump_payload(
            [
                CoverageGap(
                    ref="s1",
                    origin="beat",
                    plan_text="推门要有回应",
                    basis="literal",
                    beat_kind="plant",
                    thread_name=thread.name,
                    thread_id=thread.id,
                )
            ],
            [],
        ),
        plan_check_at=datetime.now(UTC),
    )
    await chapter_repo.create(session, chapter_one)
    chapter_two = Chapter(
        project_id=project.id,
        volume_id=volume_b.id,
        title="第二章",
        content=OLD_CH2_CONTENT,
        word_count=600,
        order=0,
    )
    await chapter_repo.create(session, chapter_two)

    chapter_summary_one = ChapterSummary(
        project_id=project.id,
        summary_type="chapter",
        status="ready",
        chapter_id=chapter_one.id,
        volume_id=volume_a.id,
        chapter_order=0,
        summary="第一章摘要",
        source_chapter_ids_json=json.dumps([chapter_one.id]),
    )
    await chapter_summary_repo.create(session, chapter_summary_one)
    chapter_summary_two = ChapterSummary(
        project_id=project.id,
        summary_type="chapter",
        status="ready",
        chapter_id=chapter_two.id,
        volume_id=volume_b.id,
        chapter_order=0,
        summary="第二章摘要",
        source_chapter_ids_json=json.dumps([chapter_two.id]),
    )
    await chapter_summary_repo.create(session, chapter_summary_two)
    long_term_summary = ChapterSummary(
        project_id=project.id,
        summary_type="long_term",
        status="ready",
        volume_id=volume_a.id,
        start_order=1,
        end_order=2,
        summary="前两章长程摘要",
        source_chapter_ids_json=json.dumps([chapter_one.id, chapter_two.id]),
        source_chapter_summary_signatures_json=json.dumps(["旧库里的签名", "必然失配"]),
    )
    await chapter_summary_repo.create(session, long_term_summary)

    await margin_note_repo.create(
        session,
        ChapterMarginNote(
            project_id=project.id,
            chapter_id=chapter_one.id,
            anchor_text=ANCHOR_TEXT,
            context_before="雨夜，",
            context_after="灯还亮着",
            body="这里要埋一个回家的伏笔。",
            status="open",
        ),
    )
    await margin_note_repo.create(
        session,
        ChapterMarginNote(
            project_id=project.id,
            chapter_id=chapter_two.id,
            anchor_text="长廊",
            body="这句已经处理过。",
            status="struck",
        ),
    )

    beat = PlotBeat(
        project_id=project.id, thread_id=thread.id, chapter_id=chapter_one.id, kind="plant", note="推门即埋下"
    )
    await plot_beat_repo.create(session, beat)

    await character_repo.create(
        session, Character(project_id=project.id, name="林晚棠", description="主角")
    )
    await character_repo.create(
        session, Character(project_id=project.id, name="沈照", description="门后的人")
    )

    world_info = WorldInfo(project_id=project.id, name="主世界书", description="备份测试")
    await world_info_repo.create(session, world_info)
    await world_info_entry_repo.create(
        session,
        WorldInfoEntry(
            world_info_id=world_info.id,
            uid=1,
            name="雨夜镇",
            order=0,
            content="终年下雨的小镇",
            keywords_json=json.dumps(["雨夜镇"]),
        ),
    )
    await world_info_entry_repo.create(
        session,
        WorldInfoEntry(
            world_info_id=world_info.id,
            uid=2,
            name="长廊",
            order=1,
            content="门后的向下长廊",
        ),
    )

    parent_category = NoteCategory(project_id=project.id, title="设定")
    await note_category_repo.create(session, parent_category)
    child_category = NoteCategory(
        project_id=project.id, parent_id=parent_category.id, title="角色细节"
    )
    await note_category_repo.create(session, child_category)
    await note_repo.create(
        session,
        Note(
            project_id=project.id,
            category_id=parent_category.id,
            title="世界观备忘",
            content="雨夜镇没有白天。",
        ),
    )
    await note_repo.create(
        session,
        Note(
            project_id=project.id,
            title="碎片灵感",
            content="隐藏的笔记也要备份。",
            is_hidden=True,
        ),
    )

    await agent_definition_repo.create(
        session,
        AgentDefinitionRecord(
            key="backup-planner",
            display_name="旧名字",
            description="备份测试用定义",
            kind="primary",
            prompt_agent_name="planner",
            enabled_tool_categories=["writing"],
            enabled_skills=[],
            metadata_json={"team": "backup-test"},
        ),
    )
    return project


async def _create_backup_job(client: AsyncClient, project_id: str) -> dict:
    response = await client.post(
        f"/api/v1/projects/{project_id}/backups",
        json={"local_date": "2026-07-28"},
    )
    assert response.status_code == 201
    return response.json()


async def _run_backup_job(client: AsyncClient, session, job_id: str) -> dict:
    job = await background_service.get_job(session, job_id)
    assert job is not None
    job.status = "running"
    await session.commit()
    context = JobContext(session=session, job=job, publisher=BackgroundEventPublisher(None))
    result = await dispatch_job(context)
    await background_service.mark_succeeded(
        session, context.publisher, context.job, result=result
    )
    await session.commit()
    return result


def _download_backup_zip(download) -> bytes:
    assert download.status_code == 200
    assert "attachment" in download.headers["content-disposition"]
    return download.content


def _build_backup_zip_bytes(meta: dict, entities: dict[str, list[dict]]) -> bytes:
    """手工构造备份 zip，用于截断/冲突等异常路径测试。"""
    files = {
        project_backup_service.META_FILE_NAME: json.dumps(meta, ensure_ascii=False),
    }
    for key, filename in project_backup_service.ENTITY_FILE_NAMES.items():
        files[filename] = json.dumps(entities.get(key, []), ensure_ascii=False)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as bundle:
        for name in sorted(files):
            bundle.writestr(name, files[name])
    return buffer.getvalue()


def _empty_meta(**overrides) -> dict:
    meta: dict = {
        "kind": project_backup_service.BACKUP_KIND,
        "schema_version": project_backup_service.BACKUP_SCHEMA_VERSION,
        "exported_at": "2026-07-28T00:00:00+00:00",
        "project": {
            "title": "空项目",
            "description": None,
            "word_count": 0,
            "chapter_count": 0,
            "cover_path": None,
        },
        "counts": {key: 0 for key in project_backup_service.ENTITY_FILE_NAMES},
    }
    meta.update(overrides)
    return meta


@pytest.mark.asyncio
async def test_backup_whitelist_and_counts_match_database(
    client: AsyncClient, session, monkeypatch, tmp_path
) -> None:
    async def skip_cancellation_check(_context: JobContext) -> None:
        return None

    monkeypatch.setattr(project_backup_service.settings, "project_backups_dir", tmp_path)
    monkeypatch.setattr(JobContext, "check_cancelled", skip_cancellation_check)
    project = await _seed_full_project(session)

    created = await _create_backup_job(client, project.id)
    assert created["status"] == "pending"
    assert created["filename"] == "备份测试小说-项目备份-2026-07-28.zip"

    result = await _run_backup_job(client, session, created["id"])
    assert result["counts"]["volumes"] == 2
    assert result["counts"]["chapters"] == 2
    assert result["counts"]["chapter_summaries"] == 2
    assert result["counts"]["long_term_summaries"] == 1
    assert result["counts"]["margin_notes"] == 2
    assert result["counts"]["agent_definitions"] == 1

    status_response = await client.get(
        f"/api/v1/projects/{project.id}/backups/{created['id']}"
    )
    assert status_response.status_code == 200
    assert status_response.json()["download_url"]

    content = _download_backup_zip(
        await client.get(f"/api/v1/projects/{project.id}/backups/{created['id']}/download")
    )

    # 红线：zip 清单只允许白名单文件（meta + 13 个实体 JSON），
    # settings / llm_audit_log / 模型凭据永不出现。
    with zipfile.ZipFile(io.BytesIO(content)) as bundle:
        names = set(bundle.namelist())
        file_texts = {name: bundle.read(name).decode("utf-8").lower() for name in names}
    assert names == project_backup_service.BACKUP_WHITELIST_FILE_NAMES
    assert "settings.json" not in names and "llm_audit_log.json" not in names
    # 对解压后的明文逐文件断言，压缩字节里查字面量没有证明力。
    forbidden_markers = ("api_key", "authorization", "secret", "password", "llm_audit")
    for name, text in file_texts.items():
        for marker in forbidden_markers:
            assert marker not in text, f"{name} 中出现了 {marker}"

    # 与数据库逐类对比
    db_counts = {
        "volumes": len(await volume_repo.list_by_project(session, project.id)),
        "chapters": len(await chapter_repo.list_by_project(session, project.id)),
        "chapter_summaries": len(
            await chapter_summary_repo.list_chapter_summaries_by_project(session, project.id)
        ),
        "long_term_summaries": len(
            await chapter_summary_repo.list_long_term_summaries_by_project(session, project.id)
        ),
        "margin_notes": len(await margin_note_repo.list_by_project(session, project.id)),
        "plot_threads": len(await plot_thread_repo.list_by_project(session, project.id)),
        "plot_beats": len(await plot_beat_repo.list_by_project(session, project.id)),
        "characters": len(await character_repo.list_all_by_project(session, project.id)),
        "world_info": 1,
        "world_info_entries": len(
            await world_info_entry_repo.list_all_by_world_info(
                session, (await world_info_repo.get_by_project_id(session, project.id)).id
            )
        ),
        "note_categories": len(await note_category_repo.list_by_project(session, project.id)),
        "notes": len(await note_repo.list_by_project(session, project.id)),
        "agent_definitions": len(await agent_definition_repo.list_all(session)),
    }

    with zipfile.ZipFile(io.BytesIO(content)) as bundle:
        zipped = {
            key: json.loads(bundle.read(filename))
            for key, filename in project_backup_service.ENTITY_FILE_NAMES.items()
        }
        meta = json.loads(bundle.read("meta.json"))

    assert {key: len(rows) for key, rows in zipped.items()} == db_counts
    assert meta["counts"] == db_counts
    assert meta["kind"] == project_backup_service.BACKUP_KIND
    assert meta["project"]["title"] == "备份测试小说"


@pytest.mark.asyncio
async def test_backup_preview_reports_zip_counts(
    client: AsyncClient, session, monkeypatch, tmp_path
) -> None:
    async def skip_cancellation_check(_context: JobContext) -> None:
        return None

    monkeypatch.setattr(project_backup_service.settings, "project_backups_dir", tmp_path)
    monkeypatch.setattr(JobContext, "check_cancelled", skip_cancellation_check)
    project = await _seed_full_project(session)
    created = await _create_backup_job(client, project.id)
    await _run_backup_job(client, session, created["id"])
    content = _download_backup_zip(
        await client.get(f"/api/v1/projects/{project.id}/backups/{created['id']}/download")
    )

    preview = await client.post(
        "/api/v1/project-backups/preview",
        files={"archive": ("backup.zip", content, "application/zip")},
    )
    assert preview.status_code == 200
    data = preview.json()
    assert data["kind"] == project_backup_service.BACKUP_KIND
    assert data["project_title"] == "备份测试小说"
    assert data["counts"]["chapters"] == 2
    assert data["counts"]["margin_notes"] == 2
    assert data["total_entities"] == 21


@pytest.mark.asyncio
async def test_restore_rebuilds_fresh_project_with_remapped_foreign_keys(
    client: AsyncClient, session, monkeypatch, tmp_path
) -> None:
    async def skip_cancellation_check(_context: JobContext) -> None:
        return None

    monkeypatch.setattr(project_backup_service.settings, "project_backups_dir", tmp_path)
    monkeypatch.setattr(
        project_backup_service.settings, "covers_dir", tmp_path / "covers"
    )
    cover_file = tmp_path / "covers" / "backup-cover.png"
    cover_file.parent.mkdir(parents=True, exist_ok=True)
    cover_file.write_bytes(b"png-bytes")

    monkeypatch.setattr(JobContext, "check_cancelled", skip_cancellation_check)
    project = await _seed_full_project(session, cover_path="backup-cover.png")
    created = await _create_backup_job(client, project.id)
    await _run_backup_job(client, session, created["id"])
    content = _download_backup_zip(
        await client.get(f"/api/v1/projects/{project.id}/backups/{created['id']}/download")
    )

    # 旧库对照物
    old_chapters = await chapter_repo.list_by_project(session, project.id)
    old_chapter_one = next(ch for ch in old_chapters if ch.title == "第一章")
    old_chapter_two = next(ch for ch in old_chapters if ch.title == "第二章")
    old_world_info = await world_info_repo.get_by_project_id(session, project.id)
    old_categories = await note_category_repo.list_by_project(session, project.id)
    old_summaries = await chapter_summary_repo.list_chapter_summaries_by_project(
        session, project.id
    )
    old_summary = next(s for s in old_summaries if s.chapter_id == old_chapter_one.id)
    old_long_term = (
        await chapter_summary_repo.list_long_term_summaries_by_project(session, project.id)
    )[0]
    old_threads = await plot_thread_repo.list_by_project(session, project.id)

    # agent_definitions upsert 语义准备：改掉既有 key，再补一个新 key
    planner = await agent_definition_repo.get_by_key(session, "backup-planner")
    planner.display_name = "导出后被改动的名字"
    await agent_definition_repo.update(session, planner)
    await agent_definition_repo.create(
        session,
        AgentDefinitionRecord(
            key="backup-reviewer",
            display_name="导出后才加的审稿人",
            kind="sub",
            prompt_agent_name="reviewer",
        ),
    )

    restored = await client.post(
        "/api/v1/project-backups/restore",
        files={"archive": ("backup.zip", content, "application/zip")},
    )
    assert restored.status_code == 201
    data = restored.json()
    new_project_id = data["project_id"]
    assert new_project_id != project.id
    assert data["title"] == "备份测试小说"
    assert data["counts"]["chapters"] == 2

    # 各类实体计数一致
    new_volumes = await volume_repo.list_by_project(session, new_project_id)
    new_chapters = await chapter_repo.list_by_project(session, new_project_id)
    new_summaries = await chapter_summary_repo.list_chapter_summaries_by_project(
        session, new_project_id
    )
    new_long_terms = await chapter_summary_repo.list_long_term_summaries_by_project(
        session, new_project_id
    )
    new_margin_notes = await margin_note_repo.list_by_project(session, new_project_id)
    new_threads = await plot_thread_repo.list_by_project(session, new_project_id)
    new_beats = await plot_beat_repo.list_by_project(session, new_project_id)
    new_characters = await character_repo.list_all_by_project(session, new_project_id)
    new_world_info = await world_info_repo.get_by_project_id(session, new_project_id)
    new_entries = await world_info_entry_repo.list_all_by_world_info(
        session, new_world_info.id
    )
    new_categories = await note_category_repo.list_by_project(session, new_project_id)
    new_notes = await note_repo.list_by_project(session, new_project_id)

    assert len(new_volumes) == 2
    assert len(new_chapters) == 2
    assert len(new_summaries) == 2
    assert len(new_long_terms) == 1
    assert len(new_margin_notes) == 2
    assert len(new_threads) == 1
    assert len(new_beats) == 1
    assert len(new_characters) == 2
    assert len(new_entries) == 2
    assert len(new_categories) == 2
    assert len(new_notes) == 2

    # 全部实体重新生成 id
    new_chapter_one = next(ch for ch in new_chapters if ch.title == "第一章")
    new_chapter_two = next(ch for ch in new_chapters if ch.title == "第二章")
    assert new_chapter_one.id != old_chapter_one.id
    assert new_chapter_two.id != old_chapter_two.id

    # 章节正文与旁注锚点逐字一致
    assert new_chapter_one.content == OLD_CH1_CONTENT
    assert new_chapter_two.content == OLD_CH2_CONTENT
    open_note = next(note for note in new_margin_notes if note.status == "open")
    struck_note = next(note for note in new_margin_notes if note.status == "struck")
    assert open_note.anchor_text == ANCHOR_TEXT
    assert open_note.body == "这里要埋一个回家的伏笔。"
    assert struck_note.status == "struck"

    # 封面文件还在本机磁盘时保留路径
    assert new_chapter_one.project_id == new_project_id
    restored_project = await project_repo.get_by_id(session, new_project_id)
    assert restored_project.cover_path == "backup-cover.png"

    # 外键指向新 id
    assert open_note.chapter_id == new_chapter_one.id
    assert struck_note.chapter_id == new_chapter_two.id
    assert open_note.chapter_id != old_chapter_one.id
    assert new_world_info.id != old_world_info.id
    assert all(entry.world_info_id == new_world_info.id for entry in new_entries)
    assert new_beats[0].thread_id == new_threads[0].id
    assert new_beats[0].chapter_id == new_chapter_one.id

    # plan_check_payload 内嵌的旧 thread_id 已按映射替换
    new_payload = json.loads(new_chapter_one.plan_check_payload)
    assert new_payload["gaps"][0]["thread_id"] == new_threads[0].id
    assert new_payload["gaps"][0]["thread_id"] != old_threads[0].id

    # 笔记分类父子关系按新 id 重建
    new_parent = next(c for c in new_categories if c.title == "设定")
    new_child = next(c for c in new_categories if c.title == "角色细节")
    assert new_child.parent_id == new_parent.id
    assert new_parent.id != old_categories[0].id
    category_note = next(n for n in new_notes if n.title == "世界观备忘")
    assert category_note.category_id == new_parent.id
    hidden_note = next(n for n in new_notes if n.title == "碎片灵感")
    assert hidden_note.is_hidden is True and hidden_note.category_id is None

    # 章梗概的内嵌 source_chapter_ids_json 已替换为新章节 id
    new_summary_one = next(s for s in new_summaries if s.chapter_id == new_chapter_one.id)
    assert json.loads(new_summary_one.source_chapter_ids_json) == [new_chapter_one.id]
    assert json.loads(old_summary.source_chapter_ids_json) == [old_chapter_one.id]
    new_long_term = new_long_terms[0]
    assert json.loads(new_long_term.source_chapter_ids_json) == [
        new_chapter_one.id,
        new_chapter_two.id,
    ]

    # 长程摘要按新章节 id 重算源签名：还原后不再被误判 stale
    assert json.loads(old_long_term.source_chapter_summary_signatures_json) == [
        "旧库里的签名",
        "必然失配",
    ]
    assert is_long_term_summary_stale(
        new_long_term, new_chapters, new_summaries, new_volumes
    ) is False

    # agent_definitions 全局表按 key upsert：不重复、不删除、以备份内容为准
    upserted = await agent_definition_repo.get_by_key(session, "backup-planner")
    assert upserted.display_name == "旧名字"
    assert upserted.id == planner.id
    reviewer = await agent_definition_repo.get_by_key(session, "backup-reviewer")
    assert reviewer.display_name == "导出后才加的审稿人"

    # 导入语义是「还原为全新项目」：原项目一个字节都不动
    old_chapters_after = await chapter_repo.list_by_project(session, project.id)
    assert {ch.id for ch in old_chapters_after} == {old_chapter_one.id, old_chapter_two.id}
    assert all(ch.project_id == project.id for ch in old_chapters_after)


@pytest.mark.asyncio
async def test_restore_drops_cover_path_when_file_missing(
    client: AsyncClient, session, monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(
        project_backup_service.settings, "covers_dir", tmp_path / "covers"
    )
    meta = _empty_meta(
        project={
            "title": "封面丢失的项目",
            "description": None,
            "word_count": 0,
            "chapter_count": 0,
            "cover_path": "missing-cover.png",
        }
    )
    content = _build_backup_zip_bytes(meta, {})

    restored = await client.post(
        "/api/v1/project-backups/restore",
        files={"archive": ("backup.zip", content, "application/zip")},
    )
    assert restored.status_code == 201
    restored_project = await project_repo.get_by_id(session, restored.json()["project_id"])
    assert restored_project.cover_path is None


@pytest.mark.asyncio
async def test_restore_rejects_truncated_backup_counts_mismatch(
    client: AsyncClient,
) -> None:
    meta = _empty_meta()
    meta["counts"]["chapters"] = 1  # 清单声称有一章，实际内容为空
    content = _build_backup_zip_bytes(meta, {})

    response = await client.post(
        "/api/v1/project-backups/preview",
        files={"archive": ("backup.zip", content, "application/zip")},
    )
    assert response.status_code == 400
    assert "不一致" in response.json()["detail"]


@pytest.mark.asyncio
async def test_restore_failure_rolls_back_cleanly(client: AsyncClient, session) -> None:
    meta = _empty_meta()
    meta["counts"]["volumes"] = 1
    meta["counts"]["chapters"] = 1
    entities = {
        "volumes": [
            {"id": "vol-old", "project_id": "p-old", "title": "卷", "order": 0}
        ],
        "chapters": [
            {
                "id": "ch-old",
                "project_id": "p-old",
                "volume_id": "vol-missing",
                "title": "章",
                "content": "",
                "order": 0,
            }
        ],
    }
    content = _build_backup_zip_bytes(meta, entities)

    response = await client.post(
        "/api/v1/project-backups/restore",
        files={"archive": ("backup.zip", content, "application/zip")},
    )
    assert response.status_code == 400
    assert "卷" in response.json()["detail"]

    # 生产环境 get_session 在异常时回滚；这里显式回滚后验证无残留项目。
    await session.rollback()
    projects_after = await client.get("/api/v1/projects")
    assert projects_after.status_code == 200
    assert projects_after.json()["total"] == 0


@pytest.mark.asyncio
async def test_restore_rejects_conflicting_world_info_rows(
    client: AsyncClient, session
) -> None:
    meta = _empty_meta()
    meta["counts"]["world_info"] = 2
    entities = {
        "world_info": [
            {"id": "wi-a", "project_id": "p-old", "name": "第一本"},
            {"id": "wi-b", "project_id": "p-old", "name": "第二本"},
        ],
    }
    content = _build_backup_zip_bytes(meta, entities)

    response = await client.post(
        "/api/v1/project-backups/restore",
        files={"archive": ("backup.zip", content, "application/zip")},
    )
    # 两行世界书映射到同一个新项目，触发 project_id 唯一约束 → 400 而非 500。
    assert response.status_code == 400
    assert "冲突" in response.json()["detail"]

    await session.rollback()
    projects_after = await client.get("/api/v1/projects")
    assert projects_after.json()["total"] == 0


@pytest.mark.asyncio
async def test_cleanup_removes_expired_backup_zip_but_keeps_recent(
    session, monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(project_backup_service.settings, "project_backups_dir", tmp_path)
    expired_job = BackgroundJob(
        id="expired-backup",
        type=project_backup_service.BACKUP_JOB_TYPE,
        status="succeeded",
        result_json='{"expires_at":"2020-01-01T00:00:00+00:00"}',
    )
    fresh_job = BackgroundJob(
        id="fresh-backup",
        type=project_backup_service.BACKUP_JOB_TYPE,
        status="succeeded",
        result_json=json.dumps(
            {
                "expires_at": (
                    datetime.now(UTC) + timedelta(hours=1)
                ).isoformat()
            }
        ),
    )
    session.add(expired_job)
    session.add(fresh_job)
    await session.commit()

    _part, expired_path = project_backup_service.backup_file_paths("expired-backup")
    expired_path.write_text("stale", encoding="utf-8")
    _part, fresh_path = project_backup_service.backup_file_paths("fresh-backup")
    fresh_path.write_text("recent", encoding="utf-8")

    removed = await project_backup_service.cleanup_project_backup_files(session)
    assert removed == 1
    assert not expired_path.exists()
    assert fresh_path.exists()


@pytest.mark.asyncio
async def test_cleanup_keeps_part_file_while_backup_running(
    session, monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(project_backup_service.settings, "project_backups_dir", tmp_path)
    running_job = BackgroundJob(
        id="running-backup",
        type=project_backup_service.BACKUP_JOB_TYPE,
        status="running",
        payload_json="{}",
    )
    session.add(running_job)
    await session.commit()

    part_path, _output = project_backup_service.backup_file_paths("running-backup")
    part_path.write_text("writing", encoding="utf-8")

    assert await project_backup_service.cleanup_project_backup_files(session) == 0
    assert part_path.exists()


@pytest.mark.asyncio
async def test_restore_rejects_non_backup_zip(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/project-backups/preview",
        files={"archive": ("not-backup.zip", b"not a zip", "application/zip")},
    )
    assert response.status_code == 400
    assert "zip" in response.json()["detail"]


@pytest.mark.asyncio
async def test_failed_backup_cleans_files_and_marks_failed(
    client: AsyncClient, session, monkeypatch, tmp_path
) -> None:
    async def skip_cancellation_check(_context: JobContext) -> None:
        return None

    monkeypatch.setattr(project_backup_service.settings, "project_backups_dir", tmp_path)
    monkeypatch.setattr(JobContext, "check_cancelled", skip_cancellation_check)

    async def failing_writer(context):
        _part_path, output_path = project_backup_service.backup_file_paths(context.job_id)
        output_path.write_text("半成品", encoding="utf-8")
        raise RuntimeError("磁盘炸了")

    monkeypatch.setattr(project_backup_service, "write_project_backup", failing_writer)
    project = await _seed_full_project(session)
    created = await _create_backup_job(client, project.id)
    job = await background_service.get_job(session, created["id"])
    job.status = "running"
    await session.commit()
    context = JobContext(session=session, job=job, publisher=BackgroundEventPublisher(None))

    with pytest.raises(RuntimeError):
        await dispatch_job(context)

    _part_path, output_path = project_backup_service.backup_file_paths(job.id)
    assert output_path.exists()

    # 与 worker._mark_failed_after_rollback 相同的状态流转：先钩子后落状态
    definition = get_job_registry().get(JOB_TYPE_PROJECT_BACKUP)
    await definition.on_failed(context, "磁盘炸了")
    assert not output_path.exists()
    await background_service.mark_failed(
        session, context.publisher, context.job, error_message="磁盘炸了"
    )
    await session.commit()
    assert context.job.status == "failed"


@pytest.mark.asyncio
async def test_timeout_hook_cleans_files(
    client: AsyncClient, session, monkeypatch, tmp_path
) -> None:
    async def skip_cancellation_check(_context: JobContext) -> None:
        return None

    monkeypatch.setattr(project_backup_service.settings, "project_backups_dir", tmp_path)
    monkeypatch.setattr(JobContext, "check_cancelled", skip_cancellation_check)
    project = await _seed_full_project(session)
    created = await _create_backup_job(client, project.id)
    job = await background_service.get_job(session, created["id"])
    _part_path, output_path = project_backup_service.backup_file_paths(job.id)
    output_path.write_text("半成品", encoding="utf-8")

    definition = get_job_registry().get(JOB_TYPE_PROJECT_BACKUP)
    context = JobContext(session=session, job=job, publisher=BackgroundEventPublisher(None))
    await definition.on_timeout(context, "后台任务执行超时")
    assert not output_path.exists()


@pytest.mark.asyncio
async def test_cancel_endpoint_cleans_pending_backup_files(
    client: AsyncClient, session, monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(project_backup_service.settings, "project_backups_dir", tmp_path)
    project = await _seed_full_project(session)
    created = await _create_backup_job(client, project.id)
    job_id = created["id"]
    part_path, output_path = project_backup_service.backup_file_paths(job_id)
    part_path.write_text("partial", encoding="utf-8")
    output_path.write_text("complete", encoding="utf-8")

    cancelled = await client.post(f"/api/v1/projects/{project.id}/backups/{job_id}/cancel")

    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert not part_path.exists()
    assert not output_path.exists()


@pytest.mark.asyncio
async def test_backup_download_expired_returns_conflict(
    client: AsyncClient, session, monkeypatch, tmp_path
) -> None:
    async def skip_cancellation_check(_context: JobContext) -> None:
        return None

    monkeypatch.setattr(project_backup_service.settings, "project_backups_dir", tmp_path)
    monkeypatch.setattr(JobContext, "check_cancelled", skip_cancellation_check)
    project = await _seed_full_project(session)
    created = await _create_backup_job(client, project.id)
    job = await background_service.get_job(session, created["id"])
    job.status = "running"
    await session.commit()
    context = JobContext(session=session, job=job, publisher=BackgroundEventPublisher(None))
    result = await dispatch_job(context)
    expired_result = {**result, "expires_at": "2020-01-01T00:00:00+00:00"}
    await background_service.mark_succeeded(
        session, context.publisher, context.job, result=expired_result
    )
    await session.commit()

    response = await client.get(f"/api/v1/projects/{project.id}/backups/{job.id}/download")
    assert response.status_code == 409
