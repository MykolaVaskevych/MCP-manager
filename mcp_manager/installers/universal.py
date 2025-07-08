"""Universal installer system supporting all source types."""

import asyncio
import logging
import shutil
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import urlparse

from ..config.models import ServerConfig

logger = logging.getLogger(__name__)


class InstallationError(Exception):
    """Raised when installation fails."""

    pass


class BaseInstaller(ABC):
    """Base class for all installers."""

    def __init__(self, base_install_dir: Path):
        self.base_install_dir = base_install_dir

    @abstractmethod
    async def install(self, server_id: str, config: ServerConfig) -> Path:
        """Install the server and return the installation path."""
        pass

    @abstractmethod
    def get_install_path(self, server_id: str, config: ServerConfig) -> Path:
        """Get the path where the server would be installed."""
        pass

    @abstractmethod
    def is_installed(self, server_id: str, config: ServerConfig) -> bool:
        """Check if the server is already installed."""
        pass

    async def _run_command(
        self, cmd: list, cwd: Optional[Path] = None, env: Optional[Dict] = None
    ) -> subprocess.CompletedProcess:
        """Run a command asynchronously."""
        logger.debug(f"Running command: {' '.join(cmd)} in {cwd}")

        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error_msg = f"Command failed: {' '.join(cmd)}\nStdout: {stdout.decode()}\nStderr: {stderr.decode()}"
            logger.error(error_msg)
            raise InstallationError(error_msg)

        return subprocess.CompletedProcess(
            args=cmd, returncode=process.returncode, stdout=stdout, stderr=stderr
        )


class NPMInstaller(BaseInstaller):
    """Installer for NPM packages."""

    def get_install_path(self, server_id: str, config: ServerConfig) -> Path:
        package_name = config.source.split(":", 1)[1]
        safe_name = package_name.replace("@", "").replace("/", "-")
        return self.base_install_dir / "npm" / f"{safe_name}"

    def is_installed(self, server_id: str, config: ServerConfig) -> bool:
        install_path = self.get_install_path(server_id, config)
        package_json = install_path / "package.json"
        return package_json.exists()

    async def install(self, server_id: str, config: ServerConfig) -> Path:
        package_name = config.source.split(":", 1)[1]
        install_path = self.get_install_path(server_id, config)

        logger.info(f"Installing NPM package: {package_name}")

        # Create installation directory
        install_path.mkdir(parents=True, exist_ok=True)

        # Create package.json
        package_json_content = {
            "name": f"mcp-manager-{server_id}",
            "version": "1.0.0",
            "dependencies": {package_name: config.version or "latest"},
        }

        import json

        with open(install_path / "package.json", "w") as f:
            json.dump(package_json_content, f, indent=2)

        # Install package
        await self._run_command(["npm", "install"], cwd=install_path)

        logger.info(f"NPM package {package_name} installed successfully")
        return install_path


class PipInstaller(BaseInstaller):
    """Installer for Python packages via pip."""

    def get_install_path(self, server_id: str, config: ServerConfig) -> Path:
        package_name = config.source.split(":", 1)[1]
        safe_name = package_name.replace("/", "-").replace("_", "-")
        return self.base_install_dir / "pip" / safe_name

    def is_installed(self, server_id: str, config: ServerConfig) -> bool:
        install_path = self.get_install_path(server_id, config)
        return install_path.exists() and any(install_path.iterdir())

    async def install(self, server_id: str, config: ServerConfig) -> Path:
        package_name = config.source.split(":", 1)[1]
        install_path = self.get_install_path(server_id, config)

        logger.info(f"Installing pip package: {package_name}")

        # Create installation directory
        install_path.mkdir(parents=True, exist_ok=True)

        # Install package with pip
        version_spec = (
            f"{package_name}=={config.version}" if config.version else package_name
        )
        await self._run_command(
            [
                "pip",
                "install",
                "--target",
                str(install_path),
                "--no-deps",  # We'll handle deps separately if needed
                version_spec,
            ]
        )

        logger.info(f"Pip package {package_name} installed successfully")
        return install_path


