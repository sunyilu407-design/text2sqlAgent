"""Time series forecasting module using statistical methods.

Provides lightweight forecasting capabilities:
- Simple/Double Exponential Smoothing
- Growth rate analysis
- Basic seasonality detection
- Confidence interval estimation
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any


@dataclass
class ForecastPoint:
    """Represents a single forecast data point."""
    date: Any
    value: float
    lower_bound: float
    upper_bound: float


@dataclass
class ForecastResult:
    """Result of time series forecasting."""
    forecast_values: list[ForecastPoint] = field(default_factory=list)
    forecast_dates: list[Any] = field(default_factory=list)
    confidence_interval: tuple[float, float] = (0.15, 0.15)
    interpretation: str = ""


class StatisticsPredictor:
    """Lightweight time series forecasting using statistical methods.
    
    Supports exponential smoothing, growth rate analysis, and basic
    seasonality detection for time series data.
    
    Example:
        >>> predictor = StatisticsPredictor()
        >>> data = [
        ...     {"date": "2024-01-01", "value": 100},
        ...     {"date": "2024-02-01", "value": 120},
        ...     {"date": "2024-03-01", "value": 115},
        ... ]
        >>> result = predictor.forecast(data, "date", "value", periods=3)
        >>> print(f"Forecast: {result.forecast_values}")
    """
    
    # Confidence interval defaults
    DEFAULT_CONFIDENCE_WIDTH = 0.15  # ±15%
    DEFAULT_ALPHA = 0.3  # Smoothing factor
    
    # Seasonality detection
    MIN_SEASONAL_PERIOD = 4
    
    def forecast(
        self,
        data: list[dict[str, Any]],
        time_col: str,
        value_col: str,
        periods: int = 3
    ) -> ForecastResult:
        """Generate forecast for the specified time series.
        
        Args:
            data: List of dictionaries with time and value columns.
            time_col: Name of the time/date column.
            value_col: Name of the value column to forecast.
            periods: Number of future periods to forecast (default 3).
        
        Returns:
            ForecastResult with forecast values, dates, confidence
            intervals, and natural language interpretation.
        
        Raises:
            ValueError: If data is empty or invalid.
        """
        if not data:
            return ForecastResult(interpretation="错误：提供的数据为空")
        
        # Extract values
        values: list[float] = []
        dates: list[Any] = []
        
        for row in data:
            if time_col in row and value_col in row:
                val = row[value_col]
                if self._is_numeric(val):
                    values.append(float(val))
                    dates.append(row[time_col])
        
        if len(values) < 2:
            return ForecastResult(interpretation="错误：数据点不足，无法进行预测")
        
        # Check for variance
        if self._variance(values) == 0:
            return self._constant_forecast(values, dates, periods)
        
        # Calculate growth rates
        growth_rates = self._calculate_growth_rate(data, value_col)
        
        # Detect seasonality
        has_seasonality, seasonal_period = self._detect_seasonality(data, values)
        
        # Apply exponential smoothing
        smoothed_value = self._simple_exponential_smoothing(data, values)
        
        # Generate forecast
        forecast_values = self._generate_forecast_values(
            values, smoothed_value, growth_rates, periods
        )
        
        # Generate dates for forecast periods
        forecast_dates = self._generate_forecast_dates(dates, periods)
        
        # Calculate confidence intervals
        confidence = self._estimate_confidence_interval(values, periods)
        
        # Build forecast points
        forecast_points = []
        for i, (date, value) in enumerate(zip(forecast_dates, forecast_values)):
            lower = value * (1 - confidence)
            upper = value * (1 + confidence)
            forecast_points.append(ForecastPoint(
                date=date,
                value=round(value, 2),
                lower_bound=round(lower, 2),
                upper_bound=round(upper, 2)
            ))
        
        # Generate interpretation
        interpretation = self._generate_interpretation(growth_rates, forecast_values)
        
        return ForecastResult(
            forecast_values=forecast_points,
            forecast_dates=forecast_dates,
            confidence_interval=(confidence, confidence),
            interpretation=interpretation
        )
    
    def _calculate_growth_rate(
        self,
        data: list[dict[str, Any]],
        value_col: str
    ) -> list[float]:
        """Calculate period-over-period growth rates.
        
        Args:
            data: List of dictionaries with value column.
            value_col: Name of the value column.
        
        Returns:
            List of growth rates (as decimals, e.g., 0.05 for 5%).
        """
        growth_rates: list[float] = []
        
        values: list[float] = []
        for row in data:
            if value_col in row and self._is_numeric(row[value_col]):
                values.append(float(row[value_col]))
        
        for i in range(1, len(values)):
            prev_value = values[i - 1]
            if prev_value != 0:
                growth_rate = (values[i] - prev_value) / prev_value
                growth_rates.append(growth_rate)
        
        return growth_rates
    
    def _simple_exponential_smoothing(
        self,
        data: list[dict[str, Any]],
        values: list[float],
        alpha: float = 0.3
    ) -> float:
        """Apply simple exponential smoothing to values.
        
        Simple exponential smoothing formula:
        S_t = alpha * Y_t + (1 - alpha) * S_{t-1}
        
        Args:
            data: List of dictionaries (unused, kept for API compatibility).
            values: List of numeric values.
            alpha: Smoothing factor (0 < alpha <= 1).
        
        Returns:
            Smoothed forecast value.
        """
        if not values:
            return 0.0
        
        alpha = max(0.01, min(1.0, alpha))
        
        # Initialize with first value
        smoothed = values[0]
        
        # Apply smoothing
        for value in values[1:]:
            smoothed = alpha * value + (1 - alpha) * smoothed
        
        return smoothed
    
    def _double_exponential_smoothing(
        self,
        values: list[float],
        alpha: float = 0.3,
        beta: float = 0.1
    ) -> tuple[float, float]:
        """Apply double exponential smoothing (Holt's method).
        
        Handles trend in addition to level.
        
        Args:
            values: List of numeric values.
            alpha: Level smoothing factor.
            beta: Trend smoothing factor.
        
        Returns:
            Tuple of (smoothed_level, trend).
        """
        if len(values) < 2:
            return (values[0] if values else 0.0, 0.0)
        
        alpha = max(0.01, min(1.0, alpha))
        beta = max(0.01, min(1.0, beta))
        
        # Initialize level and trend
        level = values[0]
        trend = values[1] - values[0]
        
        # Apply double smoothing
        for i in range(1, len(values)):
            prev_level = level
            level = alpha * values[i] + (1 - alpha) * (level + trend)
            trend = beta * (level - prev_level) + (1 - beta) * trend
        
        return level, trend
    
    def _estimate_confidence_interval(
        self,
        values: list[float],
        periods: int = 3
    ) -> float:
        """Estimate confidence interval width for forecasts.
        
        Uses a simple ±15% confidence interval by default,
        adjusted based on data variance.
        
        Args:
            values: Historical values.
            periods: Number of forecast periods.
        
        Returns:
            Confidence interval width (e.g., 0.15 for ±15%).
        """
        if len(values) < 3:
            return self.DEFAULT_CONFIDENCE_WIDTH
        
        # Calculate coefficient of variation
        mean = sum(values) / len(values)
        std = math.sqrt(self._variance(values))
        
        if mean == 0:
            return self.DEFAULT_CONFIDENCE_WIDTH
        
        cv = std / abs(mean)
        
        # Adjust confidence width based on variance
        # Higher variance = wider confidence interval
        base_width = self.DEFAULT_CONFIDENCE_WIDTH
        
        if cv < 0.1:
            width = base_width
        elif cv < 0.3:
            width = base_width * 1.5
        else:
            width = base_width * 2
        
        # Wider intervals for longer forecasts
        period_factor = 1 + (periods - 1) * 0.1
        width = min(width * period_factor, 0.5)  # Cap at 50%
        
        return width
    
    def _generate_interpretation(
        self,
        growth_rates: list[float],
        forecast_values: list[float]
    ) -> str:
        """Generate Chinese natural language summary of forecast.
        
        Args:
            growth_rates: List of historical growth rates.
            forecast_values: Predicted future values.
        
        Returns:
            Chinese language interpretation string.
        """
        if not forecast_values:
            return "无法生成预测解读"
        
        parts: list[str] = []
        
        # Trend analysis
        if growth_rates:
            avg_growth = sum(growth_rates) / len(growth_rates)
            avg_growth_pct = avg_growth * 100
            
            if avg_growth_pct > 5:
                trend_desc = "呈上升趋势"
            elif avg_growth_pct < -5:
                trend_desc = "呈下降趋势"
            else:
                trend_desc = "相对稳定"
            
            parts.append(f"历史数据{trend_desc}，平均增长率 {avg_growth_pct:.1f}%。")
        else:
            parts.append("历史数据无明显变化趋势。")
        
        # Forecast summary
        if len(forecast_values) >= 2:
            first_val = forecast_values[0]
            last_val = forecast_values[-1]
            
            if last_val > first_val * 1.05:
                parts.append(f"预测显示未来值将上升至 {last_val:.2f}。")
            elif last_val < first_val * 0.95:
                parts.append(f"预测显示未来值将下降至 {last_val:.2f}。")
            else:
                parts.append(f"预测未来值将维持在 {last_val:.2f} 左右。")
        
        # Period info
        parts.append(f"基于 {len(growth_rates) + 1} 个历史数据点进行预测。")
        
        return " ".join(parts)
    
    def _detect_seasonality(
        self,
        data: list[dict[str, Any]],
        values: list[float]
    ) -> tuple[bool, int]:
        """Detect basic seasonality in time series data.
        
        Checks for repeating patterns by comparing values at
        regular intervals.
        
        Args:
            data: List of dictionaries with time data.
            values: List of numeric values.
        
        Returns:
            Tuple of (has_seasonality, detected_period).
        """
        if len(values) < self.MIN_SEASONAL_PERIOD * 2:
            return False, 0
        
        # Try different seasonal periods (2 to min(12, len/2))
        max_period = min(12, len(values) // 2)
        
        best_period = 0
        best_correlation = 0.0
        
        for period in range(2, max_period + 1):
            correlation = self._calculate_lag_correlation(values, period)
            
            if correlation > best_correlation and correlation > 0.5:
                best_correlation = correlation
                best_period = period
        
        return best_period >= self.MIN_SEASONAL_PERIOD, best_period
    
    def _calculate_lag_correlation(
        self,
        values: list[float],
        lag: int
    ) -> float:
        """Calculate correlation between values and their lagged versions.
        
        Args:
            values: List of numeric values.
            lag: Lag period.
        
        Returns:
            Correlation coefficient (-1 to 1).
        """
        if len(values) < lag * 2:
            return 0.0
        
        n = len(values) - lag
        
        # Calculate means
        mean1 = sum(values[:n]) / n
        mean2 = sum(values[lag:lag + n]) / n
        
        # Calculate correlation
        numerator = sum(
            (values[i] - mean1) * (values[i + lag] - mean2)
            for i in range(n)
        )
        
        denom1 = math.sqrt(sum((v - mean1) ** 2 for v in values[:n]))
        denom2 = math.sqrt(sum((v - mean2) ** 2 for v in values[lag:lag + n]))
        
        if denom1 == 0 or denom2 == 0:
            return 0.0
        
        return numerator / (denom1 * denom2)
    
    def _generate_forecast_values(
        self,
        historical_values: list[float],
        smoothed_value: float,
        growth_rates: list[float],
        periods: int
    ) -> list[float]:
        """Generate forecast values for future periods.
        
        Args:
            historical_values: Historical data points.
            smoothed_value: Smoothed current value.
            growth_rates: Calculated growth rates.
            periods: Number of periods to forecast.
        
        Returns:
            List of forecasted values.
        """
        forecast: list[float] = []
        
        # Calculate average growth rate
        if growth_rates:
            avg_growth = sum(growth_rates) / len(growth_rates)
        else:
            avg_growth = 0.0
        
        # Use smoothed value as base
        current_value = smoothed_value
        
        for _ in range(periods):
            # Apply growth rate with dampening
            damped_growth = avg_growth * 0.9  # Dampen to be conservative
            current_value = current_value * (1 + damped_growth)
            forecast.append(current_value)
        
        return forecast
    
    def _generate_forecast_dates(
        self,
        historical_dates: list[Any],
        periods: int
    ) -> list[Any]:
        """Generate dates for forecast periods.
        
        Args:
            historical_dates: Historical date values.
            periods: Number of periods to generate.
        
        Returns:
            List of forecast dates.
        """
        forecast_dates: list[Any] = []
        
        if not historical_dates:
            return forecast_dates
        
        # Try to determine date interval
        last_date = historical_dates[-1]
        interval_days = self._estimate_date_interval(historical_dates)
        
        for i in range(1, periods + 1):
            try:
                if isinstance(last_date, datetime):
                    next_date = last_date + timedelta(days=interval_days * i)
                    forecast_dates.append(next_date.strftime("%Y-%m-%d"))
                elif isinstance(last_date, str):
                    # Try parsing date string
                    try:
                        parsed = datetime.strptime(last_date, "%Y-%m-%d")
                        next_date = parsed + timedelta(days=interval_days * i)
                        forecast_dates.append(next_date.strftime("%Y-%m-%d"))
                    except ValueError:
                        # Use index-based dates
                        forecast_dates.append(f"T+{i}")
                else:
                    # Use generic period notation
                    forecast_dates.append(f"T+{i}")
            except (ValueError, TypeError):
                forecast_dates.append(f"T+{i}")
        
        return forecast_dates
    
    def _estimate_date_interval(self, dates: list[Any]) -> int:
        """Estimate average interval between dates in days.
        
        Args:
            dates: List of date values.
        
        Returns:
            Estimated interval in days (default 30).
        """
        if len(dates) < 2:
            return 30
        
        intervals: list[int] = []
        
        for i in range(1, min(len(dates), 5)):  # Use first few intervals
            try:
                d1 = self._parse_date(dates[i - 1])
                d2 = self._parse_date(dates[i])
                if d1 and d2:
                    intervals.append(abs((d2 - d1).days))
            except (ValueError, TypeError):
                continue
        
        if intervals:
            return max(1, sum(intervals) // len(intervals))
        
        return 30  # Default to monthly
    
    def _parse_date(self, date_val: Any) -> datetime | None:
        """Parse a date value to datetime.
        
        Args:
            date_val: Date value (string or datetime).
        
        Returns:
            Parsed datetime or None if parsing fails.
        """
        if isinstance(date_val, datetime):
            return date_val
        
        if isinstance(date_val, str):
            formats = [
                "%Y-%m-%d",
                "%Y/%m/%d",
                "%Y-%m-%d %H:%M:%S",
                "%Y/%m/%d %H:%M:%S",
                "%Y-%m",
            ]
            for fmt in formats:
                try:
                    return datetime.strptime(date_val, fmt)
                except ValueError:
                    continue
        
        return None
    
    def _constant_forecast(
        self,
        values: list[float],
        dates: list[Any],
        periods: int
    ) -> ForecastResult:
        """Generate forecast for constant (no variance) data.
        
        Args:
            values: Single repeated value.
            dates: Date values.
            periods: Number of periods to forecast.
        
        Returns:
            ForecastResult with constant forecast.
        """
        constant_value = values[0]
        forecast_dates = self._generate_forecast_dates(dates, periods)
        confidence = self.DEFAULT_CONFIDENCE_WIDTH
        
        forecast_points = []
        for date in forecast_dates:
            lower = constant_value * (1 - confidence)
            upper = constant_value * (1 + confidence)
            forecast_points.append(ForecastPoint(
                date=date,
                value=constant_value,
                lower_bound=lower,
                upper_bound=upper
            ))
        
        return ForecastResult(
            forecast_values=forecast_points,
            forecast_dates=forecast_dates,
            confidence_interval=(confidence, confidence),
            interpretation=f"数据保持恒定值 {constant_value:.2f}，预测未来值维持不变。"
        )
    
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
    
    @staticmethod
    def _variance(values: list[float]) -> float:
        """Calculate variance of values.
        
        Args:
            values: List of numeric values.
        
        Returns:
            Variance of the values.
        """
        if len(values) < 2:
            return 0.0
        
        mean = sum(values) / len(values)
        return sum((v - mean) ** 2 for v in values) / len(values)
