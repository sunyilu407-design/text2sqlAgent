"""Schema 抽取和跨库关联 API 路由

提供：
- 数据库 Schema 抽取（从真实 DB 发现表结构、主键、外键）
- 跨库关联关系 CRUD
- 数据库分组管理（同构多库聚合）
"""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import asyncio
import yaml

from micro_genbi import get_logger
from micro_genbi.database import (
    DatabaseConnectionService, CreateDatabaseConnectionInput,
)
from micro_genbi.database.cross_db_models import (
    CrossDBRelation, ConnectionGroup,
    RelationCardinality,
)
from micro_genbi.database.cross_db_services import (
    CrossDBRelationService, ConnectionGroupService,
    CreateRelationInput, CreateGroupInput, AddGroupMemberInput,
)
from micro_genbi.api.dependencies import get_db_session, get_current_user
from micro_genbi.db.schema_extractor import SchemaExtractor
from micro_genbi.db.engine import get_engine

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/schema", tags=["Schema 管理"])


# =============================================================================
# 请求/响应模型
# =============================================================================

class SchemaExtractResponse(BaseModel):
    database_name: str
    database_type: str
    tables: list[dict]
    relationships: list[dict]


class TableColumnModel(BaseModel):
    name: str
    type: str
    nullable: bool = True
    is_primary_key: bool = False
    is_foreign_key: bool = False
    default: Optional[str] = None
    description: str = ""


class TableSchemaResponse(BaseModel):
    name: str
    schema: str = ""
    columns: list[TableColumnModel]
    primary_keys: list[str]
    foreign_keys: list[dict]
    row_count: Optional[int] = None


class RelationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    source_connection_id: str
    source_table: str
    source_column: str
    target_connection_id: str
    target_table: str
    target_column: str
    cardinality: str = "one_to_one"
    description: str = ""


class RelationResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    source_connection_id: str
    source_table: str
    source_column: str
    target_connection_id: str
    target_table: str
    target_column: str
    cardinality: str
    description: str
    status: str
    is_active: bool
    sample_count: Optional[int] = None
    created_at: str

    class Config:
        from_attributes = True


class GroupCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    display_name: str = Field(..., min_length=1, max_length=200)
    mode: str = "aggregate"
    description: str = ""
    project_id: Optional[str] = None


class GroupMemberAdd(BaseModel):
    connection_id: str
    city_code: Optional[str] = None
    display_order: int = 0


class GroupResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    display_name: str
    mode: str
    description: str
    member_count: int = 0
    is_default: bool
    is_active: bool
    created_at: str

    class Config:
        from_attributes = True


class ERDiagramResponse(BaseModel):
    """前端渲染 ER 图所需的结构化数据"""
    nodes: list[dict]
    edges: list[dict]


# =============================================================================
# Schema 抽取
# =============================================================================

