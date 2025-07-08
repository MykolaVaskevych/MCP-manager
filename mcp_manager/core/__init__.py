"""Core MCP Manager application."""

from .config_watcher import ConfigWatcher
from .manager import MCPManager

__all__ = ["MCPManager", "ConfigWatcher"]
