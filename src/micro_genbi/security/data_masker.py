"""敏感数据脱敏器

对查询结果中的敏感数据进行脱敏处理。
"""

from __future__ import annotations

import re
from typing import Any, Optional, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from micro_genbi.models import ColumnInfo


class DataMasker:
    """
    敏感数据脱敏器

    对查询结果中的敏感数据进行脱敏处理。
    """

    # 敏感字段模式
    SENSITIVE_PATTERNS: list[tuple[str, Any]] = [
        # 证件号
        (r'\b\d{15,18}\b', '********'),
        (r'\b\d{4}-\d{4,8}\b', '****-****'),
        # 手机号
        (r'\b1[3-9]\d{9}\b', lambda m: m.group()[:3] + '****' + m.group()[-4:]),
        # 邮箱
        (r'\b[\w.-]+@[\w.-]+\.\w+\b', lambda m: m.group()[0] + '***@***.' + m.group().split('.')[-1]),
        # 密码相关
        (r'(?i)(password|passwd|pwd)\s*[=:]\s*\S+', lambda m: m.group().split('=')[0] + '= ***'),
    ]

    # 油库专用敏感字段
    OIL_DEPOT_SENSITIVE_FIELDS: Set[str] = {
        # 库存数据
        "tank_level", "tank_levels", "inventory_amount", "stock_quantity",
        "stock_amount", "reserved_quantity", "available_quantity",
        # 安全数据
        "safety_pressure", "alarm_threshold", "safety_threshold",
        "max_pressure", "min_pressure", "pressure_limit",
        # 财务数据
        "cost_price", "purchase_price", "selling_price",
        "profit_margin", "unit_cost", "total_cost",
        # 凭证密码
        "password", "passwd", "pwd", "secret",
        "api_key", "api_key", "secret_key", "token", "credential",
        # 运维数据
        "admin_password", "root_password", "encrypt_key",
    }

    def __init__(self, enable_oil_depot: bool = True):
        self.enable_oil_depot = enable_oil_depot

    def mask_result(
        self,
        result: list[dict[str, Any]],
        schema: Optional[dict[str, Any]] = None,
        user_role: str = "user",
    ) -> list[dict[str, Any]]:
        """
        对查询结果进行脱敏

        Args:
            result: 查询结果列表
            schema: Schema 元数据
            user_role: 用户角色

        Returns:
            脱敏后的结果
        """
        if not result:
            return result

        # 确定需要脱敏的字段
        sensitive_fields = self._get_sensitive_fields(result[0], schema, user_role)

        # 脱敏每一行
        masked = []
        for row in result:
            masked_row = {}
            for key, value in row.items():
                if key in sensitive_fields:
                    masked_row[key] = self._mask_value(key, value)
                else:
                    masked_row[key] = value
            masked.append(masked_row)

        return masked

    def _get_sensitive_fields(
        self,
        sample_row: dict[str, Any],
        schema: Optional[dict[str, Any]],
        user_role: str,
    ) -> Set[str]:
        """获取需要脱敏的字段"""
        sensitive = set()

        # 1. 检查油库敏感字段
        if self.enable_oil_depot:
            for field in sample_row.keys():
                field_lower = field.lower()
                if field_lower in self.OIL_DEPOT_SENSITIVE_FIELDS:
                    sensitive.add(field)
                # 检查部分匹配
                for sensitive_pattern in self.OIL_DEPOT_SENSITIVE_FIELDS:
                    if sensitive_pattern in field_lower:
                        sensitive.add(field)
                        break

        # 2. 检查 schema 中标记的敏感字段
        if schema:
            for table_name, table_schema in schema.items():
                columns = table_schema.get("columns", [])
                for col in columns:
                    if col.get("sensitive"):
                        sensitive.add(col["name"])

        # 3. 检查字段名模式
        sensitive_keywords = ["password", "secret", "key", "token", "credential", "ssn"]
        for field in sample_row.keys():
            field_lower = field.lower()
            for keyword in sensitive_keywords:
                if keyword in field_lower:
                    sensitive.add(field)
                    break

        # 4. 根据角色过滤
        sensitive = self._filter_by_role(sensitive, user_role)

        return sensitive

    def _filter_by_role(self, sensitive: set[str], role: str) -> set[str]:
        """根据角色过滤敏感字段"""
        # admin 角色不过滤
        if role == "admin":
            return set()

        # 油库操作员：只能看脱敏后的库存
        if role == "operator":
            oil_depot_sensitive = {
                "inventory_amount", "stock_quantity", "tank_level",
                "safety_pressure", "alarm_threshold",
            }
            return sensitive & oil_depot_sensitive

        # 只读用户：全部脱敏
        if role == "readonly":
            return sensitive

        # 普通用户：只保留高敏感字段
        high_sensitive = {"password", "api_key", "secret_key", "token", "credential"}
        return sensitive & high_sensitive

    def _mask_value(self, field: str, value: Any) -> Any:
        """脱敏值"""
        if value is None:
            return None

        field_lower = field.lower()
        value_str = str(value)

        # 密码类
        if any(kw in field_lower for kw in ["password", "passwd", "pwd", "secret"]):
            return "******"

        # API Key / Token
        if any(kw in field_lower for kw in ["api_key", "token", "credential"]):
            if len(value_str) > 8:
                return value_str[:4] + "****" + value_str[-4:]
            return "****"

        # 数值型敏感数据（油库场景）
        if any(kw in field_lower for kw in ["level", "amount", "quantity", "stock", "pressure"]):
            if self._is_numeric(value):
                return "[已脱敏]"

        # 默认脱敏
        return "***"

    def _is_numeric(self, value: Any) -> bool:
        """判断是否为数值"""
        try:
            float(value)
            return True
        except (TypeError, ValueError):
            return False

    def mask_value_by_type(
        self,
        value: Any,
        value_type: str,
    ) -> Any:
        """
        根据类型脱敏值

        Args:
            value: 原始值
            value_type: 值类型（email, phone, id_card, etc.）

        Returns:
            脱敏后的值
        """
        if value is None:
            return None

        value_str = str(value)

        type_masks = {
            "email": lambda v: v[0] + "***@" + v.split("@")[-1] if "@" in v else "***",
            "phone": lambda v: v[:3] + "****" + v[-4:] if len(v) >= 7 else "***",
            "id_card": lambda v: "**************" + v[-4:] if len(v) >= 15 else "***",
            "bank_card": lambda v: "**** **** **** " + v[-4:] if len(v) >= 13 else "***",
            "password": lambda v: "******",
            "api_key": lambda v: v[:4] + "****" + v[-4:] if len(v) >= 8 else "***",
        }

        mask_func = type_masks.get(value_type.lower())
        if mask_func:
            try:
                return mask_func(value_str)
            except Exception:
                return "***"

        return value_str

    def mask_sql_result(
        self,
        sql: str,
        result: list[dict[str, Any]],
        columns: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        对 SQL 查询结果进行脱敏

        Args:
            sql: SQL 语句
            result: 查询结果
            columns: 列信息

        Returns:
            脱敏后的结果
        """
        # 从列信息中获取敏感字段
        schema = {}
        for col in columns:
            if col.get("sensitive"):
                table = col.get("table", "default")
                if table not in schema:
                    schema[table] = {"columns": []}
                schema[table]["columns"].append(col)

        return self.mask_result(result, schema)


# =============================================================================
# 便捷函数
# =============================================================================

def mask_sensitive_data(
    result: list[dict[str, Any]],
    user_role: str = "user",
) -> list[dict[str, Any]]:
    """
    便捷函数：脱敏数据

    Args:
        result: 查询结果
        user_role: 用户角色

    Returns:
        脱敏后的结果
    """
    masker = DataMasker()
    return masker.mask_result(result, user_role=user_role)


def mask_field(value: Any, field_name: str) -> Any:
    """
    便捷函数：脱敏单个字段

    Args:
        value: 字段值
        field_name: 字段名

    Returns:
        脱敏后的值
    """
    masker = DataMasker()
    return masker._mask_value(field_name, value)
