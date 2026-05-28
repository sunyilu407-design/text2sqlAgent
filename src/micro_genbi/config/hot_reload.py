"""
Config hot reload module for monitoring configuration file changes.

This module provides a ConfigHotReloader class that watches configuration files
for changes and notifies registered callbacks when modifications are detected.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

import yaml

logger = logging.getLogger(__name__)


class ChangeType(Enum):
    """Types of configuration file changes."""

    MODIFIED = "modified"
    CREATED = "created"
    DELETED = "deleted"


@dataclass(frozen=True)
class ConfigChangeEvent:
    """
    Event representing a configuration file change.

    Attributes:
        file_path: Path to the changed configuration file.
        change_type: Type of change (modified, created, or deleted).
        timestamp: When the change was detected.
    """

    file_path: str
    change_type: ChangeType
    timestamp: datetime


class ConfigValidationError(Exception):
    """Raised when a configuration file fails validation."""

    pass


class ConfigHotReloader:
    """
    Monitors configuration files for changes using polling.

    This class watches specified configuration files and triggers callbacks
    when changes are detected. It uses a background thread with configurable
    polling interval to check for file modifications.

    Args:
        config_paths: List of file paths to watch for changes.

    Example:
        ```python
        reloader = ConfigHotReloader([
            "config.yaml",
            "settings.json"
        ])

        def on_change(event):
            print(f"Config changed: {event.file_path}")

        reloader.register_callback(on_change)
        reloader.start()
        # ... application runs ...
        reloader.stop()
        ```
    """

    SUPPORTED_EXTENSIONS = {".yaml", ".yml", ".json"}

    def __init__(self, config_paths: list[str]) -> None:
        """
        Initialize the config hot reloader.

        Args:
            config_paths: List of paths to configuration files to monitor.
        """
        self._config_paths: list[str] = config_paths
        self._file_mtimes: dict[str, float] = {}
        self._callbacks: list[Callable[[ConfigChangeEvent], None]] = []
        self._stop_event: threading.Event = threading.Event()
        self._watch_thread: Optional[threading.Thread] = None
        self._poll_interval: float = 2.0
        self._lock: threading.Lock = threading.Lock()

        self._initialize_file_tracking()

    def _initialize_file_tracking(self) -> None:
        """Initialize tracking of file modification times for all config paths."""
        for path in self._config_paths:
            mtime = self.get_last_modified(path)
            if mtime is not None:
                self._file_mtimes[path] = mtime
                logger.debug("Tracking %s (mtime: %.3f)", path, mtime)

    def get_last_modified(self, path: str) -> Optional[float]:
        """
        Get the last modification time of a file.

        Args:
            path: Path to the file.

        Returns:
            Modification time as a Unix timestamp, or None if file doesn't exist.
        """
        try:
            if os.path.exists(path):
                return os.path.getmtime(path)
            return None
        except (OSError, PermissionError) as e:
            logger.warning("Failed to get mtime for %s: %s", path, e)
            return None

    def register_callback(self, callback: Callable[[ConfigChangeEvent], None]) -> None:
        """
        Register a callback to be invoked when configuration changes are detected.

        Args:
            callback: A callable that accepts a ConfigChangeEvent parameter.
        """
        with self._lock:
            self._callbacks.append(callback)
        logger.debug("Registered callback: %s", callback.__name__ if hasattr(callback, "__name__") else str(callback))

    def start(self) -> None:
        """
        Start watching for configuration file changes.

        This method spawns a background thread that polls for file changes.
        Calling start() multiple times is safe; subsequent calls are no-ops
        if already running.
        """
        if self._watch_thread is not None and self._watch_thread.is_alive():
            logger.warning("ConfigHotReloader is already running")
            return

        self._stop_event.clear()
        self._watch_thread = threading.Thread(target=self._watch_loop, daemon=True, name="ConfigHotReloader")
        self._watch_thread.start()
        logger.info("ConfigHotReloader started, monitoring %d file(s)", len(self._config_paths))

    def stop(self) -> None:
        """
        Stop watching for configuration file changes.

        This method signals the background thread to stop and waits for it to
        complete. Calling stop() when not running is safe.
        """
        if self._watch_thread is None or not self._watch_thread.is_alive():
            logger.debug("ConfigHotReloader is not running")
            return

        self._stop_event.set()
        self._watch_thread.join(timeout=5.0)
        self._watch_thread = None
        logger.info("ConfigHotReloader stopped")

    def _watch_loop(self) -> None:
        """
        Main polling loop that checks for file changes.

        Continuously polls for file modifications until stop() is called.
        The polling interval is configurable via _poll_interval.
        """
        while not self._stop_event.is_set():
            try:
                if self._should_reload():
                    self._process_changes()
            except Exception as e:
                logger.error("Error in watch loop: %s", e, exc_info=True)

            self._stop_event.wait(timeout=self._poll_interval)

    def _should_reload(self) -> bool:
        """
        Check if any configuration file has changed.

        Returns:
            True if any tracked file has been modified, created, or deleted.
        """
        changes: list[str] = []

        for path in self._config_paths:
            current_mtime = self.get_last_modified(path)
            previous_mtime = self._file_mtimes.get(path)

            if current_mtime is None:
                if previous_mtime is not None:
                    changes.append(path)
            elif previous_mtime is None:
                changes.append(path)
            elif current_mtime > previous_mtime:
                changes.append(path)

        return len(changes) > 0

    def _process_changes(self) -> None:
        """Detect and notify all file changes since last check."""
        changes: list[ConfigChangeEvent] = []

        for path in self._config_paths:
            current_mtime = self.get_last_modified(path)
            previous_mtime = self._file_mtimes.get(path)

            if current_mtime is None and previous_mtime is not None:
                change_type = ChangeType.DELETED
                change_event = ConfigChangeEvent(
                    file_path=path,
                    change_type=change_type,
                    timestamp=datetime.now(),
                )
                changes.append(change_event)
                del self._file_mtimes[path]
                logger.info("Config file deleted: %s", path)

            elif current_mtime is not None and previous_mtime is None:
                if self._validate_config(path):
                    change_type = ChangeType.CREATED
                    change_event = ConfigChangeEvent(
                        file_path=path,
                        change_type=change_type,
                        timestamp=datetime.now(),
                    )
                    changes.append(change_event)
                    self._file_mtimes[path] = current_mtime
                    logger.info("Config file created: %s", path)
                else:
                    logger.warning("Skipping notification for invalid config: %s", path)

            elif current_mtime is not None and previous_mtime is not None:
                if current_mtime > previous_mtime:
                    if self._validate_config(path):
                        change_type = ChangeType.MODIFIED
                        change_event = ConfigChangeEvent(
                            file_path=path,
                            change_type=change_type,
                            timestamp=datetime.now(),
                        )
                        changes.append(change_event)
                        self._file_mtimes[path] = current_mtime
                        logger.info("Config file modified: %s", path)
                    else:
                        logger.warning("Skipping notification for invalid config: %s", path)

        if changes:
            self._notify_changes(changes)

    def _validate_config(self, file_path: str) -> bool:
        """
        Validate a configuration file's syntax.

        Performs basic YAML/JSON validation by attempting to parse the file.
        Only files with .yaml, .yml, or .json extensions are validated.

        Args:
            file_path: Path to the configuration file.

        Returns:
            True if the file is valid or has an unsupported extension.
            False if the file fails to parse.
        """
        path = Path(file_path)

        if not path.exists():
            return True

        ext = path.suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            return True

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            if not content.strip():
                logger.warning("Config file is empty: %s", file_path)
                return False

            if ext in {".yaml", ".yml"}:
                yaml.safe_load(content)
            elif ext == ".json":
                json.loads(content)

            return True

        except yaml.YAMLError as e:
            logger.error("YAML validation failed for %s: %s", file_path, e)
            return False
        except json.JSONDecodeError as e:
            logger.error("JSON validation failed for %s: %s", file_path, e)
            return False
        except OSError as e:
            logger.error("Failed to read config file %s: %s", file_path, e)
            return False

    def _notify_changes(self, changes: list[ConfigChangeEvent]) -> None:
        """
        Notify all registered callbacks of configuration changes.

        Args:
            changes: List of ConfigChangeEvent objects representing detected changes.
        """
        with self._lock:
            callbacks = list(self._callbacks)

        for change in changes:
            for callback in callbacks:
                try:
                    callback(change)
                except Exception as e:
                    logger.error("Callback %s raised exception: %s", callback, e, exc_info=True)

    def _on_config_change(self, file_path: str) -> None:
        """
        Handle a detected configuration change.

        This method is called internally when a configuration file change is detected.
        It validates the config and creates a change event for notification.

        Args:
            file_path: Path to the changed configuration file.
        """
        if self._validate_config(file_path):
            change_event = ConfigChangeEvent(
                file_path=file_path,
                change_type=ChangeType.MODIFIED,
                timestamp=datetime.now(),
            )
            self._notify_changes([change_event])

            current_mtime = self.get_last_modified(file_path)
            if current_mtime is not None:
                self._file_mtimes[file_path] = current_mtime
        else:
            logger.warning("Config file failed validation, skipping change notification: %s", file_path)

    @property
    def poll_interval(self) -> float:
        """Get the current polling interval in seconds."""
        return self._poll_interval

    @poll_interval.setter
    def poll_interval(self, value: float) -> None:
        """
        Set the polling interval.

        Args:
            value: New polling interval in seconds. Must be positive.
        """
        if value <= 0:
            raise ValueError("Poll interval must be positive")
        self._poll_interval = value

    @property
    def is_running(self) -> bool:
        """Check if the reloader is currently running."""
        return self._watch_thread is not None and self._watch_thread.is_alive()
