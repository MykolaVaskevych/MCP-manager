"""Configuration file watcher for hot reloading."""

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .manager import MCPManager

logger = logging.getLogger(__name__)


class ConfigWatcher:
    """Watches configuration file for changes and triggers reloads."""

    def __init__(self, config_path: str, manager: "MCPManager"):
        self.config_path = Path(config_path)
        self.manager = manager
        self.last_modified = 0
        self.watch_task: asyncio.Task = None
        self.running = False

    async def start_watching(self) -> None:
        """Start watching configuration file for changes."""
        if self.running:
            return

        self.running = True
        logger.info(f"Starting config file watcher for: {self.config_path}")

        # Initialize last modified time
        if self.config_path.exists():
            self.last_modified = self.config_path.stat().st_mtime

        while self.running:
            try:
                await self._check_for_changes()
                await asyncio.sleep(1)  # Check every second
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in config watcher: {e}")
                await asyncio.sleep(5)  # Wait longer on error

    async def stop(self) -> None:
        """Stop watching configuration file."""
        self.running = False
        if self.watch_task:
            self.watch_task.cancel()
            try:
                await self.watch_task
            except asyncio.CancelledError:
                pass

    async def _check_for_changes(self) -> None:
        """Check if configuration file has been modified."""
        if not self.config_path.exists():
            return

        try:
            current_modified = self.config_path.stat().st_mtime

            if current_modified > self.last_modified:
                logger.info("Configuration file changed, reloading...")
                await self._reload_config()
                self.last_modified = current_modified

        except Exception as e:
            logger.error(f"Error checking config file modification: {e}")

    async def _reload_config(self) -> None:
        """Reload configuration and apply changes."""
        try:
            # Validate new configuration before applying
            issues = self.manager.config_manager.validate_config()
            if issues:
                logger.error("New configuration has validation issues:")
                for issue in issues:
                    logger.error(f"  - {issue}")
                logger.error("Configuration reload skipped due to validation errors")
                return

            # Apply configuration changes
            await self.manager.reload_config()

            logger.info("Configuration reloaded successfully")

        except Exception as e:
            logger.error(f"Failed to reload configuration: {e}")
            # Don't re-raise to keep watcher running
