"""导出格式常量与文档规格定义。

导出格式（txt/epub/docx）贯穿请求 → payload → 文件名/媒体类型；
本模块是后缀、媒体类型与文档结构的唯一口径。
"""

from __future__ import annotations

from dataclasses import dataclass, field

# 支持的导出格式与对应文件后缀
EXPORT_FORMATS: tuple[str, ...] = ("txt", "epub", "docx")
DEFAULT_EXPORT_FORMAT = "txt"
EXPORT_FILE_SUFFIXES = frozenset({".txt", ".epub", ".docx"})
PART_SUFFIX = ".part"

# 下载时的媒体类型
EXPORT_MEDIA_TYPES: dict[str, str] = {
    "txt": "text/plain; charset=utf-8",
    "epub": "application/epub+zip",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def normalize_export_format(value: object) -> str:
    """校验并归一化导出格式；非法值抛 ValueError（调用方转为 400）。"""
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in EXPORT_FORMATS:
            return normalized
    raise ValueError(f"导出格式无效，仅支持 {'、'.join(EXPORT_FORMATS)}")


def export_suffix(export_format: str) -> str:
    """导出格式对应的后缀（入参须已归一化）。"""
    suffix = f".{export_format}"
    if suffix not in EXPORT_FILE_SUFFIXES:
        raise ValueError(f"导出格式无效: {export_format}")
    return suffix


@dataclass(frozen=True)
class ExportDocumentChapter:
    """单章正文（标题 + 规范化换行的正文）。"""

    title: str
    content: str


@dataclass(frozen=True)
class ExportDocumentVolume:
    """卷标题与其下章节；title 为 None 表示不渲染卷标题（纯章节模式）。"""

    title: str | None
    order: int
    chapters: list[ExportDocumentChapter] = field(default_factory=list)


@dataclass(frozen=True)
class ExportDocumentSpec:
    """整本书的结构化内容，供 EPUB/DOCX writer 消费。"""

    book_title: str
    author: str
    language: str = "zh"
    volumes: list[ExportDocumentVolume] = field(default_factory=list)
