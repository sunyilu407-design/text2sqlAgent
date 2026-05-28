"""Prediction service as unified entry point for time series forecasting.

This module provides a unified PredictionService that automatically selects
the appropriate forecasting method based on data characteristics.

Features:
- Auto-selection between Prophet and Statistics predictors
- Model caching to avoid redundant training
- Result caching for performance optimization
- Graceful fallback when Prophet is unavailable
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any

from micro_genbi.prediction.statistics_predictor import (
    StatisticsPredictor,
    ForecastResult as StatsForecastResult,
    ForecastPoint as StatsForecastPoint,
)
from micro_genbi.prediction.prophet_predictor import (
    ProphetPredictor,
    ForecastResult as ProphetForecastResult,
    ProphetForecastPoint,
    PROPHET_AVAILABLE as PROPHET_INSTALLED,
)


# Default cache TTL in seconds
DEFAULT_CACHE_TTL = 3600


@dataclass
class PredictionServiceResult:
    """Unified result format for prediction service.
    
    Attributes:
        model_used: Which model was used ("prophet", "statistics", or "none").
        forecast_values: List of forecast data points.
        metrics: Evaluation metrics (may vary by model).
        interpretation: Chinese natural language summary.
        cached: Whether the result was served from cache.
    """
    model_used: str = "none"
    forecast_values: list[Any] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    interpretation: str = ""
    cached: bool = False


class PredictionService:
    """Unified prediction service with automatic model selection.
    
    This service provides a single entry point for time series forecasting,
    automatically selecting the most appropriate method based on data
    characteristics.
    
    Model Selection Logic:
    - mode="auto": Data > 100 rows and has variance → Prophet, else Statistics
    - mode="prophet": Force Prophet (fails gracefully if unavailable)
    - mode="statistics": Force Statistics predictor
    
    Caching:
    - Model cache: Avoids retraining same data (TTL 3600s)
    - Result cache: Stores forecast results (TTL 3600s)
    
    Example:
        >>> service = PredictionService({"cache_ttl": 7200})
        >>> data = [
        ...     {"date": "2024-01-01", "sales": 100},
        ...     {"date": "2024-02-01", "sales": 120},
        ...     {"date": "2024-03-01", "sales": 115},
        ... ]
        >>> result = service.predict(
        ...     data, "date", "sales", periods=3, mode="auto"
        ... )
        >>> print(f"Used model: {result.model_used}")
        >>> print(f"Interpretation: {result.interpretation}")
    """
    
    # Threshold for auto-selecting Prophet
    AUTO_PROPHET_ROWS_THRESHOLD = 100
    VARIANCE_THRESHOLD = 0.01
    
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Initialize prediction service with configuration.
        
        Args:
            config: Optional configuration dictionary with keys:
                - cache_ttl: Cache TTL in seconds (default 3600)
                - force_prophet: Always prefer Prophet if available
                - statistics_fallback: Use Statistics if Prophet unavailable
        """
        self.config = config or {}
        
        # Cache settings
        self.cache_ttl = self.config.get("cache_ttl", DEFAULT_CACHE_TTL)
        self.force_prophet = self.config.get("force_prophet", False)
        self.statistics_fallback = self.config.get("statistics_fallback", True)
        
        # Initialize caches
        self._model_cache: dict[str, tuple[Any, float]] = {}
        self._result_cache: dict[str, tuple[PredictionServiceResult, float]] = {}
        
        # Initialize predictors
        self._statistics_predictor = StatisticsPredictor()
        self._prophet_predictor: ProphetPredictor | None = None
        
        if PROPHET_INSTALLED:
            self._prophet_predictor = ProphetPredictor()
    
    def predict(
        self,
        data: list[dict[str, Any]],
        time_col: str,
        value_col: str,
        periods: int = 3,
        mode: str = "auto"
    ) -> PredictionServiceResult:
        """Generate forecast for the specified time series.
        
        Args:
            data: List of dictionaries with time and value columns.
            time_col: Name of the time/date column.
            value_col: Name of the value column to forecast.
            periods: Number of future periods to forecast (default 3).
            mode: Prediction mode - "auto", "prophet", or "statistics".
                - "auto": Automatically select based on data characteristics
                - "prophet": Force Prophet (falls back to Statistics if unavailable)
                - "statistics": Use Statistics predictor only
        
        Returns:
            PredictionServiceResult with model_used, forecast_values,
            metrics, interpretation, and cached flag.
        
        Raises:
            ValueError: If mode is invalid or data is insufficient.
        """
        # Validate mode
        valid_modes = {"auto", "prophet", "statistics"}
        if mode not in valid_modes:
            raise ValueError(f"Invalid mode: {mode}. Must be one of {valid_modes}")
        
        if not data:
            return PredictionServiceResult(
                interpretation="错误：提供的数据为空"
            )
        
        # Check result cache
        cache_key = self._cache_result_key(data, time_col, value_col, periods, mode)
        cached_result = self._get_cached_result(cache_key)
        if cached_result is not None:
            cached_result.cached = True
            return cached_result
        
        # Determine which model to use
        if mode == "prophet":
            result = self._predict_with_prophet(data, time_col, value_col, periods)
            if result.model_used == "none":
                if self.statistics_fallback:
                    result = self._predict_with_statistics(data, time_col, value_col, periods)
        elif mode == "statistics":
            result = self._predict_with_statistics(data, time_col, value_col, periods)
        else:  # auto
            if self._should_use_prophet(data):
                result = self._predict_with_prophet(data, time_col, value_col, periods)
                if result.model_used == "none" and self.statistics_fallback:
                    result = self._predict_with_statistics(data, time_col, value_col, periods)
            else:
                result = self._predict_with_statistics(data, time_col, value_col, periods)
        
        # Cache the result
        self._cache_result(cache_key, result)
        
        return result
    
    def _should_use_prophet(self, data: list[dict[str, Any]]) -> bool:
        """Determine if Prophet should be used based on data characteristics.
        
        Prophet is preferred when:
        - There are sufficient data points (> AUTO_PROPHET_ROWS_THRESHOLD)
        - The data shows meaningful variance
        
        Args:
            data: List of dictionaries with data points.
        
        Returns:
            True if Prophet should be used, False otherwise.
        """
        # Check if Prophet is available
        if not PROPHET_INSTALLED:
            return False
        
        if not self._prophet_predictor:
            return False
        
        # Check data size
        if len(data) < self.AUTO_PROPHET_ROWS_THRESHOLD:
            return False
        
        # Check variance
        values: list[float] = []
        for row in data:
            for val in row.values():
                if isinstance(val, (int, float)) and not isinstance(val, bool):
                    values.append(float(val))
                    break
        
        if len(values) < 2:
            return False
        
        # Calculate coefficient of variation
        mean_val = sum(values) / len(values)
        if mean_val == 0:
            return False
        
        variance = sum((v - mean_val) ** 2 for v in values) / len(values)
        std_dev = variance ** 0.5
        cv = std_dev / abs(mean_val)
        
        return cv > self.VARIANCE_THRESHOLD
    
    def _cache_model_key(
        self,
        data: list[dict[str, Any]],
        time_col: str,
        value_col: str
    ) -> str:
        """Generate cache key for model training.
        
        Args:
            data: Input data.
            time_col: Time column name.
            value_col: Value column name.
        
        Returns:
            Cache key string.
        """
        data_hash = hashlib.md5(
            json.dumps(data, sort_keys=True, default=str).encode()
        ).hexdigest()
        return f"model:{data_hash}:{time_col}:{value_col}"
    
    def _cache_result_key(
        self,
        data: list[dict[str, Any]],
        time_col: str,
        value_col: str,
        periods: int,
        mode: str
    ) -> str:
        """Generate cache key for forecast results.
        
        Args:
            data: Input data.
            time_col: Time column name.
            value_col: Value column name.
            periods: Number of forecast periods.
            mode: Prediction mode.
        
        Returns:
            Cache key string.
        """
        data_hash = hashlib.md5(
            json.dumps(data, sort_keys=True, default=str).encode()
        ).hexdigest()
        return f"result:{data_hash}:{time_col}:{value_col}:{periods}:{mode}"
    
    def _get_cached_result(self, cache_key: str) -> PredictionServiceResult | None:
        """Retrieve cached result if still valid.
        
        Args:
            cache_key: Cache key to look up.
        
        Returns:
            Cached result or None if not found or expired.
        """
        if cache_key not in self._result_cache:
            return None
        
        result, timestamp = self._result_cache[cache_key]
        
        if time.time() - timestamp > self.cache_ttl:
            del self._result_cache[cache_key]
            return None
        
        return result
    
    def _cache_result(self, cache_key: str, result: PredictionServiceResult) -> None:
        """Cache a forecast result.
        
        Args:
            cache_key: Cache key for the result.
            result: Result to cache.
        """
        # Clean expired entries
        self._clean_expired_cache()
        
        self._result_cache[cache_key] = (result, time.time())
    
    def _clean_expired_cache(self) -> None:
        """Remove expired entries from result cache."""
        current_time = time.time()
        expired_keys = [
            key for key, (_, timestamp) in self._result_cache.items()
            if current_time - timestamp > self.cache_ttl
        ]
        for key in expired_keys:
            del self._result_cache[key]
        
        # Also clean model cache
        expired_model_keys = [
            key for key, (_, timestamp) in self._model_cache.items()
            if current_time - timestamp > self.cache_ttl
        ]
        for key in expired_model_keys:
            del self._model_cache[key]
    
    def _predict_with_prophet(
        self,
        data: list[dict[str, Any]],
        time_col: str,
        value_col: str,
        periods: int
    ) -> PredictionServiceResult:
        """Generate forecast using Prophet.
        
        Args:
            data: Input data.
            time_col: Time column name.
            value_col: Value column name.
            periods: Number of periods to forecast.
        
        Returns:
            PredictionServiceResult with Prophet forecast or error state.
        """
        if not PROPHET_INSTALLED or not self._prophet_predictor:
            return PredictionServiceResult(
                model_used="none",
                interpretation="Prophet 未安装，使用统计方法进行预测"
            )
        
        try:
            prophet_result = self._prophet_predictor.forecast(
                data, time_col, value_col, periods
            )
            
            if not prophet_result.forecast_values:
                return PredictionServiceResult(
                    model_used="prophet",
                    interpretation=prophet_result.interpretation or "Prophet 预测失败"
                )
            
            # Convert to unified format
            forecast_values = []
            for point in prophet_result.forecast_values:
                forecast_values.append({
                    "date": point.ds,
                    "value": point.yhat,
                    "lower_bound": point.yhat_lower,
                    "upper_bound": point.yhat_upper
                })
            
            return PredictionServiceResult(
                model_used="prophet",
                forecast_values=forecast_values,
                metrics={
                    "mape": prophet_result.metrics.mape,
                    "rmse": prophet_result.metrics.rmse,
                    "r_squared": prophet_result.metrics.r_squared
                },
                interpretation=prophet_result.interpretation
            )
            
        except Exception as e:
            return PredictionServiceResult(
                model_used="prophet",
                interpretation=f"Prophet 预测出错: {str(e)}"
            )
    
    def _predict_with_statistics(
        self,
        data: list[dict[str, Any]],
        time_col: str,
        value_col: str,
        periods: int
    ) -> PredictionServiceResult:
        """Generate forecast using Statistics predictor.
        
        Args:
            data: Input data.
            time_col: Time column name.
            value_col: Value column name.
            periods: Number of periods to forecast.
        
        Returns:
            PredictionServiceResult with Statistics forecast.
        """
        try:
            stats_result = self._statistics_predictor.forecast(
                data, time_col, value_col, periods
            )
            
            # Convert to unified format
            forecast_values = []
            for point in stats_result.forecast_values:
                forecast_values.append({
                    "date": point.date,
                    "value": point.value,
                    "lower_bound": point.lower_bound,
                    "upper_bound": point.upper_bound
                })
            
            return PredictionServiceResult(
                model_used="statistics",
                forecast_values=forecast_values,
                metrics={
                    "confidence_interval": stats_result.confidence_interval
                },
                interpretation=stats_result.interpretation
            )
            
        except Exception as e:
            return PredictionServiceResult(
                model_used="statistics",
                interpretation=f"统计预测出错: {str(e)}"
            )
    
    def clear_cache(self) -> None:
        """Clear all cached models and results."""
        self._model_cache.clear()
        self._result_cache.clear()
    
    def get_cache_stats(self) -> dict[str, int]:
        """Get cache statistics.
        
        Returns:
            Dictionary with cache sizes.
        """
        return {
            "model_cache_size": len(self._model_cache),
            "result_cache_size": len(self._result_cache)
        }
    
    def is_prophet_available(self) -> bool:
        """Check if Prophet is available.
        
        Returns:
            True if Prophet can be used, False otherwise.
        """
        return PROPHET_INSTALLED
    
    @property
    def statistics_predictor(self) -> StatisticsPredictor:
        """Get the underlying statistics predictor.
        
        Returns:
            StatisticsPredictor instance.
        """
        return self._statistics_predictor
    
    @property
    def prophet_predictor(self) -> ProphetPredictor | None:
        """Get the underlying Prophet predictor.
        
        Returns:
            ProphetPredictor instance or None if unavailable.
        """
        return self._prophet_predictor
