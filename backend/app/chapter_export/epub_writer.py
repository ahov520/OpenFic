"""EPUB 导出 writer：按卷/章结构生成 EPUB，中文元数据（书名/作者/语言 zh）。"""

from __future__ import annotations

from pathlib import Path

from ebooklib import epub

from app.chapter_export.formats import ExportDocumentSpec

_CHAPTER_FILE_TEMPLATE = "chapter_{:04d}.xhtml"
_VOLUME_FILE_TEMPLATE = "volume_{:04d}.xhtml"


def _escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _chapter_document(index: int, title: str, content: str) -> epub.EpubHtml:
    paragraphs = [paragraph.strip() for paragraph in content.split("\n")]
    body = "".join(
        f"<p>{_escape(paragraph)}</p>" for paragraph in paragraphs if paragraph
    )
    document = epub.EpubHtml(
        title=title,
        file_name=_CHAPTER_FILE_TEMPLATE.format(index),
        lang="zh",
    )
    document.content = f"<h2>{_escape(title)}</h2>{body}"
    return document


def write_epub(path: str | Path, spec: ExportDocumentSpec) -> None:
    """按 spec 生成 EPUB 文件并写盘。

    卷标题映射为一级标题（独立卷页），章节映射为二级标题文档；
    元数据写入书名、作者与语言（zh）。
    """
    book = epub.EpubBook()
    book.set_title(spec.book_title)
    book.set_language(spec.language)
    book.add_author(spec.author)
    book.add_item(epub.EpubNav())
    book.add_item(epub.EpubNcx())

    spine: list[object] = ["nav"]
    toc: list[object] = []
    chapter_index = 0
    volume_index = 0

    for volume in spec.volumes:
        volume_entry: epub.EpubHtml | epub.Section
        volume_chapters: list[epub.EpubHtml] = []
        if volume.title is not None:
            volume_index += 1
            volume_document = epub.EpubHtml(
                title=volume.title,
                file_name=_VOLUME_FILE_TEMPLATE.format(volume_index),
                lang=spec.language,
            )
            volume_document.content = f"<h1>{_escape(volume.title)}</h1>"
            book.add_item(volume_document)
            spine.append(volume_document)
            volume_entry = epub.Section(volume.title)
        else:
            volume_entry = epub.Section(spec.book_title)
        for chapter in volume.chapters:
            chapter_index += 1
            document = _chapter_document(chapter_index, chapter.title, chapter.content)
            book.add_item(document)
            spine.append(document)
            volume_chapters.append(document)
        toc.append((volume_entry, tuple(volume_chapters)))

    book.toc = list(toc)
    book.spine = spine
    epub.write_epub(str(path), book)
