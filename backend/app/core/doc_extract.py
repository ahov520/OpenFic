# -*- coding: utf-8 -*-
"""DOCX/EPUB 老书迁移导入的文本提取。

仅依赖纯 Python 库（docx2txt / ebooklib），不依赖任何系统工具：
- DOCX 走 docx2txt 直读；
- EPUB 用 ebooklib 直读各 XHTML 文档并剥标签提纯文本。

与 agent_runtime/attachments.py 的 langchain 加载包装相互独立：
导入链路不引用 agent_runtime，避免形成 core → agent_runtime 的反向依赖。
"""

from __future__ import annotations

import io
from html.parser import HTMLParser

# 生成导航页的常见文件名片段（其内容是目录，不是正文）
_NAV_DOCUMENT_HINTS = ("nav", "toc")


class _XHTMLTextExtractor(HTMLParser):
    """把 XHTML 文档剥成纯文本：块级标签转换行，实体自动反转义。"""

    _BLOCK_TAGS = frozenset(
        {
            "p",
            "div",
            "br",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "li",
            "tr",
            "section",
            "article",
            "blockquote",
        }
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._pieces: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001
        if tag in self._BLOCK_TAGS:
            self._pieces.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._BLOCK_TAGS:
            self._pieces.append("\n")

    def handle_data(self, data: str) -> None:
        if data:
            self._pieces.append(data)

    def get_text(self) -> str:
        raw = "".join(self._pieces)
        lines = [line.strip() for line in raw.splitlines()]
        collapsed: list[str] = []
        blank_pending = False
        for line in lines:
            if line:
                collapsed.append(line)
                blank_pending = False
            elif collapsed and not blank_pending:
                collapsed.append("")
                blank_pending = True
        return "\n".join(collapsed).strip()


def extract_text_from_docx(content: bytes) -> str:
    """提取 DOCX 全文纯文本。"""
    import docx2txt

    try:
        text = docx2txt.process(io.BytesIO(content))
    except Exception as exc:
        raise ValueError("DOCX 文件无法读取，请确认文件没有损坏或加密") from exc
    return (text or "").strip()


def extract_text_from_epub(content: bytes) -> str:
    """提取 EPUB 各正文文档的纯文本（跳过导航页）。

    按 spine（阅读顺序）解析：EPUB 规范允许 manifest 声明顺序与
    spine 阅读顺序不一致，仅按 manifest 遍历会导致章节静默乱序。
    不在 spine 中的正文文档（如有）追加在末尾兜底。
    """
    from ebooklib import ITEM_DOCUMENT, epub

    try:
        book = epub.read_epub(io.BytesIO(content))
    except Exception as exc:
        raise ValueError("EPUB 文件无法读取，请确认文件没有损坏或加密") from exc

    def document_text(item) -> str | None:  # noqa: ANN001
        file_name = (item.file_name or "").lower()
        if any(hint in file_name for hint in _NAV_DOCUMENT_HINTS):
            return None
        html = item.get_content().decode("utf-8", errors="replace")
        extractor = _XHTMLTextExtractor()
        try:
            extractor.feed(html)
            extractor.close()
        except Exception as exc:
            raise ValueError("EPUB 文件无法读取，请确认文件没有损坏或加密") from exc
        return extractor.get_text() or None

    parts: list[str] = []
    seen_ids: set[str] = set()

    # spine 条目为 (idref, linear) 元组（兼容个别生成器写出的裸 idref 字符串）
    for spine_entry in book.spine:
        idref = spine_entry[0] if isinstance(spine_entry, (tuple, list)) else spine_entry
        item = book.get_item_with_id(idref)
        if item is None or item.get_type() != ITEM_DOCUMENT:
            continue
        seen_ids.add(item.id)
        text = document_text(item)
        if text:
            parts.append(text)

    # 兜底：不在 spine 里的正文文档（如 cover 页之外的散落文档）追加在末尾
    for item in book.get_items_of_type(ITEM_DOCUMENT):
        if item.id in seen_ids:
            continue
        text = document_text(item)
        if text:
            parts.append(text)
    return "\n\n".join(parts).strip()
