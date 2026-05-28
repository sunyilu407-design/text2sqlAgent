"""pytest 配置文件"""

import pytest
import sys
from pathlib import Path

# 添加 src 目录到路径
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))


@pytest.fixture
def sample_schema():
    """示例 Schema"""
    return {
        "databases": [
            {
                "id": "db_001",
                "name": "oil_depot",
                "tables": [
                    {
                        "name": "tank_inventory",
                        "display_name": "储罐库存",
                        "columns": [
                            {"name": "tank_id", "type": "VARCHAR"},
                            {"name": "tank_level", "type": "DECIMAL"},
                        ],
                    }
                ],
            }
        ]
    }


@pytest.fixture
def sample_query_result():
    """示例查询结果"""
    return [
        {"tank_id": "T001", "tank_level": 85.5},
        {"tank_id": "T002", "tank_level": 72.3},
    ]


@pytest.fixture
def malicious_sql_samples():
    """恶意 SQL 示例（用于测试安全验证）"""
    return [
        "SELECT * FROM users; DROP TABLE users; --",
        "SELECT * FROM admin WHERE id = 1 OR 1=1",
        "SELECT * FROM users UNION SELECT * FROM passwords",
        "'; DELETE FROM users WHERE '1'='1",
    ]


@pytest.fixture
def safe_sql_samples():
    """安全 SQL 示例"""
    return [
        "SELECT tank_id, tank_level FROM tank_inventory",
        "SELECT COUNT(*) FROM orders WHERE date > '2026-01-01'",
        "SELECT dept_name, SUM(amount) as total FROM expense GROUP BY dept_name",
    ]
