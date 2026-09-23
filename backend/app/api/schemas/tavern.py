"""Tavern material import schemas."""

from pydantic import BaseModel, Field


class TavernLorePreview(BaseModel):
    """One lore entry in an import preview."""

    name: str
    keywords: list[str] = Field(default_factory=list)
    is_constant: bool
    is_enabled: bool


class TavernBlockPreview(BaseModel):
    """One classified preset or card prompt."""

    block_id: str
    name: str
    content_preview: str
    bucket: str
    reason: str
    included: bool


class TavernPreviewResponse(BaseModel):
    """Preview of a character card, world book, or preset."""

    kind: str
    character_name: str = ""
    description_preview: str = ""
    discarded: list[str] = Field(default_factory=list)
    constant_count: int = 0
    keyword_count: int = 0
    lore_entries: list[TavernLorePreview] = Field(default_factory=list)
    preset_name: str = ""
    blocks: list[TavernBlockPreview] = Field(default_factory=list)


class TavernImportResponse(BaseModel):
    """Result of writing a tavern file."""

    kind: str
    character_id: str | None = None
    imported_entries: int = 0
    imported_rules: int = 0
    imported_skills: int = 0
