"""Anomaly detection module for identifying anomalous data points in datasets.

Supports multiple detection methods:
- Z-Score: Values beyond 3 standard deviations from mean
- IQR: Values outside interquartile range
- Trend: Sudden jumps or drops in time series data
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AnomalyRecord:
    """Represents a single detected anomaly."""
    row_index: int
    column: str
    value: float
    expected_range: tuple[float, float]
    score: float
    severity: str


@dataclass
class AnomalyDetectionResult:
    """Result of anomaly detection analysis."""
    anomalies: list[AnomalyRecord] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    severity_counts: dict[str, int] = field(default_factory=dict)


class AnomalyDetector:
    """Detects anomalous data points using statistical methods.
    
    Supports Z-Score, IQR, and trend-based anomaly detection.
    
    Example:
        >>> detector = AnomalyDetector()
        >>> data = [{"value": 10}, {"value": 12}, {"value": 100}]
        >>> result = detector.detect_anomalies(data, ["value"], method="zscore")
        >>> print(f"Found {len(result.anomalies)} anomalies")
    """
    
    # Severity thresholds based on standard deviations
    SEVERITY_CRITICAL_THRESHOLD = 4.0
    SEVERITY_HIGH_THRESHOLD = 3.0
    SEVERITY_MEDIUM_THRESHOLD = 2.0
    SEVERITY_LOW_THRESHOLD = 1.5
    
    # Z-Score defaults
    DEFAULT_ZSCORE_THRESHOLD = 3.0
    
    # IQR defaults
    DEFAULT_IQR_FACTOR = 1.5
    
    def detect_anomalies(
        self,
        data: list[dict[str, Any]],
        columns: list[str],
        method: str = "zscore"
    ) -> AnomalyDetectionResult:
        """Detect anomalies in the specified columns using the given method.
        
        Args:
            data: List of dictionaries representing rows.
            columns: List of column names to analyze.
            method: Detection method - "zscore", "iqr", or "trend".
                   Defaults to "zscore".
        
        Returns:
            AnomalyDetectionResult with anomalies, summary, and severity counts.
        
        Raises:
            ValueError: If method is not supported.
        """
        if not data:
            return AnomalyDetectionResult(
                summary={"error": "Empty dataset provided"},
                severity_counts={}
            )
        
        anomalies: list[AnomalyRecord] = []
        
        for column in columns:
            if method == "zscore":
                col_anomalies = self._detect_zscore(data, column)
            elif method == "iqr":
                col_anomalies = self._detect_iqr(data, column)
            elif method == "trend":
                col_anomalies = self._detect_trend_anomaly(data, None, column)
            else:
                raise ValueError(
                    f"Unsupported method: {method}. "
                    f"Use 'zscore', 'iqr', or 'trend'."
                )
            anomalies.extend(col_anomalies)
        
        severity_counts = self._count_severities(anomalies)
        
        summary = self._generate_summary(data, columns, anomalies, method)
        
        return AnomalyDetectionResult(
            anomalies=anomalies,
            summary=summary,
            severity_counts=severity_counts
        )
    
    def _detect_zscore(
        self,
        data: list[dict[str, Any]],
        column: str,
        threshold: float = 3.0
    ) -> list[AnomalyRecord]:
        """Detect anomalies using Z-Score method.
        
        Values beyond `threshold` standard deviations from mean are flagged.
        
        Args:
            data: List of dictionaries representing rows.
            column: Column name to analyze.
            threshold: Z-Score threshold (default 3.0).
        
        Returns:
            List of AnomalyRecord for detected anomalies.
        """
        anomalies: list[AnomalyRecord] = []
        
        # Extract numeric values and their indices
        numeric_values: list[tuple[int, float]] = []
        for i, row in enumerate(data):
            if column in row:
                value = row[column]
                if self._is_numeric(value):
                    numeric_values.append((i, float(value)))
        
        if len(numeric_values) < 3:
            return anomalies
        
        values = [v for _, v in numeric_values]
        mean = sum(values) / len(values)
        
        # Calculate standard deviation
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        std = math.sqrt(variance)
        
        if std == 0:
            return anomalies
        
        for idx, value in numeric_values:
            z_score = self._compute_zscore(value, mean, std)
            
            if abs(z_score) > threshold:
                lower_bound = mean - threshold * std
                upper_bound = mean + threshold * std
                
                severity = self._determine_severity(abs(z_score))
                
                anomalies.append(AnomalyRecord(
                    row_index=idx,
                    column=column,
                    value=value,
                    expected_range=(round(lower_bound, 2), round(upper_bound, 2)),
                    score=round(z_score, 3),
                    severity=severity
                ))
        
        return anomalies
    
    def _detect_iqr(
        self,
        data: list[dict[str, Any]],
        column: str,
        factor: float = 1.5
    ) -> list[AnomalyRecord]:
        """Detect anomalies using Interquartile Range (IQR) method.
        
        Values outside Q1 - factor*IQR or Q3 + factor*IQR are flagged.
        
        Args:
            data: List of dictionaries representing rows.
            column: Column name to analyze.
            factor: IQR multiplier (default 1.5).
        
        Returns:
            List of AnomalyRecord for detected anomalies.
        """
        anomalies: list[AnomalyRecord] = []
        
        # Extract numeric values and their indices
        numeric_values: list[tuple[int, float]] = []
        for i, row in enumerate(data):
            if column in row:
                value = row[column]
                if self._is_numeric(value):
                    numeric_values.append((i, float(value)))
        
        if len(numeric_values) < 4:
            return anomalies
        
        values = sorted([v for _, v in numeric_values])
        n = len(values)
        
        # Calculate quartiles
        q1_idx = n // 4
        q3_idx = 3 * n // 4
        
        q1 = values[q1_idx]
        q3 = values[q3_idx]
        iqr = q3 - q1
        
        # Calculate bounds
        lower_bound = q1 - factor * iqr
        upper_bound = q3 + factor * iqr
        
        for idx, value in numeric_values:
            if value < lower_bound or value > upper_bound:
                # Calculate IQR-based score
                if value < lower_bound:
                    iqr_score = (lower_bound - value) / iqr if iqr != 0 else 0
                else:
                    iqr_score = (value - upper_bound) / iqr if iqr != 0 else 0
                
                severity = self._determine_severity(iqr_score)
                
                anomalies.append(AnomalyRecord(
                    row_index=idx,
                    column=column,
                    value=value,
                    expected_range=(round(lower_bound, 2), round(upper_bound, 2)),
                    score=round(iqr_score, 3),
                    severity=severity
                ))
        
        return anomalies
    
    def _detect_trend_anomaly(
        self,
        data: list[dict[str, Any]],
        time_col: str | None,
        value_col: str
    ) -> list[AnomalyRecord]:
        """Detect sudden jumps or drops in time series.
        
        Compares each value with its neighbors to find sudden changes.
        If time_col is None, uses row index as time proxy.
        
        Args:
            data: List of dictionaries representing rows.
            time_col: Time/date column name (optional).
            value_col: Value column name to analyze.
        
        Returns:
            List of AnomalyRecord for detected trend anomalies.
        """
        anomalies: list[AnomalyRecord] = []
        
        # Extract values with their order
        numeric_values: list[tuple[int, float]] = []
        for i, row in enumerate(data):
            if value_col in row:
                value = row[value_col]
                if self._is_numeric(value):
                    numeric_values.append((i, float(value)))
        
        if len(numeric_values) < 3:
            return anomalies
        
        values = [v for _, v in numeric_values]
        
        # Calculate differences between consecutive values
        diffs = []
        for i in range(1, len(values)):
            diff = values[i] - values[i - 1]
            diffs.append(diff)
        
        if not diffs:
            return anomalies
        
        # Calculate statistics of differences
        mean_diff = sum(diffs) / len(diffs)
        diff_variance = sum((d - mean_diff) ** 2 for d in diffs) / len(diffs)
        diff_std = math.sqrt(diff_variance)
        
        if diff_std == 0:
            return anomalies
        
        # Z-score threshold for trend anomalies
        trend_threshold = 2.5
        
        for i in range(1, len(values)):
            idx, value = numeric_values[i]
            diff = values[i] - values[i - 1]
            z_score = self._compute_zscore(diff, mean_diff, diff_std)
            
            if abs(z_score) > trend_threshold:
                prev_value = values[i - 1]
                expected_change = mean_diff
                expected_value = prev_value + expected_change
                
                lower_bound = expected_value - 2 * diff_std
                upper_bound = expected_value + 2 * diff_std
                
                severity = self._determine_severity(abs(z_score))
                
                anomalies.append(AnomalyRecord(
                    row_index=idx,
                    column=value_col,
                    value=value,
                    expected_range=(round(lower_bound, 2), round(upper_bound, 2)),
                    score=round(z_score, 3),
                    severity=severity
                ))
        
        return anomalies
    
    def _compute_zscore(self, value: float, mean: float, std: float) -> float:
        """Calculate Z-Score for a value.
        
        Args:
            value: The value to score.
            mean: The mean of the distribution.
            std: The standard deviation of the distribution.
        
        Returns:
            Z-Score (number of standard deviations from mean).
        
        Note:
            Returns 0 if std is 0 to avoid division by zero.
        """
        if std == 0:
            return 0.0
        return (value - mean) / std
    
    def _determine_severity(self, score: float) -> str:
        """Determine severity level based on score.
        
        Args:
            score: The anomaly score (Z-Score or IQR score).
        
        Returns:
            Severity level: "critical", "high", "medium", or "low".
        """
        if score > self.SEVERITY_CRITICAL_THRESHOLD:
            return "critical"
        elif score > self.SEVERITY_HIGH_THRESHOLD:
            return "high"
        elif score > self.SEVERITY_MEDIUM_THRESHOLD:
            return "medium"
        elif score > self.SEVERITY_LOW_THRESHOLD:
            return "low"
        else:
            return "info"
    
    def _count_severities(
        self,
        anomalies: list[AnomalyRecord]
    ) -> dict[str, int]:
        """Count anomalies by severity level.
        
        Args:
            anomalies: List of detected anomalies.
        
        Returns:
            Dictionary mapping severity to count.
        """
        counts: dict[str, int] = {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "info": 0
        }
        
        for anomaly in anomalies:
            counts[anomaly.severity] = counts.get(anomaly.severity, 0) + 1
        
        # Remove zero counts
        return {k: v for k, v in counts.items() if v > 0}
    
    def _generate_summary(
        self,
        data: list[dict[str, Any]],
        columns: list[str],
        anomalies: list[AnomalyRecord],
        method: str
    ) -> dict[str, Any]:
        """Generate summary statistics for the detection results.
        
        Args:
            data: Original dataset.
            columns: Columns analyzed.
            anomalies: Detected anomalies.
            method: Detection method used.
        
        Returns:
            Summary dictionary with statistics.
        """
        total_rows = len(data)
        total_anomalies = len(anomalies)
        anomaly_rate = (total_anomalies / total_rows * 100) if total_rows > 0 else 0
        
        # Column-specific statistics
        column_stats: dict[str, Any] = {}
        for column in columns:
            col_values = [
                row[column] for row in data
                if column in row and self._is_numeric(row[column])
            ]
            if col_values:
                numeric_vals = [float(v) for v in col_values]
                column_stats[column] = {
                    "count": len(numeric_vals),
                    "mean": round(sum(numeric_vals) / len(numeric_vals), 3),
                    "min": round(min(numeric_vals), 3),
                    "max": round(max(numeric_vals), 3)
                }
        
        return {
            "total_rows": total_rows,
            "total_anomalies": total_anomalies,
            "anomaly_rate": round(anomaly_rate, 2),
            "columns_analyzed": columns,
            "method": method,
            "column_statistics": column_stats
        }
    
    @staticmethod
    def _is_numeric(value: Any) -> bool:
        """Check if a value is numeric (int or float).
        
        Args:
            value: Value to check.
        
        Returns:
            True if value is int or float (excluding bool).
        """
        if isinstance(value, bool):
            return False
        return isinstance(value, (int, float))
