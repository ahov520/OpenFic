# -*- coding: utf-8 -*-
"""DOCX/EPUB 导入提取测试：提取文本与 .txt 导入等价。"""

import io

import pytest
from docx import Document
from ebooklib import epub

from app.core.project_import import (
    SUPPORTED_IMPORT_SUFFIXES,
    parse_project_import,
)

# 章节正文足够长：自动分章要求标题间隔 >500 字符（规避目录误判的设计）
_CHAPTER_ONE_BODY = "他沿着河岸一直走。\n" * 65
_CHAPTER_TWO_BODY = "她把信折好收进口袋。\n" * 65
SAMPLE_TEXT = (
    f"第一章 风起\n{_CHAPTER_ONE_BODY}\n第二章 云散\n{_CHAPTER_TWO_BODY}"
)


def _build_docx() -> bytes:
    document = Document()
    for line in SAMPLE_TEXT.split("\n"):
        document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _build_epub_with_manifest_reversed() -> bytes:
    """manifest 声明顺序为 ch2,ch1，而 spine 阅读顺序为 ch1,ch2 的样例。"""
    book = epub.EpubBook()
    book.set_title("老书")
    book.set_language("zh")
    book.add_author("作者")
    book.add_item(epub.EpubNav())
    book.add_item(epub.EpubNcx())

    second = epub.EpubHtml(title="第二章 云散", file_name="chapter_0002.xhtml", lang="zh")
    second.content = "<html><body><h2>第二章 云散</h2><p>第二章正文</p></body></html>"
    first = epub.EpubHtml(title="第一章 风起", file_name="chapter_0001.xhtml", lang="zh")
    first.content = "<html><body><h2>第一章 风起</h2><p>第一章正文</p></body></html>"
    # manifest 顺序：先 ch2 后 ch1
    book.add_item(second)
    book.add_item(first)
    # spine 阅读顺序：ch1 → ch2
    book.spine = ["nav", first, second]
    buffer = io.BytesIO()
    epub.write_epub(buffer, book)
    return buffer.getvalue()


def _build_epub() -> bytes:
    book = epub.EpubBook()
    book.set_title("老书")
    book.set_language("zh")
    book.add_author("作者")
    book.add_item(epub.EpubNav())
    book.add_item(epub.EpubNcx())

    first = epub.EpubHtml(title="第一章 风起", file_name="chapter_0001.xhtml", lang="zh")
    first.content = (
        "<html><body><h2>第一章 风起</h2>"
        f"<p>{_CHAPTER_ONE_BODY.strip().replace(chr(10), '</p><p>')}</p></body></html>"
    )
    second = epub.EpubHtml(title="第二章 云散", file_name="chapter_0002.xhtml", lang="zh")
    second.content = (
        "<html><body><h2>第二章 云散</h2>"
        f"<p>{_CHAPTER_TWO_BODY.strip().replace(chr(10), '</p><p>')}</p></body></html>"
    )
    book.add_item(first)
    book.add_item(second)
    book.spine = ["nav", first, second]
    buffer = io.BytesIO()
    epub.write_epub(buffer, book)
    return buffer.getvalue()


def _normalized_chapters(parse_result) -> list[tuple[str, str]]:
    """章节标题 + 空白归一化后的正文（提取不保留精确空行布局）。"""
    normalized: list[tuple[str, str]] = []
    for volume in parse_result.volumes:
        for chapter in volume.chapters:
            compact_content = "\n".join(
                line for line in chapter.content.splitlines() if line.strip()
            )
            normalized.append((chapter.title, compact_content))
    return normalized


def test_docx_epub_suffixes_are_supported() -> None:
    assert {".docx", ".epub"} <= SUPPORTED_IMPORT_SUFFIXES


def test_docx_and_txt_import_are_equivalent() -> None:
    txt_result = parse_project_import("书.txt", SAMPLE_TEXT.encode("utf-8"))
    docx_result = parse_project_import("书.docx", _build_docx())

    assert txt_result.chapter_count == 2
    assert docx_result.chapter_count == txt_result.chapter_count
    assert _normalized_chapters(docx_result) == _normalized_chapters(txt_result)


def test_epub_and_txt_import_are_equivalent() -> None:
    txt_result = parse_project_import("书.txt", SAMPLE_TEXT.encode("utf-8"))
    epub_result = parse_project_import("书.epub", _build_epub())

    assert epub_result.chapter_count == txt_result.chapter_count
    assert _normalized_chapters(epub_result) == _normalized_chapters(txt_result)


def test_docx_manual_split_preserves_all_text() -> None:
    """手动分割按字符块切：提取文本的空白布局差异会移动块边界，
    但总字数与正文内容必须与 .txt 完全一致（不丢文本）。"""
    txt_result = parse_project_import(
        "书.txt",
        SAMPLE_TEXT.encode("utf-8"),
        split_mode="manual",
        chunk_size=200,
    )
    docx_result = parse_project_import(
        "书.docx",
        _build_docx(),
        split_mode="manual",
        chunk_size=200,
    )

    assert docx_result.chapter_count > 1
    assert docx_result.total_word_count == txt_result.total_word_count

    def squashed(result) -> str:
        # 去掉全部空白字符后比较：块边界与空白布局差异不影响文本内容
        return "".join(
            "".join(chapter[1].split()) for chapter in _normalized_chapters(result)
        )

    assert squashed(docx_result) == squashed(txt_result)


def test_corrupted_epub_raises_value_error() -> None:
    with pytest.raises(ValueError, match="EPUB"):
        parse_project_import("书.epub", b"not-an-epub")


def test_epub_extraction_follows_spine_order() -> None:
    """EPUB 按 spine 阅读顺序提取：manifest 顺序颠倒不导致章节乱序。"""
    from app.core.doc_extract import extract_text_from_epub

    text = extract_text_from_epub(_build_epub_with_manifest_reversed())

    assert "第一章 风起" in text
    assert "第二章 云散" in text
    assert "第一章正文" in text
    assert "第二章正文" in text
    assert text.index("第一章 风起") < text.index("第二章 云散")


def test_corrupted_docx_raises_value_error() -> None:
    with pytest.raises(ValueError, match="DOCX"):
        parse_project_import("书.docx", b"not-a-docx")