@router.get(
    "/extract/{connection_id}",
    response_model=SchemaExtractResponse,
    summary="抽取数据库 Schema",
)
async def extract_schema(
    connection_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    从真实数据库中抽取完整的 Schema 信息。

    返回：
    - 所有表及其列信息
    - 主键和外键关系
    - 表行数统计
    """
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="未登录")

    async for session in get_db_session():
        db_service = DatabaseConnectionService(session)
        conn = await db_service.get_by_id(connection_id)

        if not conn:
            raise HTTPException(status_code=404, detail="数据源不存在")
        if conn.tenant_id != tenant_id:
            raise HTTPException(status_code=403, detail="无权访问该数据源")

        try:
            engine = await get_engine(connection_id)
            extractor = SchemaExtractor(engine)
            schema = extractor.extract_sync()
            return SchemaExtractResponse(
                database_name=schema.database_name,
                database_type=schema.database_type,
                tables=[t.to_dict() for t in schema.tables],
                relationships=[r.to_dict() for r in schema.relationships],
            )
        except Exception as e:
            logger.error(f"Schema extraction failed for {connection_id}: {e}")
            raise HTTPException(status_code=500, detail=f"Schema 抽取失败: {str(e)}")


@router.get(
    "/extract/{connection_id}/table/{table_name}",
    response_model=TableSchemaResponse,
    summary="抽取单表结构",
)
async def extract_table_schema(
    connection_id: str,
    table_name: str,
    current_user: dict = Depends(get_current_user),
):
    """抽取单个表的详细结构信息"""
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="未登录")

    async for session in get_db_session():
        db_service = DatabaseConnectionService(session)
        conn = await db_service.get_by_id(connection_id)

        if not conn or conn.tenant_id != tenant_id:
            raise HTTPException(status_code=404, detail="数据源不存在")

        try:
            engine = await get_engine(connection_id)
            extractor = SchemaExtractor(engine)
            schema = extractor.extract_sync()

            table = next((t for t in schema.tables if t.name == table_name), None)
            if not table:
                raise HTTPException(status_code=404, detail=f"表 {table_name} 不存在")

            return TableSchemaResponse(
                name=table.name,
                schema=table.schema,
                columns=[TableColumnModel(**c.to_dict()) for c in table.columns],
                primary_keys=table.primary_keys,
                foreign_keys=[f.to_dict() for f in table.foreign_keys],
                row_count=table.row_count,
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Table extraction failed: {e}")
            raise HTTPException(status_code=500, detail=f"表结构抽取失败: {str(e)}")


@router.get(
    "/extract/{connection_id}/yaml",
    summary="导出 YAML 配置",
)
async def export_yaml(
    connection_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    从真实数据库抽取 Schema 并生成 YAML 配置文件。

    用户可以在此基础上补充 description 和 enum_values。
    """
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="未登录")

    async for session in get_db_session():
        db_service = DatabaseConnectionService(session)
        conn = await db_service.get_by_id(connection_id)

        if not conn or conn.tenant_id != tenant_id:
            raise HTTPException(status_code=404, detail="数据源不存在")

        try:
            engine = await get_engine(connection_id)
            extractor = SchemaExtractor(engine)
            schema = extractor.extract_sync()
            yaml_content = extractor.generate_yaml_config(schema)

            return {
                "connection_id": connection_id,
                "connection_name": conn.name,
                "yaml_content": yaml_content,
            }
        except Exception as e:
            logger.error(f"YAML export failed: {e}")
            raise HTTPException(status_code=500, detail=f"YAML 导出失败: {str(e)}")


# =============================================================================
# ER 图数据
# =============================================================================

