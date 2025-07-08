"""Local filesystem MCP server installer."""

import logging
import shutil
from pathlib import Path

from ..config.models import ServerConfig
from .base import BaseInstaller

logger = logging.getLogger(__name__)


class LocalInstaller(BaseInstaller):
    """Installer for local filesystem MCP servers."""

    def get_install_path(self, server_id: str, config: ServerConfig) -> Path:
        """Get installation path for local server."""
        _, source_path = config.source.split(":", 1)

        # If it's already an absolute path, use it directly
        source_path_obj = Path(source_path)
        if source_path_obj.is_absolute():
            return source_path_obj

        # Otherwise, treat it as relative to current directory
        return Path.cwd() / source_path

    def is_installed(self, server_id: str, config: ServerConfig) -> bool:
        """Check if local server path exists."""
        install_path = self.get_install_path(server_id, config)
        return install_path.exists()

    async def install(self, server_id: str, config: ServerConfig) -> Path:
        """Install local MCP server (mainly validation)."""
        _, source_path = config.source.split(":", 1)
        source_path_obj = Path(source_path)
        install_path = self.get_install_path(server_id, config)

        logger.info(f"Setting up local MCP server: {source_path}")

        # If source path doesn't exist, raise error
        if not source_path_obj.exists():
            raise FileNotFoundError(f"Local source path does not exist: {source_path}")

        # If source is relative and we need to copy it
        if not source_path_obj.is_absolute():
            # Create a copy in our managed directory
            managed_path = self.base_install_dir / "local" / server_id
            managed_path.mkdir(parents=True, exist_ok=True)

            if source_path_obj.is_file():
                # Copy single file
                shutil.copy2(source_path_obj, managed_path)
                install_path = managed_path / source_path_obj.name
            else:
                # Copy entire directory
                if managed_path.exists():
                    shutil.rmtree(managed_path)
                shutil.copytree(source_path_obj, managed_path)
                install_path = managed_path

        # Install dependencies if needed
        await self._install_dependencies(install_path)

        logger.info(f"Local MCP server {source_path} set up successfully")
        return install_path

    async def _install_dependencies(self, install_path: Path) -> None:
        """Install dependencies for local server."""
        if install_path.is_file():
            # Single file, check if it's in a directory with dependencies
            install_path = install_path.parent

        # Check for Python project
        if (install_path / "requirements.txt").exists() or (
            install_path / "pyproject.toml"
        ).exists():
            logger.info("Installing Python dependencies for local server")
            await self._pip_install(install_path)

        # Check for Node.js project
        elif (install_path / "package.json").exists():
            logger.info("Installing Node.js dependencies for local server")
            await self._npm_install(install_path)
