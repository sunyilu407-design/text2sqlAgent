"""AnomalyDetector 单元测试"""

import pytest
from micro_genbi.service.anomaly_detector import (
    AnomalyDetector,
    AnomalyRecord,
    AnomalyDetectionResult,
)


class TestAnomalyDetector:
    """异常检测器测试"""

    @pytest.fixture
    def detector(self) -> AnomalyDetector:
        return AnomalyDetector()

    @pytest.fixture
    def normal_data(self) -> list[dict]:
        return [
            {"date": "2024-01-01", "value": 100},
            {"date": "2024-01-02", "value": 105},
            {"date": "2024-01-03", "value": 98},
            {"date": "2024-01-04", "value": 102},
            {"date": "2024-01-05", "value": 99},
            {"date": "2024-01-06", "value": 101},
            {"date": "2024-01-07", "value": 104},
        ]

    @pytest.fixture
    def data_with_outliers(self) -> list[dict]:
        return [
            {"date": "2024-01-01", "value": 100},
            {"date": "2024-01-02", "value": 105},
            {"date": "2024-01-03", "value": 98},
            {"date": "2024-01-04", "value": 500},
            {"date": "2024-01-05", "value": 99},
            {"date": "2024-01-06", "value": 101},
            {"date": "2024-01-07", "value": 1000},
        ]

    def test_detect_zscore_normal(self, detector: AnomalyDetector, normal_data):
        """正常数据应无异常"""
        result = detector.detect_anomalies(normal_data, ["value"], method="zscore")
        assert len(result.anomalies) == 0

    def test_detect_zscore_returns_result(self, detector: AnomalyDetector):
        """Z-Score 检测应返回正确结构"""
        data = [{"v": 1}, {"v": 2}, {"v": 3}]
        result = detector.detect_anomalies(data, ["v"], method="zscore")
        assert isinstance(result.anomalies, list)
        assert isinstance(result.summary, dict)
        assert isinstance(result.severity_counts, dict)
        assert result.summary.get("method") == "zscore"

    def test_detect_zscore_empty(self, detector: AnomalyDetector):
        """空数据应返回空结果"""
        result = detector.detect_anomalies([], ["value"], method="zscore")
        assert len(result.anomalies) == 0

    def test_detect_iqr_normal(self, detector: AnomalyDetector, normal_data):
        """正常数据 IQR 检测应无异常"""
        result = detector.detect_anomalies(normal_data, ["value"], method="iqr")
        assert len(result.anomalies) == 0

    def test_detect_iqr_returns_result(self, detector: AnomalyDetector):
        """IQR 检测应返回正确结构"""
        data = [{"v": 1}, {"v": 2}, {"v": 3}]
        result = detector.detect_anomalies(data, ["v"], method="iqr")
        assert isinstance(result.anomalies, list)
        assert isinstance(result.summary, dict)
        assert isinstance(result.severity_counts, dict)
        assert result.summary.get("method") == "iqr"

    def test_detect_no_value_column(self, detector: AnomalyDetector):
        """不存在的列应返回空结果"""
        data = [{"x": 1}, {"x": 2}]
        result = detector.detect_anomalies(data, ["nonexistent"], method="zscore")
        assert len(result.anomalies) == 0

    def test_detect_single_row(self, detector: AnomalyDetector):
        """单行数据应返回空结果"""
        data = [{"value": 100}]
        result = detector.detect_anomalies(data, ["value"], method="zscore")
        assert len(result.anomalies) == 0

    def test_anomaly_record_structure(self, detector: AnomalyDetector):
        """异常记录应包含必需字段"""
        data = [{"v": 1}, {"v": 2}, {"v": 3}, {"v": 1000}]
        result = detector.detect_anomalies(data, ["v"], method="zscore")
        for anomaly in result.anomalies:
            assert anomaly.row_index >= 0
            assert anomaly.column == "v"
            assert isinstance(anomaly.value, float)
            assert isinstance(anomaly.score, float)
            assert anomaly.severity in ("low", "medium", "high", "critical")

    def test_summary_generation(self, detector: AnomalyDetector, data_with_outliers):
        """检测结果应生成摘要"""
        result = detector.detect_anomalies(data_with_outliers, ["value"], method="zscore")
        assert isinstance(result.summary, dict)
        assert "total_rows" in result.summary

    def test_invalid_method_raises(self, detector: AnomalyDetector):
        """不支持的方法应抛出异常"""
        with pytest.raises(ValueError):
            detector.detect_anomalies([{"v": 1}], ["v"], method="invalid_method")

    def test_severity_counts(self, detector: AnomalyDetector, data_with_outliers):
        """严重程度计数应正确"""
        result = detector.detect_anomalies(data_with_outliers, ["value"], method="zscore")
        assert isinstance(result.severity_counts, dict)
