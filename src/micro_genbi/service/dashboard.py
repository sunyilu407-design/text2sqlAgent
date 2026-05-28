"""
Dashboard Service Module

Manages custom dashboards with widgets (query cards, charts, tables).
Provides thread-safe in-memory storage and auto-layout functionality.
"""

import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4


@dataclass
class WidgetPosition:
    """Position of a widget in the dashboard grid."""
    x: int = 0
    y: int = 0
    w: int = 4  # width in grid columns
    h: int = 2  # height in grid rows


@dataclass
class DashboardWidget:
    """A widget that can be placed on a dashboard."""
    id: str
    type: str  # query_card, chart, table, text
    title: str
    query: str = ""  # SQL or NL question
    chart_type: str = ""  # line, bar, pie, etc.
    position: WidgetPosition = field(default_factory=WidgetPosition)
    refresh_interval: int = 0  # seconds, 0 = no auto-refresh
    config: dict = field(default_factory=dict)

    def __post_init__(self):
        """Validate widget type after initialization."""
        valid_types = ("query_card", "chart", "table", "text")
        if self.type not in valid_types:
            raise ValueError(f"Invalid widget type: {self.type}. Must be one of {valid_types}")


@dataclass
class Dashboard:
    """A dashboard containing multiple widgets."""
    id: str
    user_id: str
    name: str
    description: str
    widgets: list[DashboardWidget] = field(default_factory=list)
    layout: str = "grid"  # grid, freeform
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    is_favorite: bool = False


