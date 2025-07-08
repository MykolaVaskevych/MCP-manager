"""GitHub-based MCP server installer."""

import logging
from pathlib import Path

from ..config.models import ServerConfig
from .base import BaseInstaller

logger = logging.getLogger(__name__)


class GitHubInstaller(BaseInstaller):
    """Installer for GitHub-based MCP servers."""

    def get_install_path(self, server_id: str, config: ServerConfig) -> Path:
        """Get installation path for GitHub repository."""
        _, repo_path = config.source.split(":", 1)
        safe_name = repo_path.replace("/", "-")
        return self.base_install_dir / "github" / safe_name

    def is_installed(self, server_id: str, config: ServerConfig) -> bool:
        """Check if GitHub repository is cloned."""
        install_path = self.get_install_path(server_id, config)
        git_dir = install_path / ".git"
        return install_path.exists() and git_dir.exists()

    async def install(self, server_id: str, config: ServerConfig) -> Path:
        """Install GitHub-based MCP server."""
        _, repo_path = config.source.split(":", 1)
        install_path = self.get_install_path(server_id, config)

        logger.info(f"Installing GitHub repository: {repo_path}")

        try:
            # Clone repository
            repo_url = f"https://github.com/{repo_path}.git"
            clone_cmd = ["git", "clone", repo_url, str(install_path)]

            if config.branch:
                clone_cmd.extend(["--branch", config.branch])

            await self._run_command(clone_cmd)

            # Switch to specific branch if needed
            if config.branch and config.branch != "main":
                await self._run_command(
                    ["git", "checkout", config.branch], cwd=install_path
                )

            # Install dependencies based on project type
            await self._install_dependencies(install_path)

            logger.info(f"GitHub repository {repo_path} installed successfully")
            return install_path

        except Exception as e:
            logger.error(f"Failed to install GitHub repository {repo_path}: {e}")
            # Clean up on failure
            if install_path.exists():
                await self._cleanup_directory(install_path)
            raise

    async def _install_dependencies(self, install_path: Path) -> None:
        """Install dependencies based on project files."""
        # Check for Node.js project
        if (install_path / "package.json").exists():
            logger.info("Detected Node.js project, running npm install")
            await self._npm_install(install_path)

        # Check for Python project
        elif (install_path / "requirements.txt").exists() or (
            install_path / "pyproject.toml"
        ).exists():
            logger.info("Detected Python project, installing dependencies")
            await self._pip_install(install_path)

        # Check for other project types
        elif (install_path / "Cargo.toml").exists():
            logger.info("Detected Rust project, running cargo build")
            await self._run_command(["cargo", "build", "--release"], cwd=install_path)

        elif (install_path / "go.mod").exists():
            logger.info("Detected Go project, running go build")
            await self._run_command(["go", "build"], cwd=install_path)

        else:
            logger.warning(
                f"Unknown project type in {install_path}, skipping dependency installation"
            )

    async def _cleanup_directory(self, directory: Path) -> None:
        """Clean up installation directory."""
        try:
            await self._run_command(["rm", "-rf", str(directory)])
        except Exception as e:
            logger.warning(f"Failed to cleanup directory {directory}: {e}")
