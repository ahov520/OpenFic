# -*- coding: utf-8 -*-
"""敏感词词库 API 数据模型。"""

from pydantic import BaseModel, Field


class SensitiveWordEntry(BaseModel):
    """单个敏感词条目（来源可选）。"""

    word: str = Field(min_length=1, max_length=50, description="敏感词")
    source: str = Field(default="", max_length=100, description="来源/备注")


class SensitiveWordsListResponse(BaseModel):
    """敏感词词表。"""

    words: list[SensitiveWordEntry]
    count: int
    stats: dict[str, int] | None = None


class SensitiveWordsUpdateRequest(BaseModel):
    """整表更新请求。"""

    words: list[SensitiveWordEntry] = Field(default_factory=list)


class SensitiveWordsImportRequest(BaseModel):
    """导入请求（TXT：每行一词可选「词|来源」；JSON：词条数组）。"""

    content: str = Field(min_length=1)
    format: str = Field(default="txt", pattern="^(txt|json)$")


class SensitiveWordsExportResponse(BaseModel):
    """导出结果。"""

    filename: str
    format: str
    content: str
