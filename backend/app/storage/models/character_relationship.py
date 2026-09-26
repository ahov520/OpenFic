# -*- coding: utf-8 -*-
"""CharacterRelationship 数据模型。角色与角色之间的一条关系连线。"""

from datetime import UTC, datetime

from sqlalchemy import Column, String, Text, UniqueConstraint, text
from sqlmodel import Field, SQLModel

from app.core.ids import generate_id


class CharacterRelationship(SQLModel, table=True):
    """
    项目内两名角色之间的关系。

    关系无方向，存储时把字典序较小的角色 ID 放在 from_character_id，
    同一对角色只允许一条连线。

    Attributes:
        id: 关系唯一标识符（nanoid）。
        project_id: 所属项目 ID。
        from_character_id: 角色 ID（与 to 合并为无序对，字典序小者在前）。
        to_character_id: 另一角色 ID。
        relation_type: 关系类型，如 亲人、敌对、师徒。
        description: 关系说明。
        created_at: 创建时间。
        updated_at: 上次修改时间。
    """

    __tablename__ = "character_relationships"
    __table_args__ = (
        UniqueConstraint(
            "from_character_id",
            "to_character_id",
            name="uq_character_relationships_pair",
        ),
    )

    id: str = Field(default_factory=generate_id, primary_key=True)
    project_id: str = Field(index=True, foreign_key="projects.id")
    from_character_id: str = Field(index=True, foreign_key="characters.id")
    to_character_id: str = Field(index=True, foreign_key="characters.id")
    relation_type: str = Field(
        max_length=80,
        sa_column=Column(String(80), nullable=False, server_default=text("''")),
    )
    description: str = Field(
        default="",
        sa_column=Column(Text, nullable=False, server_default=text("''")),
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
