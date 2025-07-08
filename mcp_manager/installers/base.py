"""Base installer interface."""

import asyncio
import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict

from ..config.models import ServerConfig


class BaseInstaller(ABC):
    """Base class for MCP server installers."""

    def __init__(self):
        self.base_install_dir = Path.cwd() / "mcp-servers"
        self.base_install_dir.mkdir(exist_ok=True)

    @abstractmethod
    async def install(self, server_id: str, config: ServerConfig) -> Path:
        """Install the MCP server and return installation path."""
        pass

    @abstractmethod
    def get_install_path(self, server_id: str, config: ServerConfig) -> Path:
        """Get the installation path for a server."""
        pass

    @abstractmethod
    def is_installed(self, server_id: str, config: ServerConfig) -> bool:
        """Check if server is already installed."""
        pass

    async def _run_command(
        self, cmd: list[str], cwd: Path = None, env: Dict[str, str] = None
    ) -> tuple[str, str]:
        """Run a command and return stdout, stderr."""
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=env,
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise RuntimeError(
                f"Command failed: {' '.join(cmd)}\nstderr: {stderr.decode()}"
            )

        return stdout.decode(), stderr.decode()

    async def _create_package_json(
        self, install_dir: Path, package_name: str, version: str = None
    ):
        """Create a package.json file."""
        package_json = {
            "name": f"mcp-{package_name.replace('/', '-')}",
            "dependencies": {package_name: version or "latest"},
        }

        with open(install_dir / "package.json", "w") as f:
            json.dump(package_json, f, indent=2)

    async def _npm_install(self, install_dir: Path) -> None:
        """Run npm install in directory."""
        await self._run_command(["npm", "install"], cwd=install_dir)

    async def _pip_install(
        self, install_dir: Path, requirements_file: str = "requirements.txt"
    ) -> None:
        """Run pip install in directory."""
        req_file = install_dir / requirements_file
        if req_file.exists():
            await self._run_command(
                ["pip", "install", "-r", str(req_file)], cwd=install_dir
            )

        # Also try pyproject.toml
        pyproject = install_dir / "pyproject.toml"
        if pyproject.exists():
            await self._run_command(["pip", "install", "-e", "."], cwd=install_dir)
