"""Prediction module for time series forecasting and anomaly detection.

This module provides lightweight statistical methods for:
- Anomaly detection in numerical data
- Time series forecasting with confidence intervals
- Facebook Prophet integration for advanced forecasting
- Unified prediction service with auto-selection
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from micro_genbi.service.anomaly_detector import AnomalyDetector
else:
    AnomalyDetector = None  # type: ignore

from micro_genbi.prediction.statistics_predictor import StatisticsPredictor
from micro_genbi.prediction.prophet_predictor import ProphetPredictor, ForecastResult as ProphetForecastResult
from micro_genbi.prediction.prediction_service import PredictionService, PredictionServiceResult

__all__ = [
    "AnomalyDetector",
    "StatisticsPredictor",
    "ProphetPredictor",
    "ProphetForecastResult",
    "PredictionService",
    "PredictionServiceResult",
]
