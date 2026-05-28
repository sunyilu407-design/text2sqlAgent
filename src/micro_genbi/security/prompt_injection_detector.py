"""Prompt 注入检测器

检测用户输入中可能的 Prompt 注入尝试。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from micro_genbi.errors import GenBIError


@dataclass
class InjectionCheckResult:
    """注入检测结果"""
    is_safe: bool
    violations: list[dict]
    risk_score: float  # 0.0 - 1.0


class PromptInjectionDetector:
    """
    Prompt 注入检测器

    检测用户输入中可能的 Prompt 注入尝试。
    """

    # 注入模式
    INJECTION_PATTERNS: list[tuple[str, str, str]] = [
        # 角色扮演绕过
        (r"(?i)(ignore|disregard|bypass).*(previous|above|instruction|system)",
         "injection_pattern", "high", "block"),
        (r"(?i)(you are now|act as|pretend to be|imagine you are)",
         "role_play", "high", "block"),
        (r"(?i)forget (all |)previous (instructions|commands|rules)",
         "instruction_override", "high", "block"),

        # 提示泄露
        (r"(?i)(what (are |is )?your (system |)prompt)",
         "prompt_leak", "medium", "block"),
        (r"(?i)(reveal your (system |)instruction)",
         "prompt_leak", "medium", "block"),
        (r"(?i)(what (were |was )?you told)",
         "prompt_leak", "medium", "block"),

        # 越狱提示
        (r"(?i)dan[ ,]+(do|anything|now)",
         "jailbreak", "critical", "block"),
        (r"(?i)(jailbreak)",
         "jailbreak", "critical", "block"),
        (r"(?i)(developer mode)",
         "jailbreak", "high", "block"),

        # SQL 注入试探
        (r"(?i)(admin|';|UNION|SELECT|--).*(FROM|WHERE)",
         "sql_injection_attempt", "high", "block"),
        (r"(?i)(execute|run).*(shell|command|system)",
         "system_command", "critical", "block"),
    ]

    # 油库场景敏感词
    OIL_DEPOT_SENSITIVE_PATTERNS: list[tuple[str, str, str, str]] = [
        (r"(?i)(shutdown|stop|emergency|evacuation)",
         "safety_keyword", "critical", "block"),
        (r"(?i)(override|disable).*(safety|alarm|protocol)",
         "safety_bypass", "critical", "block"),
        (r"(?i)(set.*pressure.*high|disable.*sensor)",
         "equipment_control", "critical", "block"),
    ]

    def __init__(self, enable_oil_depot_sensitive: bool = True):
        self.enable_oil_depot_sensitive = enable_oil_depot_sensitive

    def detect(self, user_input: str) -> InjectionCheckResult:
        """
        检测 Prompt 注入

        Args:
            user_input: 用户输入

        Returns:
            InjectionCheckResult: 检测结果
        """
        violations: list[dict] = []

        # 1. 模式匹配检测
        for pattern, violation_type, severity, action in self.INJECTION_PATTERNS:
            if re.search(pattern, user_input):
                violations.append({
                    "type": violation_type,
                    "pattern": pattern,
                    "severity": severity,
                    "action": action,
                })

        # 2. 油库敏感词检测（可选）
        if self.enable_oil_depot_sensitive:
            for pattern, violation_type, severity, action in self.OIL_DEPOT_SENSITIVE_PATTERNS:
                if re.search(pattern, user_input):
                    violations.append({
                        "type": violation_type,
                        "pattern": pattern,
                        "severity": severity,
                        "action": action,
                    })

        # 3. 重复模式检测（自动注入特征）
        if self._detect_repetition(user_input):
            violations.append({
                "type": "repetition_pattern",
                "severity": "medium",
            })

        # 4. Base64/编码检测
        if self._contains_encoded_content(user_input):
            violations.append({
                "type": "encoded_content",
                "severity": "high",
            })

        # 5. 计算风险分数
        risk_score = self._calculate_risk_score(violations)

        # 6. 判断是否安全
        is_safe = len([v for v in violations if v.get("action") == "block"]) == 0

        return InjectionCheckResult(
            is_safe=is_safe,
            violations=violations,
            risk_score=risk_score,
        )

    def _detect_repetition(self, text: str) -> bool:
        """检测重复模式（自动注入特征）"""
        words = text.split()
        if len(words) < 20:
            return False

        # 检查是否有大量重复词
        from collections import Counter
        word_counts = Counter(words)
        max_ratio = max(word_counts.values()) / len(words)
        return max_ratio > 0.3

    def _contains_encoded_content(self, text: str) -> bool:
        """检测编码内容"""
        # Base64 检测
        if re.match(r'^[A-Za-z0-9+/]+=*$', text.strip()):
            if len(text.strip()) > 50:
                return True

        # URL 编码检测
        if '%' in text and re.search(r'%[0-9A-Fa-f]{2}', text):
            return True

        return False

    def _calculate_risk_score(self, violations: list[dict]) -> float:
        """计算风险分数"""
        if not violations:
            return 0.0

        severity_weights = {
            "critical": 1.0,
            "high": 0.7,
            "medium": 0.4,
            "low": 0.2,
        }

        total_score = 0.0
        for v in violations:
            severity = v.get("severity", "medium")
            total_score += severity_weights.get(severity, 0.5)

        return min(total_score / len(violations), 1.0)

    def detect_and_raise(self, user_input: str) -> None:
        """
        检测并抛出异常

        Args:
            user_input: 用户输入

        Raises:
            PermissionDeniedError: 检测到注入攻击
        """
        from micro_genbi.errors import PermissionDeniedError

        result = self.detect(user_input)
        if not result.is_safe:
            raise PermissionDeniedError(
                f"检测到可疑输入: {result.violations[0]['type']}"
            )


# =============================================================================
# 便捷函数
# =============================================================================

def check_prompt_safety(user_input: str) -> InjectionCheckResult:
    """
    便捷函数：检查 Prompt 安全性

    Args:
        user_input: 用户输入

    Returns:
        InjectionCheckResult: 检测结果
    """
    detector = PromptInjectionDetector()
    return detector.detect(user_input)


def is_safe_input(user_input: str) -> bool:
    """
    便捷函数：判断输入是否安全

    Args:
        user_input: 用户输入

    Returns:
        bool: 是否安全
    """
    result = check_prompt_safety(user_input)
    return result.is_safe