class DashboardService:
    """
    Service for managing dashboards with widgets.

    Provides thread-safe in-memory storage for dashboards and widgets.
    Supports auto-layout using a 12-column grid system.
    """

    GRID_COLUMNS = 12
    GRID_ROW_HEIGHT = 2

    def __init__(self):
        """Initialize the dashboard service with thread-safe storage."""
        self._dashboards: dict[str, Dashboard] = {}
        self._lock = threading.RLock()

    def create_dashboard(
        self,
        name: str,
        user_id: str,
        description: str = ""
    ) -> str:
        """
        Create a new dashboard.

        Args:
            name: Display name of the dashboard.
            user_id: ID of the user who owns the dashboard.
            description: Optional description of the dashboard.

        Returns:
            The ID of the created dashboard.
        """
        dashboard_id = str(uuid4())
        now = datetime.now()

        dashboard = Dashboard(
            id=dashboard_id,
            user_id=user_id,
            name=name,
            description=description,
            created_at=now,
            updated_at=now
        )

        with self._lock:
            self._dashboards[dashboard_id] = dashboard

        return dashboard_id

    def update_dashboard(
        self,
        dashboard_id: str,
        name: str | None = None,
        description: str | None = None
    ) -> bool:
        """
        Update an existing dashboard's metadata.

        Args:
            dashboard_id: ID of the dashboard to update.
            name: New name for the dashboard (optional).
            description: New description (optional).

        Returns:
            True if the dashboard was updated, False if not found.
        """
        with self._lock:
            dashboard = self._dashboards.get(dashboard_id)
            if not dashboard:
                return False

            if name is not None:
                dashboard.name = name
            if description is not None:
                dashboard.description = description

            dashboard.updated_at = datetime.now()
            return True

    def delete_dashboard(self, dashboard_id: str) -> bool:
        """
        Delete a dashboard and all its widgets.

        Args:
            dashboard_id: ID of the dashboard to delete.

        Returns:
            True if the dashboard was deleted, False if not found.
        """
        with self._lock:
            if dashboard_id not in self._dashboards:
                return False

            del self._dashboards[dashboard_id]
            return True

    def get_dashboard(self, dashboard_id: str) -> Dashboard | None:
        """
        Retrieve a dashboard by its ID.

        Args:
            dashboard_id: ID of the dashboard to retrieve.

        Returns:
            The Dashboard object if found, None otherwise.
        """
        with self._lock:
            return self._dashboards.get(dashboard_id)

    def list_dashboards(self, user_id: str) -> list[Dashboard]:
        """
        List all dashboards owned by a user.

        Args:
            user_id: ID of the user whose dashboards to list.

        Returns:
            List of Dashboard objects owned by the user.
        """
        with self._lock:
            return [
                d for d in self._dashboards.values()
                if d.user_id == user_id
            ]

    def add_widget(
        self,
        dashboard_id: str,
        widget: DashboardWidget
    ) -> str | None:
        """
        Add a widget to a dashboard.

        Args:
            dashboard_id: ID of the dashboard to add the widget to.
            widget: The DashboardWidget to add.

        Returns:
            The widget ID if added successfully, None if dashboard not found.
        """
        with self._lock:
            dashboard = self._dashboards.get(dashboard_id)
            if not dashboard:
                return None

            widget_id = widget.id or str(uuid4())
            widget.id = widget_id

            # Auto-layout if position is default
            if widget.position.x == 0 and widget.position.y == 0:
                positions = self._auto_layout(dashboard.widgets + [widget])
                widget.position = positions[-1]

            dashboard.widgets.append(widget)
            dashboard.updated_at = datetime.now()

            return widget_id

    def update_widget(
        self,
        dashboard_id: str,
        widget_id: str,
        updates: dict[str, Any]
    ) -> bool:
        """
        Update a widget's properties.

        Args:
            dashboard_id: ID of the dashboard containing the widget.
            widget_id: ID of the widget to update.
            updates: Dictionary of properties to update.

        Returns:
            True if the widget was updated, False if not found.
        """
        with self._lock:
            dashboard = self._dashboards.get(dashboard_id)
            if not dashboard:
                return False

            widget = next(
                (w for w in dashboard.widgets if w.id == widget_id),
                None
            )
            if not widget:
                return False

            # Apply updates
            if "title" in updates:
                widget.title = updates["title"]
            if "query" in updates:
                widget.query = updates["query"]
            if "chart_type" in updates:
                widget.chart_type = updates["chart_type"]
            if "refresh_interval" in updates:
                widget.refresh_interval = updates["refresh_interval"]
            if "config" in updates:
                widget.config.update(updates["config"])

            # Handle position update separately
            if "position" in updates:
                pos = updates["position"]
                if isinstance(pos, dict):
                    widget.position = WidgetPosition(
                        x=pos.get("x", widget.position.x),
                        y=pos.get("y", widget.position.y),
                        w=pos.get("w", widget.position.w),
                        h=pos.get("h", widget.position.h)
                    )
                elif isinstance(pos, WidgetPosition):
                    widget.position = pos

            dashboard.updated_at = datetime.now()
            return True

    def remove_widget(self, dashboard_id: str, widget_id: str) -> bool:
        """
        Remove a widget from a dashboard.

        Args:
            dashboard_id: ID of the dashboard containing the widget.
            widget_id: ID of the widget to remove.

        Returns:
            True if the widget was removed, False if not found.
        """
        with self._lock:
            dashboard = self._dashboards.get(dashboard_id)
            if not dashboard:
                return False

            widget = next(
                (w for w in dashboard.widgets if w.id == widget_id),
                None
            )
            if not widget:
                return False

            dashboard.widgets.remove(widget)
            dashboard.updated_at = datetime.now()
            return True

    def refresh_widget(
        self,
        dashboard_id: str,
        widget_id: str,
        ask_service: Any = None
    ) -> dict[str, Any] | None:
        """
        Refresh a widget's data by re-executing its query.

        Args:
            dashboard_id: ID of the dashboard containing the widget.
            widget_id: ID of the widget to refresh.
            ask_service: Optional service to execute queries.

        Returns:
            Dictionary containing the refreshed widget data, or None if not found.
        """
        with self._lock:
            dashboard = self._dashboards.get(dashboard_id)
            if not dashboard:
                return None

            widget = next(
                (w for w in dashboard.widgets if w.id == widget_id),
                None
            )
            if not widget:
                return None

        # Execute query outside lock for thread safety
        result = self._execute_widget_query(widget, ask_service)

        return {
            "widget_id": widget_id,
            "type": widget.type,
            "title": widget.title,
            "data": result,
            "refreshed_at": datetime.now().isoformat()
        }

    def _execute_widget_query(
        self,
        widget: DashboardWidget,
        ask_service: Any = None
    ) -> dict[str, Any]:
        """
        Execute a widget's query and return the result.

        Args:
            widget: The widget whose query to execute.
            ask_service: Service to use for executing queries.

        Returns:
            Dictionary containing the query result.
        """
        if widget.type == "text":
            return {"content": widget.config.get("content", "")}

        if not widget.query:
            return {"error": "No query specified"}

        if widget.type == "query_card":
            if ask_service:
                try:
                    result = ask_service.ask(widget.query)
                    return {
                        "query": widget.query,
                        "result_count": len(result.get("data", [])),
                        "result": result
                    }
                except Exception as e:
                    return {"error": str(e), "query": widget.query}
            return {"query": widget.query, "result_count": 0}

        if widget.type == "chart":
            if ask_service:
                try:
                    result = ask_service.ask(widget.query)
                    return {
                        "query": widget.query,
                        "chart_type": widget.chart_type,
                        "data": result.get("data", [])
                    }
                except Exception as e:
                    return {"error": str(e), "query": widget.query}
            return {"query": widget.query, "chart_type": widget.chart_type, "data": []}

        if widget.type == "table":
            if ask_service:
                try:
                    result = ask_service.ask(widget.query)
                    return {
                        "query": widget.query,
                        "columns": result.get("columns", []),
                        "rows": result.get("data", [])
                    }
                except Exception as e:
                    return {"error": str(e), "query": widget.query}
            return {"query": widget.query, "columns": [], "rows": []}

        return {"error": f"Unknown widget type: {widget.type}"}

    def _auto_layout(self, widgets: list[DashboardWidget]) -> list[WidgetPosition]:
        """
        Calculate positions for widgets using a simple grid layout algorithm.

        Uses a 12-column grid and stacks widgets vertically, wrapping to the
        next row when a widget doesn't fit in the current row.

        Args:
            widgets: List of widgets to layout.

        Returns:
            List of WidgetPosition objects for each widget.
        """
        positions: list[WidgetPosition] = []
        current_x = 0
        current_y = 0
        row_height = self.GRID_ROW_HEIGHT

        for widget in widgets:
            w = widget.position.w if widget.position.w > 0 else 4

            # Check if widget fits in current row
            if current_x + w > self.GRID_COLUMNS:
                current_x = 0
                current_y += row_height

            positions.append(WidgetPosition(
                x=current_x,
                y=current_y,
                w=w,
                h=widget.position.h if widget.position.h > 0 else row_height
            ))

            current_x += w

        return positions

    def _validate_position(
        self,
        x: int,
        y: int,
        w: int,
        h: int
    ) -> bool:
        """
        Validate that a widget position is within grid bounds.

        Args:
            x: X coordinate (column).
            y: Y coordinate (row).
            w: Width in columns.
            h: Height in rows.

        Returns:
            True if the position is valid, False otherwise.
        """
        if x < 0 or y < 0:
            return False
        if w <= 0 or h <= 0:
            return False
        if x + w > self.GRID_COLUMNS:
            return False
        return True

    def toggle_favorite(self, dashboard_id: str) -> bool:
        """
        Toggle the favorite status of a dashboard.

        Args:
            dashboard_id: ID of the dashboard to toggle.

        Returns:
            The new favorite status, or False if dashboard not found.
        """
        with self._lock:
            dashboard = self._dashboards.get(dashboard_id)
            if not dashboard:
                return False

            dashboard.is_favorite = not dashboard.is_favorite
            dashboard.updated_at = datetime.now()
            return dashboard.is_favorite

    def get_widget(self, dashboard_id: str, widget_id: str) -> DashboardWidget | None:
        """
        Retrieve a specific widget from a dashboard.

        Args:
            dashboard_id: ID of the dashboard containing the widget.
            widget_id: ID of the widget to retrieve.

        Returns:
            The DashboardWidget if found, None otherwise.
        """
        with self._lock:
            dashboard = self._dashboards.get(dashboard_id)
            if not dashboard:
                return None

            return next(
                (w for w in dashboard.widgets if w.id == widget_id),
                None
            )

    def reorder_widgets(
        self,
        dashboard_id: str,
        widget_ids: list[str]
    ) -> bool:
        """
        Reorder widgets in a dashboard by providing a new order of widget IDs.

        Args:
            dashboard_id: ID of the dashboard whose widgets to reorder.
            widget_ids: List of widget IDs in the desired order.

        Returns:
            True if reordering was successful, False if dashboard not found.
        """
        with self._lock:
            dashboard = self._dashboards.get(dashboard_id)
            if not dashboard:
                return False

            # Create a mapping of widget_id to widget
            widget_map = {w.id: w for w in dashboard.widgets}

            # Reorder widgets based on provided IDs
            reordered = []
            for wid in widget_ids:
                if wid in widget_map:
                    reordered.append(widget_map[wid])

            # Add any widgets not in the provided list at the end
            for widget in dashboard.widgets:
                if widget.id not in widget_ids:
                    reordered.append(widget)

            dashboard.widgets = reordered
            dashboard.updated_at = datetime.now()
            return True