class UvxInstaller(BaseInstaller):
    """Universal runner for uvx packages - no installation needed."""

    def get_install_path(self, server_id: str, config: ServerConfig) -> Path:
        # UVX doesn't install - it runs directly
        # Return a placeholder path for compatibility
        package_name = config.source.split(":", 1)[1]
        safe_name = package_name.replace("/", "-").replace("@", "")
        return self.base_install_dir / "uvx" / safe_name

    def is_installed(self, server_id: str, config: ServerConfig) -> bool:
        # UVX packages are "always installed" - uvx runs them on-demand
        return True

    async def install(self, server_id: str, config: ServerConfig) -> Path:
        package_name = config.source.split(":", 1)[1]
        install_path = self.get_install_path(server_id, config)

        logger.info(f"UVX package ready: {package_name} (no installation needed)")

        # Create placeholder directory for reference
        install_path.mkdir(parents=True, exist_ok=True)

        # Create a marker file with the package name for reference
        marker_file = install_path / "package_name.txt"
        with open(marker_file, "w") as f:
            f.write(package_name)

        logger.info(f"UVX package {package_name} ready for execution")
        return install_path


class GitHubInstaller(BaseInstaller):
    """Installer for GitHub repositories."""

    def get_install_path(self, server_id: str, config: ServerConfig) -> Path:
        repo_path = config.source.split(":", 1)[1]
        safe_name = repo_path.replace("/", "-")
        return self.base_install_dir / "github" / safe_name

    def is_installed(self, server_id: str, config: ServerConfig) -> bool:
        install_path = self.get_install_path(server_id, config)
        return (install_path / ".git").exists()

    async def install(self, server_id: str, config: ServerConfig) -> Path:
        repo_path = config.source.split(":", 1)[1]
        install_path = self.get_install_path(server_id, config)

        logger.info(f"Installing GitHub repository: {repo_path}")

        # Remove existing installation
        if install_path.exists():
            shutil.rmtree(install_path)

        # Clone repository
        repo_url = f"https://github.com/{repo_path}.git"
        clone_cmd = ["git", "clone", repo_url, str(install_path)]

        if hasattr(config, "branch") and config.branch:
            clone_cmd.extend(["--branch", config.branch])

        await self._run_command(clone_cmd)

        # Install dependencies based on project type
        await self._install_dependencies(install_path)

        logger.info(f"GitHub repository {repo_path} installed successfully")
        return install_path

    async def _install_dependencies(self, install_path: Path):
        """Install dependencies based on project type."""
        if (install_path / "package.json").exists():
            logger.info("Installing Node.js dependencies")
            await self._run_command(["npm", "install"], cwd=install_path)
        elif (install_path / "pyproject.toml").exists():
            logger.info("Installing Python dependencies")
            await self._run_command(["pip", "install", "-e", "."], cwd=install_path)
        elif (install_path / "requirements.txt").exists():
            logger.info("Installing Python requirements")
            await self._run_command(
                ["pip", "install", "-r", "requirements.txt"], cwd=install_path
            )
        elif (install_path / "Cargo.toml").exists():
            logger.info("Building Rust project")
            await self._run_command(["cargo", "build", "--release"], cwd=install_path)
        elif (install_path / "go.mod").exists():
            logger.info("Building Go project")
            await self._run_command(["go", "build"], cwd=install_path)


