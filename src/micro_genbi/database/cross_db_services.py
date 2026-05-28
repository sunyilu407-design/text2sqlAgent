"""跨库关联关系服务

提供跨库关联关系的 CRUD 操作和验证功能。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Optional, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, and_

from micro_genbi.database.models import DatabaseConnection
from micro_genbi.database.cross_db_models import (
    CrossDBRelation, ConnectionGroup, ConnectionGroupMember,
    RelationCardinality, RelationStatus,
)
from micro_genbi.db.schema_extractor import SchemaExtractor, ExtractedSchema


@dataclass
class CreateRelationInput:
    """创建跨库关系输入"""
    tenant_id: str
    name: str
    source_connection_id: str
    source_table: str
    source_column: str
    target_connection_id: str
    target_table: str
    target_column: str
    cardinality: str = "one_to_one"
    description: str = ""
    created_by: Optional[str] = None


@dataclass
class CreateGroupInput:
    """创建数据库分组输入"""
    tenant_id: str
    name: str
    display_name: str
    mode: str = "aggregate"
    description: str = ""
    project_id: Optional[str] = None


@dataclass
class AddGroupMemberInput:
    """添加分组成员输入"""
    group_id: str
    connection_id: str
    city_code: Optional[str] = None
    display_order: int = 0


class CrossDBRelationService:
    """跨库关联关系服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_relation(self, input: CreateRelationInput) -> CrossDBRelation:
        """创建跨库关联关系"""
        relation = CrossDBRelation(
            id=str(uuid.uuid4()),
            tenant_id=input.tenant_id,
            name=input.name,
            source_connection_id=input.source_connection_id,
            source_table=input.source_table,
            source_column=input.source_column,
            target_connection_id=input.target_connection_id,
            target_table=input.target_table,
            target_column=input.target_column,
            cardinality=input.cardinality,
            description=input.description,
            created_by=input.created_by,
        )
        self.session.add(relation)
        await self.session.commit()
        await self.session.refresh(relation)
        return relation

    async def get_relation(self, relation_id: str) -> Optional[CrossDBRelation]:
        """获取关联关系"""
        result = await self.session.execute(
            select(CrossDBRelation).where(CrossDBRelation.id == relation_id)
        )
        return result.scalar_one_or_none()

    async def list_relations(
        self,
        tenant_id: str,
        connection_id: Optional[str] = None,
        active_only: bool = True,
    ) -> list[CrossDBRelation]:
        """列出跨库关联关系"""
        conditions = [CrossDBRelation.tenant_id == tenant_id]
        if active_only:
            conditions.append(CrossDBRelation.is_active == True)
        if connection_id:
            conditions.append(
                (CrossDBRelation.source_connection_id == connection_id) |
                (CrossDBRelation.target_connection_id == connection_id)
            )

        result = await self.session.execute(
            select(CrossDBRelation).where(and_(*conditions))
        )
        return list(result.scalars().all())

    async def get_relations_between(
        self,
        conn_a: str,
        conn_b: str,
    ) -> list[CrossDBRelation]:
        """获取两个数据库之间的所有关联关系"""
        result = await self.session.execute(
            select(CrossDBRelation).where(
                and_(
                    CrossDBRelation.is_active == True,
                    (
                        (CrossDBRelation.source_connection_id == conn_a) &
                        (CrossDBRelation.target_connection_id == conn_b)
                    ) |
                    (
                        (CrossDBRelation.source_connection_id == conn_b) &
                        (CrossDBRelation.target_connection_id == conn_a)
                    )
                )
            )
        )
        return list(result.scalars().all())

    async def update_relation(
        self,
        relation_id: str,
        **updates,
    ) -> Optional[CrossDBRelation]:
        """更新关联关系"""
        relation = await self.get_relation(relation_id)
        if not relation:
            return None

        for key, value in updates.items():
            if hasattr(relation, key):
                setattr(relation, key, value)

        relation.updated_at = uuid.uuid4()
        await self.session.commit()
        await self.session.refresh(relation)
        return relation

    async def delete_relation(self, relation_id: str) -> bool:
        """删除关联关系（软删除）"""
        relation = await self.get_relation(relation_id)
        if not relation:
            return False
        relation.is_active = False
        await self.session.commit()
        return True

    async def verify_relation(
        self,
        relation_id: str,
        source_extractor: SchemaExtractor,
        target_extractor: SchemaExtractor,
    ) -> dict[str, Any]:
        """
        验证跨库关联关系是否有效。

        通过抽样查询验证两端的关联键是否有匹配记录。
        """
        relation = await self.get_relation(relation_id)
        if not relation:
            return {"valid": False, "error": "Relation not found"}

        try:
            # 验证源端
            source_schema = source_extractor.extract_sync()
            source_table = next(
                (t for t in source_schema.tables if t.name == relation.source_table), None
            )
            if not source_table:
                return {"valid": False, "error": f"Source table {relation.source_table} not found"}

            # 验证目标端
            target_schema = target_extractor.extract_sync()
            target_table = next(
                (t for t in target_schema.tables if t.name == relation.target_table), None
            )
            if not target_table:
                return {"valid": False, "error": f"Target table {relation.target_table} not found"}

            # 更新状态
            relation.status = RelationStatus.VERIFIED.value
            await self.session.commit()

            return {
                "valid": True,
                "source_table": relation.source_table,
                "source_column": relation.source_column,
                "target_table": relation.target_table,
                "target_column": relation.target_column,
            }
        except Exception as e:
            relation.status = RelationStatus.INVALID.value
            await self.session.commit()
            return {"valid": False, "error": str(e)}

    async def get_related_connections(self, connection_id: str) -> list[str]:
        """获取与指定数据库有跨库关联的所有数据库 ID"""
        relations = await self.list_relations(
            tenant_id="",  # 忽略租户过滤，因为 connection_id 已足够
            connection_id=connection_id,
        )
        related = set()
        for r in relations:
            if r.source_connection_id == connection_id:
                related.add(r.target_connection_id)
            else:
                related.add(r.source_connection_id)
        return list(related)