@router.get(
    "/er/{connection_id}",
    response_model=ERDiagramResponse,
    summary="获取 ER 图数据",
)
async def get_er_diagram(
    connection_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    获取前端渲染 ER 图所需的结构化数据。

    返回 nodes（表节点）和 edges（关系边），前端可用 D3.js / Mermaid / G6 渲染。
    """
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="未登录")

    async for session in get_db_session():
        db_service = DatabaseConnectionService(session)
        conn = await db_service.get_by_id(connection_id)

        if not conn or conn.tenant_id != tenant_id:
            raise HTTPException(status_code=404, detail="数据源不存在")

        try:
            engine = await get_engine(connection_id)
            extractor = SchemaExtractor(engine)
            schema = extractor.extract_sync()

            # 构建节点
            nodes = []
            for table in schema.tables:
                pk_cols = [c for c in table.columns if c.is_primary_key]
                fk_cols = [c for c in table.columns if c.is_foreign_key]
                nodes.append({
                    "id": table.name,
                    "label": table.name,
                    "type": "table",
                    "pk": [c.name for c in pk_cols],
                    "fk": [c.name for c in fk_cols],
                    "columns": len(table.columns),
                    "row_count": table.row_count,
                })

            # 构建边（库内 FK 关系）
            edges = []
            for table in schema.tables:
                for fk in table.foreign_keys:
                    edges.append({
                        "id": f"{table.name}.{fk.constrained_columns[0]}_to_{fk.referred_table}",
                        "source": table.name,
                        "source_col": fk.constrained_columns[0],
                        "target": fk.referred_table,
                        "target_col": fk.referred_columns[0],
                        "cardinality": fk.name or "FK",
                        "type": "has_fk",
                    })

            return ERDiagramResponse(nodes=nodes, edges=edges)
        except Exception as e:
            logger.error(f"ER diagram generation failed: {e}")
            raise HTTPException(status_code=500, detail=f"ER 图生成失败: {str(e)}")


# =============================================================================
# 跨库关联关系管理
# =============================================================================

@router.post(
    "/relations",
    response_model=RelationResponse,
    summary="创建跨库关联关系",
)
async def create_relation(
    relation: RelationCreate,
    current_user: dict = Depends(get_current_user),
):
    """
    手动配置两个数据库之间的跨库关联关系。

    必须配置后才能进行跨库 JOIN 查询。
    """
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="未登录")

    # 验证两个连接都存在且属于同一租户
    async for session in get_db_session():
        db_service = DatabaseConnectionService(session)
        src_conn = await db_service.get_by_id(relation.source_connection_id)
        tgt_conn = await db_service.get_by_id(relation.target_connection_id)

        if not src_conn or src_conn.tenant_id != tenant_id:
            raise HTTPException(status_code=404, detail="源数据源不存在")
        if not tgt_conn or tgt_conn.tenant_id != tenant_id:
            raise HTTPException(status_code=404, detail="目标数据源不存在")
        if src_conn.id == tgt_conn.id:
            raise HTTPException(status_code=400, detail="不能创建同一数据库内的跨库关系")

        rel_service = CrossDBRelationService(session)
        result = await rel_service.create_relation(CreateRelationInput(
            tenant_id=tenant_id,
            name=relation.name,
            source_connection_id=relation.source_connection_id,
            source_table=relation.source_table,
            source_column=relation.source_column,
            target_connection_id=relation.target_connection_id,
            target_table=relation.target_table,
            target_column=relation.target_column,
            cardinality=relation.cardinality,
            description=relation.description,
            created_by=current_user.get("user_id"),
        ))
        return RelationResponse(
            id=result.id,
            tenant_id=result.tenant_id,
            name=result.name,
            source_connection_id=result.source_connection_id,
            source_table=result.source_table,
            source_column=result.source_column,
            target_connection_id=result.target_connection_id,
            target_table=result.target_table,
            target_column=result.target_column,
            cardinality=result.cardinality,
            description=result.description,
            status=result.status,
            is_active=result.is_active,
            sample_count=result.sample_count,
            created_at=result.created_at.isoformat() if result.created_at else "",
        )


@router.get(
    "/relations",
    response_model=list[RelationResponse],
    summary="列出跨库关联关系",
)
async def list_relations(
    connection_id: Optional[str] = Query(None, description="筛选特定数据源的关联关系"),
    current_user: dict = Depends(get_current_user),
):
    """列出当前租户的所有跨库关联关系"""
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="未登录")

    async for session in get_db_session():
        rel_service = CrossDBRelationService(session)
        relations = await rel_service.list_relations(tenant_id, connection_id)
        return [
            RelationResponse(
                id=r.id,
                tenant_id=r.tenant_id,
                name=r.name,
                source_connection_id=r.source_connection_id,
                source_table=r.source_table,
                source_column=r.source_column,
                target_connection_id=r.target_connection_id,
                target_table=r.target_table,
                target_column=r.target_column,
                cardinality=r.cardinality,
                description=r.description,
                status=r.status,
                is_active=r.is_active,
                sample_count=r.sample_count,
                created_at=r.created_at.isoformat() if r.created_at else "",
            )
            for r in relations
        ]


@router.delete(
    "/relations/{relation_id}",
    summary="删除跨库关联关系",
)
async def delete_relation(
    relation_id: str,
    current_user: dict = Depends(get_current_user),
):
    """删除跨库关联关系（软删除）"""
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="未登录")

    async for session in get_db_session():
        rel_service = CrossDBRelationService(session)
        relation = await rel_service.get_relation(relation_id)
        if not relation or relation.tenant_id != tenant_id:
            raise HTTPException(status_code=404, detail="关联关系不存在")
        await rel_service.delete_relation(relation_id)
        return {"message": "关联关系已删除"}


# =============================================================================
# 数据库分组管理（同构多库聚合）
# =============================================================================

@router.post(
    "/groups",
    response_model=GroupResponse,
    summary="创建数据库分组",
)
async def create_group(
    group: GroupCreate,
    current_user: dict = Depends(get_current_user),
):
    """创建数据库分组，用于同构多库聚合场景"""
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="未登录")

    async for session in get_db_session():
        grp_service = ConnectionGroupService(session)
        result = await grp_service.create_group(CreateGroupInput(
            tenant_id=tenant_id,
            name=group.name,
            display_name=group.display_name,
            mode=group.mode,
            description=group.description,
            project_id=group.project_id,
        ))
        return GroupResponse(
            id=result.id,
            tenant_id=result.tenant_id,
            name=result.name,
            display_name=result.display_name,
            mode=result.mode,
            description=result.description or "",
            member_count=0,
            is_default=result.is_default,
            is_active=result.is_active,
            created_at=result.created_at.isoformat() if result.created_at else "",
        )


@router.get(
    "/groups",
    response_model=list[GroupResponse],
    summary="列出数据库分组",
)
async def list_groups(
    project_id: Optional[str] = Query(None, description="筛选特定项目"),
    current_user: dict = Depends(get_current_user),
):
    """列出当前租户的所有数据库分组"""
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="未登录")

    async for session in get_db_session():
        grp_service = ConnectionGroupService(session)
        groups = await grp_service.list_groups(tenant_id, project_id)
        results = []
        for g in groups:
            members = await grp_service.get_group_members(g.id)
            results.append(GroupResponse(
                id=g.id,
                tenant_id=g.tenant_id,
                name=g.name,
                display_name=g.display_name,
                mode=g.mode,
                description=g.description or "",
                member_count=len(members),
                is_default=g.is_default,
                is_active=g.is_active,
                created_at=g.created_at.isoformat() if g.created_at else "",
            ))
        return results


@router.post(
    "/groups/{group_id}/members",
    summary="添加分组成员",
)
async def add_group_member(
    group_id: str,
    member: GroupMemberAdd,
    current_user: dict = Depends(get_current_user),
):
    """向分组添加数据库成员"""
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="未登录")

    async for session in get_db_session():
        grp_service = ConnectionGroupService(session)
        db_service = DatabaseConnectionService(session)

        group = await grp_service.get_group(group_id)
        if not group or group.tenant_id != tenant_id:
            raise HTTPException(status_code=404, detail="分组不存在")

        conn = await db_service.get_by_id(member.connection_id)
        if not conn or conn.tenant_id != tenant_id:
            raise HTTPException(status_code=404, detail="数据源不存在")

        result = await grp_service.add_member(AddGroupMemberInput(
            group_id=group_id,
            connection_id=member.connection_id,
            city_code=member.city_code,
            display_order=member.display_order,
        ))
        return {
            "id": result.id,
            "group_id": result.group_id,
            "connection_id": result.connection_id,
            "city_code": result.city_code,
            "display_order": result.display_order,
        }


@router.get(
    "/groups/{group_id}/members",
    summary="列出分组成员",
)
async def list_group_members(
    group_id: str,
    current_user: dict = Depends(get_current_user),
):
    """列出分组中的所有数据库成员"""
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="未登录")

    async for session in get_db_session():
        grp_service = ConnectionGroupService(session)
        db_service = DatabaseConnectionService(session)

        group = await grp_service.get_group(group_id)
        if not group or group.tenant_id != tenant_id:
            raise HTTPException(status_code=404, detail="分组不存在")

        members = await grp_service.get_group_members(group_id)
        results = []
        for m in members:
            conn = await db_service.get_by_id(m.connection_id)
            if conn:
                results.append({
                    "id": m.id,
                    "connection_id": m.connection_id,
                    "connection_name": conn.name,
                    "db_type": conn.db_type,
                    "host": f"{conn.host}:{conn.port}" if conn.host else None,
                    "city_code": m.city_code,
                    "display_order": m.display_order,
                })
        return results


@router.delete(
    "/groups/{group_id}/members/{connection_id}",
    summary="移除分组成员",
)
async def remove_group_member(
    group_id: str,
    connection_id: str,
    current_user: dict = Depends(get_current_user),
):
    """从分组移除数据库成员"""
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="未登录")

    async for session in get_db_session():
        grp_service = ConnectionGroupService(session)
        group = await grp_service.get_group(group_id)
        if not group or group.tenant_id != tenant_id:
            raise HTTPException(status_code=404, detail="分组不存在")

        success = await grp_service.remove_member(group_id, connection_id)
        if not success:
            raise HTTPException(status_code=404, detail="成员不在该分组中")
        return {"message": "成员已移除"}


@router.delete(
    "/groups/{group_id}",
    summary="删除数据库分组",
)
async def delete_group(
    group_id: str,
    current_user: dict = Depends(get_current_user),
):
    """删除数据库分组（软删除）"""
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="未登录")

    async for session in get_db_session():
        grp_service = ConnectionGroupService(session)
        group = await grp_service.get_group(group_id)
        if not group or group.tenant_id != tenant_id:
            raise HTTPException(status_code=404, detail="分组不存在")

        await grp_service.delete_group(group_id)
        return {"message": "分组已删除"}
