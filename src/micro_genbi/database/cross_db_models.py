"""跨库关联关系模型

定义跨数据库的关联关系，支持用户手动配置。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import Column, String, Text, Boolean, Integer, DateTime, ForeignKey, JSON, UniqueConstraint, Index
from sqlalchemy.orm import relationship

from micro_genbi.database.models import Base


class RelationCardinality(str, Enum):
    """关系基数"""
    ONE_TO_ONE = "one_to_one"
    ONE_TO_MANY = "one_to_many"
    MANY_TO_ONE = "many_to_one"
    MANY_TO_MANY = "many_to_many"


class RelationStatus(str, Enum):
    """关系状态"""
    PENDING = "pending"
    VERIFIED = "verified"
    INVALID = "invalid"


class CrossDBRelation(Base):
    """
    跨库关联关系配置。

    记录两个不同数据库之间表与表的关联方式。
    例如：订单库 orders 表的 order_id 关联到财务库 payments 表的 order_id。
    """
    __tablename__ = "cross_db_relations"

    id = Column(String(36), primary_key=True)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False)

    # 关系名称（业务意义）
    name = Column(String(200), nullable=False, comment="关系名称，如：订单-支付关联")

    # 源端（发起方）
    source_connection_id = Column(String(36), ForeignKey("database_connections.id"), nullable=False)
    source_table = Column(String(255), nullable=False, comment="源表名")
    source_column = Column(String(255), nullable=False, comment="源列名（关联键）")

    # 目标端（被引用方）
    target_connection_id = Column(String(36), ForeignKey("database_connections.id"), nullable=False)
    target_table = Column(String(255), nullable=False, comment="目标表名")
    target_column = Column(String(255), nullable=False, comment="目标列名（关联键）")

    # 关系属性
    cardinality = Column(String(20), default=RelationCardinality.ONE_TO_ONE.value)
    description = Column(Text, comment="关系描述，说明业务含义")
    status = Column(String(20), default=RelationStatus.PENDING.value)
    is_active = Column(Boolean, default=True)

    # 验证信息
    sample_count = Column(Integer, comment="抽样验证的匹配记录数")

    # 元数据
    created_by = Column(String(36))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关系（通过 connection_id 关联）
    source_connection = relationship(
        "DatabaseConnection",
        foreign_keys=[source_connection_id],
        backref="outgoing_relations",
    )
    target_connection = relationship(
        "DatabaseConnection",
        foreign_keys=[target_connection_id],
        backref="incoming_relations",
    )

    __table_args__ = (
        UniqueConstraint(
            "source_connection_id", "source_table", "source_column",
            "target_connection_id", "target_table", "target_column",
            name="uq_cross_db_relation",
        ),
        Index("idx_relation_tenant", "tenant_id"),
        Index("idx_relation_source", "source_connection_id", "source_table"),
        Index("idx_relation_target", "target_connection_id", "target_table"),
    )

    def __repr__(self):
        return (
            f"<CrossDBRelation {self.source_connection_id}.{self.source_table}."
            f"{self.source_column} → {self.target_connection_id}."
            f"{self.target_table}.{self.target_column}>"
        )


class DatabaseMode(str, Enum):
    """数据库架构模式"""
    SINGLE = "single"           # 单库模式
    AGGREGATE = "aggregate"     # 同构多库聚合（大屏展示）
    FEDERATED = "federated"     # 异构多库联邦（跨库 JOIN）


class ConnectionGroup(Base):
    """
    数据库分组（用于同构多库聚合）。

    例如：将杭州、宁波、温州的数据库分到一个组 province_cities。
    """
    __tablename__ = "connection_groups"

    id = Column(String(36), primary_key=True)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True)

    name = Column(String(100), nullable=False, comment="分组名称，如：省库同构组")
    display_name = Column(String(200), nullable=False, comment="中文显示名，如：浙江省各地市子系统")
    mode = Column(String(20), default=DatabaseMode.AGGREGATE.value)
    description = Column(Text)

    is_default = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关系
    tenant = relationship("Tenant", backref="connection_groups")
    project = relationship("Project", backref="connection_groups")

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_connection_group"),
        Index("idx_group_tenant", "tenant_id"),
    )


class ConnectionGroupMember(Base):
    """数据库分组中的成员"""
    __tablename__ = "connection_group_members"

    id = Column(String(36), primary_key=True)
    group_id = Column(String(36), ForeignKey("connection_groups.id"), nullable=False)
    connection_id = Column(String(36), ForeignKey("database_connections.id"), nullable=False)

    # 同构组专用字段
    city_code = Column(String(50), comment="城市/子系统编码，用于结果归并标识")
    display_order = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)

    # 关系
    group = relationship("ConnectionGroup", backref="members")
    connection = relationship("DatabaseConnection", backref="group_memberships")

    __table_args__ = (
        UniqueConstraint("group_id", "connection_id", name="uq_group_member"),
        Index("idx_group_member_group", "group_id"),
        Index("idx_group_member_conn", "connection_id"),
    )