class LocalInstaller(BaseInstaller):
    """Installer for local filesystem paths."""

    def get_install_path(self, server_id: str, config: ServerConfig) -> Path:
        source_path = Path(config.source.split(":", 1)[1])

        if source_path.is_absolute():
            # For absolute paths, return them directly
            return source_path
        else:
            # For relative paths, copy to managed directory
            return self.base_install_dir / "local" / server_id

    def is_installed(self, server_id: str, config: ServerConfig) -> bool:
        install_path = self.get_install_path(server_id, config)
        return install_path.exists()

    async def install(self, server_id: str, config: ServerConfig) -> Path:
        source_path = Path(config.source.split(":", 1)[1])
        install_path = self.get_install_path(server_id, config)

        logger.info(f"Installing local server: {source_path}")

        if not source_path.exists():
            raise InstallationError(f"Local source path does not exist: {source_path}")

        if source_path.is_absolute():
            # Absolute paths are used in place
            logger.info(f"Using local server in place: {source_path}")
            return source_path
        else:
            # Copy relative paths to managed directory
            if install_path.exists():
                shutil.rmtree(install_path)

            if source_path.is_file():
                install_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, install_path)
            else:
                shutil.copytree(source_path, install_path)

            # Install dependencies if needed
            await self._install_dependencies(install_path)

            logger.info(f"Local server installed to: {install_path}")
            return install_path

    async def _install_dependencies(self, install_path: Path):
        """Install dependencies for local servers."""
        # Same logic as GitHub installer
        if (install_path / "package.json").exists():
            await self._run_command(["npm", "install"], cwd=install_path)
        elif (install_path / "pyproject.toml").exists():
            await self._run_command(["pip", "install", "-e", "."], cwd=install_path)
        elif (install_path / "requirements.txt").exists():
            await self._run_command(
                ["pip", "install", "-r", "requirements.txt"], cwd=install_path
            )


class BinaryInstaller(BaseInstaller):
    """Installer for pre-compiled binaries."""

    def get_install_path(self, server_id: str, config: ServerConfig) -> Path:
        return self.base_install_dir / "binary" / server_id

    def is_installed(self, server_id: str, config: ServerConfig) -> bool:
        install_path = self.get_install_path(server_id, config)
        return install_path.exists() and any(
            f.is_file() and f.stat().st_mode & 0o111  # Executable
            for f in install_path.iterdir()
        )

    async def install(self, server_id: str, config: ServerConfig) -> Path:
        binary_url = config.source.split(":", 1)[1]
        install_path = self.get_install_path(server_id, config)

        logger.info(f"Installing binary: {binary_url}")

        # Create installation directory
        install_path.mkdir(parents=True, exist_ok=True)

        # Download binary
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.get(binary_url)
            response.raise_for_status()

            # Determine filename from URL or Content-Disposition
            filename = Path(urlparse(binary_url).path).name or f"{server_id}-server"
            binary_path = install_path / filename

            with open(binary_path, "wb") as f:
                f.write(response.content)

            # Make executable
            binary_path.chmod(0o755)

        logger.info(f"Binary installed to: {binary_path}")
        return install_path


class UniversalInstaller:
    """Universal installer that routes to specific installers based on source type."""

    def __init__(self, base_install_dir: Path):
        self.base_install_dir = base_install_dir
        self.installers = {
            "npm": NPMInstaller(base_install_dir),
            "pip": PipInstaller(base_install_dir),
            "uvx": UvxInstaller(base_install_dir),
            "github": GitHubInstaller(base_install_dir),
            "local": LocalInstaller(base_install_dir),
            "binary": BinaryInstaller(base_install_dir),
            "http": BinaryInstaller(base_install_dir),  # HTTP URLs treated as binaries
            "https": BinaryInstaller(
                base_install_dir
            ),  # HTTPS URLs treated as binaries
        }

    def get_installer(self, source: str) -> BaseInstaller:
        """Get the appropriate installer for a source."""
        if "://" in source:
            # URL format: https://example.com/binary
            scheme = source.split("://", 1)[0]
        else:
            # Prefix format: npm:package, github:user/repo, etc.
            scheme = source.split(":", 1)[0]

        installer = self.installers.get(scheme)
        if not installer:
            raise InstallationError(f"Unsupported source type: {scheme}")

        return installer

    async def install(self, server_id: str, config: ServerConfig) -> Path:
        """Install a server using the appropriate installer."""
        installer = self.get_installer(config.source)
        return await installer.install(server_id, config)

    def is_installed(self, server_id: str, config: ServerConfig) -> bool:
        """Check if a server is already installed."""
        try:
            installer = self.get_installer(config.source)
            return installer.is_installed(server_id, config)
        except InstallationError:
            return False

    def get_install_path(self, server_id: str, config: ServerConfig) -> Path:
        """Get the installation path for a server."""
        installer = self.get_installer(config.source)
        return installer.get_install_path(server_id, config)