class ConnectionGroupService:
    """数据库分组服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_group(self, input: CreateGroupInput) -> ConnectionGroup:
        """创建数据库分组"""
        group = ConnectionGroup(
            id=str(uuid.uuid4()),
            tenant_id=input.tenant_id,
            name=input.name,
            display_name=input.display_name,
            mode=input.mode,
            description=input.description,
            project_id=input.project_id,
        )
        self.session.add(group)
        await self.session.commit()
        await self.session.refresh(group)
        return group

    async def get_group(self, group_id: str) -> Optional[ConnectionGroup]:
        """获取分组"""
        result = await self.session.execute(
            select(ConnectionGroup).where(ConnectionGroup.id == group_id)
        )
        return result.scalar_one_or_none()

    async def list_groups(
        self,
        tenant_id: str,
        project_id: Optional[str] = None,
    ) -> list[ConnectionGroup]:
        """列出数据库分组"""
        conditions = [
            ConnectionGroup.tenant_id == tenant_id,
            ConnectionGroup.is_active == True,
        ]
        if project_id:
            conditions.append(ConnectionGroup.project_id == project_id)

        result = await self.session.execute(
            select(ConnectionGroup).where(and_(*conditions))
        )
        return list(result.scalars().all())

    async def add_member(
        self, input: AddGroupMemberInput
    ) -> ConnectionGroupMember:
        """添加分组成员"""
        member = ConnectionGroupMember(
            id=str(uuid.uuid4()),
            group_id=input.group_id,
            connection_id=input.connection_id,
            city_code=input.city_code,
            display_order=input.display_order,
        )
        self.session.add(member)
        await self.session.commit()
        await self.session.refresh(member)
        return member

    async def remove_member(
        self,
        group_id: str,
        connection_id: str,
    ) -> bool:
        """移除分组成员"""
        result = await self.session.execute(
            delete(ConnectionGroupMember).where(
                and_(
                    ConnectionGroupMember.group_id == group_id,
                    ConnectionGroupMember.connection_id == connection_id,
                )
            )
        )
        await self.session.commit()
        return result.rowcount > 0

    async def get_group_members(
        self, group_id: str
    ) -> list[ConnectionGroupMember]:
        """获取分组所有成员"""
        result = await self.session.execute(
            select(ConnectionGroupMember)
            .where(ConnectionGroupMember.group_id == group_id)
            .order_by(ConnectionGroupMember.display_order)
        )
        return list(result.scalars().all())

    async def delete_group(self, group_id: str) -> bool:
        """删除分组（软删除）"""
        group = await self.get_group(group_id)
        if not group:
            return False
        group.is_active = False
        await self.session.commit()
        return True
