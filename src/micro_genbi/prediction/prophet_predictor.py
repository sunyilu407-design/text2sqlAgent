"""Time series forecasting module using Facebook Prophet.

Provides advanced forecasting capabilities with:
- Trend and seasonality decomposition
- Confidence intervals
- Holiday effects
- Model evaluation metrics (MAPE, RMSE, R²)

Note:
    This module is optional. If Prophet is not installed,
    import will raise an ImportError with helpful guidance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

try:
    from prophet import Prophet
    PROPHET_AVAILABLE = True
except ImportError:
    Prophet = None  # type: ignore
    PROPHET_AVAILABLE = False


@dataclass
class ProphetForecastPoint:
    """Represents a single Prophet forecast data point."""
    ds: Any
    yhat: float
    yhat_lower: float
    yhat_upper: float


@dataclass
class ProphetMetrics:
    """Evaluation metrics for Prophet model."""
    mape: float = 0.0
    rmse: float = 0.0
    r_squared: float = 0.0


@dataclass
class ProphetComponents:
    """Decomposed components from Prophet model."""
    trend: list[dict[str, Any]] = field(default_factory=list)
    seasonality: list[dict[str, Any]] = field(default_factory=list)
    holidays: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ForecastResult:
    """Result of Prophet-based time series forecasting.
    
    Attributes:
        model: The fitted Prophet model (or None if unavailable).
        forecast_values: List of forecast points with predictions and intervals.
        metrics: Model evaluation metrics (MAPE, RMSE, R²).
        components: Decomposed trend/seasonality/holiday components.
        interpretation: Chinese natural language summary.
    """
    model: Any = None
    forecast_values: list[ProphetForecastPoint] = field(default_factory=list)
    metrics: ProphetMetrics = field(default_factory=ProphetMetrics)
    components: ProphetComponents = field(default_factory=ProphetComponents)
    interpretation: str = ""


class ProphetPredictor:
    """Advanced time series forecasting using Facebook Prophet.
    
    Prophet is a procedure for forecasting time series data based on an
    additive model where non-linear trends are fit with yearly, weekly,
    and daily seasonality, plus holiday effects.
    
    Args:
        api_key: Optional Prophet API key (for Prophet enterprise features).
            Most features work without an API key.
    
    Example:
        >>> predictor = ProphetPredictor()
        >>> data = [
        ...     {"date": "2024-01-01", "value": 100},
        ...     {"date": "2024-02-01", "value": 120},
        ...     {"date": "2024-03-01", "value": 115},
        ... ]
        >>> result = predictor.forecast(data, "date", "value", periods=3)
        >>> print(result.interpretation)
    """
    
    # Configuration defaults
    DEFAULT_PERIODS = 3
    MIN_DATA_POINTS = 5
    DEFAULT_SEASONALITY_MODE = "multiplicative"
    
    # Seasonality configuration
    DEFAULT_YEARLY_SEASONALITY = True
    DEFAULT_WEEKLY_SEASONALITY = True
    DEFAULT_DAILY_SEASONALITY = False
    
    def __init__(
        self,
        api_key: str = "",
        yearly_seasonality: bool | None = None,
        weekly_seasonality: bool | None = None,
        daily_seasonality: bool | None = None,
        seasonality_mode: str = "multiplicative"
    ) -> None:
        """Initialize Prophet predictor with configuration.
        
        Args:
            api_key: Optional API key for Prophet enterprise.
            yearly_seasonality: Enable yearly seasonality (default True).
            weekly_seasonality: Enable weekly seasonality (default True).
            daily_seasonality: Enable daily seasonality (default False).
            seasonality_mode: Seasonality mode - "additive" or "multiplicative".
        """
        if not PROPHET_AVAILABLE:
            raise ImportError(
                "Prophet is not installed. Install it with:\n"
                "    pip install prophet\n"
                "Or install the optional dependencies:\n"
                "    pip install micro-genbi[prediction]\n"
            )
        
        self.api_key = api_key
        self.yearly_seasonality = (
            yearly_seasonality 
            if yearly_seasonality is not None 
            else self.DEFAULT_YEARLY_SEASONALITY
        )
        self.weekly_seasonality = (
            weekly_seasonality 
            if weekly_seasonality is not None 
            else self.DEFAULT_WEEKLY_SEASONALITY
        )
        self.daily_seasonality = (
            daily_seasonality 
            if daily_seasonality is not None 
            else self.DEFAULT_DAILY_SEASONALITY
        )
        self.seasonality_mode = seasonality_mode
        
        self._model: Prophet | None = None
        self._fitted_df: Any = None
    
    def forecast(
        self,
        data: list[dict[str, Any]],
        time_col: str,
        value_col: str,
        periods: int = DEFAULT_PERIODS,
        config: dict[str, Any] | None = None
    ) -> ForecastResult:
        """Generate forecast for the specified time series.
        
        Args:
            data: List of dictionaries with time and value columns.
            time_col: Name of the time/date column.
            value_col: Name of the value column to forecast.
            periods: Number of future periods to forecast (default 3).
            config: Optional configuration overrides for seasonality settings.
        
        Returns:
            ForecastResult with forecast values, metrics, components,
            and Chinese natural language interpretation.
        
        Raises:
            ImportError: If Prophet is not installed.
            ValueError: If data is insufficient or invalid.
        """
        if not PROPHET_AVAILABLE:
            raise ImportError(
                "Prophet is not installed. Install it with: pip install prophet"
            )
        
        if not data or len(data) < self.MIN_DATA_POINTS:
            return ForecastResult(
                interpretation=f"错误：数据点不足，至少需要 {self.MIN_DATA_POINTS} 个数据点"
            )
        
        config = config or {}
        
        # Merge config with instance settings
        yearly = config.get("yearly_seasonality", self.yearly_seasonality)
        weekly = config.get("weekly_seasonality", self.weekly_seasonality)
        daily = config.get("daily_seasonality", self.daily_seasonality)
        mode = config.get("seasonality_mode", self.seasonality_mode)
        
        # Prepare dataframe
        df = self._prepare_dataframe(data, time_col, value_col)
        if df is None:
            return ForecastResult(interpretation="错误：无法解析时间列或值列数据")
        
        # Build and fit model
        self._model = self._build_model(yearly, weekly, daily, mode)
        self._fitted_df = self._fit_model(df, periods)
        
        # Extract forecast
        forecast_df = self._extract_forecast(self._model, df)
        
        # Evaluate model
        metrics = self._evaluate_model(df, forecast_df)
        
        # Detect components
        components = self._detect_components(self._model)
        
        # Build result
        forecast_values = self._build_forecast_points(forecast_df)
        interpretation = self.interpret(ForecastResult(
            model=self._model,
            forecast_values=forecast_values,
            metrics=metrics,
            components=components
        ))
        
        return ForecastResult(
            model=self._model,
            forecast_values=forecast_values,
            metrics=metrics,
            components=components,
            interpretation=interpretation
        )
    
    def _prepare_dataframe(
        self,
        data: list[dict[str, Any]],
        time_col: str,
        value_col: str
    ) -> Any:
        """Convert input data to Prophet-compatible DataFrame.
        
        Prophet requires columns named 'ds' (datestamp) and 'y' (value).
        
        Args:
            data: List of dictionaries with time and value columns.
            time_col: Name of the time/date column.
            value_col: Name of the value column.
        
        Returns:
            pandas DataFrame with 'ds' and 'y' columns, or None if conversion fails.
        """
        import pandas as pd
        
        records: list[dict[str, Any]] = []
        
        for row in data:
            if time_col not in row or value_col not in row:
                continue
            
            ds_value = row[time_col]
            y_value = row[value_col]
            
            if not self._is_numeric(y_value):
                continue
            
            parsed_ds = self._parse_datetime(ds_value)
            if parsed_ds is None:
                continue
            
            records.append({
                "ds": parsed_ds,
                "y": float(y_value)
            })
        
        if len(records) < self.MIN_DATA_POINTS:
            return None
        
        return pd.DataFrame(records)
    
    def _build_model(
        self,
        yearly_seasonality: bool,
        weekly_seasonality: bool,
        daily_seasonality: bool,
        seasonality_mode: str
    ) -> Prophet:
        """Create Prophet model with specified configuration.
        
        Args:
            yearly_seasonality: Enable yearly seasonality.
            weekly_seasonality: Enable weekly seasonality.
            daily_seasonality: Enable daily seasonality.
            seasonality_mode: "additive" or "multiplicative".
        
        Returns:
            Configured Prophet model instance.
        """
        model = Prophet(
            yearly_seasonality=yearly_seasonality,
            weekly_seasonality=weekly_seasonality,
            daily_seasonality=daily_seasonality,
            seasonality_mode=seasonality_mode
        )
        
        if self.api_key:
            model.api_key = self.api_key
        
        return model
    
    def _fit_model(self, df: Any, periods: int) -> Any:
        """Fit Prophet model to the data.
        
        Args:
            df: pandas DataFrame with 'ds' and 'y' columns.
            periods: Number of future periods to forecast.
        
        Returns:
            DataFrame with future dates for prediction.
        """
        self._model.fit(df)
        future = self._model.make_future_dataframe(periods=periods)
        return future
    
    def _extract_forecast(self, model: Prophet, df: Any) -> Any:
        """Extract forecast values and confidence intervals.
        
        Args:
            model: Fitted Prophet model.
            df: Future dates DataFrame.
        
        Returns:
            Forecast DataFrame with yhat, yhat_lower, yhat_upper columns.
        """
        return model.predict(df)
    
    def _evaluate_model(self, actual_df: Any, forecast_df: Any) -> ProphetMetrics:
        """Compute evaluation metrics for the model.
        
        Calculates:
        - MAPE: Mean Absolute Percentage Error
        - RMSE: Root Mean Squared Error
        - R²: Coefficient of determination
        
        Args:
            actual_df: DataFrame with actual values.
            forecast_df: DataFrame with predicted values.
        
        Returns:
            ProphetMetrics with computed values.
        """
        import numpy as np
        
        actual_values = actual_df["y"].values
        n_actual = len(actual_values)
        
        if n_actual == 0:
            return ProphetMetrics()
        
        start_idx = len(forecast_df) - n_actual
        end_idx = len(forecast_df)
        predicted_values = forecast_df["yhat"].iloc[start_idx:end_idx].values
        
        if len(predicted_values) != len(actual_values):
            return ProphetMetrics()
        
        # MAPE calculation
        mask = actual_values != 0
        if np.any(mask):
            mape = np.mean(np.abs((actual_values[mask] - predicted_values[mask]) / actual_values[mask])) * 100
        else:
            mape = 0.0
        
        # RMSE calculation
        mse = np.mean((actual_values - predicted_values) ** 2)
        rmse = np.sqrt(mse)
        
        # R² calculation
        ss_res = np.sum((actual_values - predicted_values) ** 2)
        ss_tot = np.sum((actual_values - np.mean(actual_values)) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0.0
        
        return ProphetMetrics(
            mape=round(mape, 2),
            rmse=round(rmse, 2),
            r_squared=round(r_squared, 4)
        )
    
    def _detect_components(self, model: Prophet) -> ProphetComponents:
        """Extract trend and seasonality components from model.
        
        Args:
            model: Fitted Prophet model.
        
        Returns:
            ProphetComponents with trend, seasonality, and holiday data.
        """
        import pandas as pd
        
        components = ProphetComponents()
        
        # Get trend component
        trend = model.plot_components(model.predict(model.make_future_dataframe(periods=0)))
        if hasattr(trend, "to_dict"):
            pass
        
        # Extract from model
        if hasattr(model, "trend") and model.trend is not None:
            trend_data = model.trend
            if hasattr(trend_data, "values"):
                trend_data = trend_data.values
            
            if hasattr(trend_data, "__iter__"):
                trend_values = list(trend_data)
                if len(trend_values) > 0:
                    first_val = float(trend_values[0])
                    last_val = float(trend_values[-1])
                    components.trend.append({
                        "direction": "increasing" if last_val > first_val else "decreasing",
                        "change_pct": round((last_val - first_val) / first_val * 100, 2) if first_val != 0 else 0,
                        "start_value": round(first_val, 2),
                        "end_value": round(last_val, 2)
                    })
        
        # Detect seasonality patterns
        seasonality_names = []
        if self.yearly_seasonality:
            seasonality_names.append("yearly")
        if self.weekly_seasonality:
            seasonality_names.append("weekly")
        if self.daily_seasonality:
            seasonality_names.append("daily")
        
        for name in seasonality_names:
            components.seasonality.append({
                "type": name,
                "enabled": True
            })
        
        # Handle holidays if present
        if hasattr(model, "holidays") and model.holidays is not None:
            if isinstance(model.holidays, pd.DataFrame) and len(model.holidays) > 0:
                for _, holiday in model.holidays.iterrows():
                    if "holiday" in holiday:
                        components.holidays.append({
                            "name": str(holiday["holiday"]),
                            "lower_window": int(holiday.get("lower_window", 0)),
                            "upper_window": int(holiday.get("upper_window", 0))
                        })
        
        return components
    
    def _build_forecast_points(self, forecast_df: Any) -> list[ProphetForecastPoint]:
        """Build list of forecast points from forecast DataFrame.
        
        Args:
            forecast_df: Prophet forecast DataFrame.
        
        Returns:
            List of ProphetForecastPoint objects.
        """
        forecast_points: list[ProphetForecastPoint] = []
        
        for _, row in forecast_df.iterrows():
            forecast_points.append(ProphetForecastPoint(
                ds=row["ds"],
                yhat=round(float(row["yhat"]), 2),
                yhat_lower=round(float(row["yhat_lower"]), 2),
                yhat_upper=round(float(row["yhat_upper"]), 2)
            ))
        
        return forecast_points
    
    def interpret(self, forecast_result: ForecastResult) -> str:
        """Generate Chinese natural language summary of forecast.
        
        Args:
            forecast_result: The forecast result to interpret.
        
        Returns:
            Chinese language interpretation string.
        """
        parts: list[str] = []
        
        # Model info
        parts.append("【Prophet 预测分析】")
        
        # Trend analysis
        if forecast_result.components.trend:
            trend_info = forecast_result.components.trend[0]
            direction = trend_info.get("direction", "unknown")
            
            if direction == "increasing":
                parts.append(f"数据显示明显上升趋势，增幅约 {trend_info.get('change_pct', 0):.1f}%。")
            elif direction == "decreasing":
                parts.append(f"数据显示下降趋势，降幅约 {abs(trend_info.get('change_pct', 0)):.1f}%。")
            else:
                parts.append("数据趋势相对平稳。")
        
        # Seasonality
        if forecast_result.components.seasonality:
            season_types = [s.get("type", "") for s in forecast_result.components.seasonality]
            if season_types:
                parts.append(f"检测到 {', '.join(season_types)} 季节性模式。")
        
        # Metrics
        metrics = forecast_result.metrics
        if metrics.mape > 0 or metrics.rmse > 0:
            parts.append(f"模型评估：MAPE {metrics.mape:.1f}%，RMSE {metrics.rmse:.2f}。")
            
            if metrics.r_squared > 0.7:
                parts.append("模型拟合度较高 (R² > 0.7)。")
            elif metrics.r_squared > 0.4:
                parts.append("模型拟合度中等 (R² 0.4-0.7)。")
            else:
                parts.append("模型拟合度较低，建议补充更多历史数据。")
        
        # Forecast summary
        if forecast_result.forecast_values:
            forecast_values = forecast_result.forecast_values
            last_forecast = forecast_values[-1]
            
            parts.append(
                f"未来预测：{last_forecast.yhat:.2f} "
                f"(置信区间: {last_forecast.yhat_lower:.2f} - {last_forecast.yhat_upper:.2f})"
            )
        
        return " ".join(parts)
    
    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        """Parse various datetime formats to datetime object.
        
        Args:
            value: Date value to parse.
        
        Returns:
            Parsed datetime or None if parsing fails.
        """
        if isinstance(value, datetime):
            return value
        
        if isinstance(value, str):
            formats = [
                "%Y-%m-%d",
                "%Y/%m/%d",
                "%Y-%m-%d %H:%M:%S",
                "%Y/%m/%d %H:%M:%S",
                "%Y-%m-%d %H:%M",
                "%Y-%m",
                "%Y%m%d",
            ]
            for fmt in formats:
                try:
                    return datetime.strptime(value, fmt)
                except ValueError:
                    continue
        
        if hasattr(value, "to_pydatetime"):
            return value.to_pydatetime()
        
        return None
    
    @staticmethod
    def _is_numeric(value: Any) -> bool:
        """Check if a value is numeric.
        
        Args:
            value: Value to check.
        
        Returns:
            True if value is int or float (excluding bool).
        """
        if isinstance(value, bool):
            return False
        return isinstance(value, (int, float))
    
    @staticmethod
    def is_available() -> bool:
        """Check if Prophet is available in the environment.
        
        Returns:
            True if Prophet can be imported, False otherwise.
        """
        return PROPHET_AVAILABLE
