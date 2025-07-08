"""NPM-based MCP server installer."""

import json
import logging
from pathlib import Path

import httpx

from ..config.models import ServerConfig
from .base import BaseInstaller

logger = logging.getLogger(__name__)


class NPMInstaller(BaseInstaller):
    """Installer for NPM-based MCP servers."""

    def get_install_path(self, server_id: str, config: ServerConfig) -> Path:
        """Get installation path for NPM package."""
        _, package_name = config.source.split(":", 1)
        safe_name = package_name.replace("/", "-").replace("@", "")
        return self.base_install_dir / "npm" / safe_name

    def is_installed(self, server_id: str, config: ServerConfig) -> bool:
        """Check if NPM package is installed."""
        install_path = self.get_install_path(server_id, config)

        # Check if package.json and node_modules exist
        package_json = install_path / "package.json"
        node_modules = install_path / "node_modules"

        return package_json.exists() and node_modules.exists()

    async def install(self, server_id: str, config: ServerConfig) -> Path:
        """Install NPM-based MCP server."""
        _, package_name = config.source.split(":", 1)
        install_path = self.get_install_path(server_id, config)

        logger.info(f"Installing NPM package: {package_name}")

        # Create installation directory
        install_path.mkdir(parents=True, exist_ok=True)

        try:
            # Get package info from NPM registry
            package_info = await self._get_package_info(package_name)
            version = config.version or package_info["dist-tags"]["latest"]

            # Create package.json
            await self._create_package_json(install_path, package_name, version)

            # Run npm install
            await self._npm_install(install_path)

            # Create a main entry point if needed
            await self._create_main_script(install_path, package_name)

            logger.info(f"NPM package {package_name} installed successfully")
            return install_path

        except Exception as e:
            logger.error(f"Failed to install NPM package {package_name}: {e}")
            # Clean up on failure
            if install_path.exists():
                await self._cleanup_directory(install_path)
            raise

    async def _get_package_info(self, package_name: str) -> dict:
        """Get package information from NPM registry."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"https://registry.npmjs.org/{package_name}")
            response.raise_for_status()
            return response.json()

    async def _create_main_script(self, install_path: Path, package_name: str) -> None:
        """Create a main script to run the NPM package."""
        # Try to find the main entry point
        package_json_path = (
            install_path / "node_modules" / package_name / "package.json"
        )

        if package_json_path.exists():
            with open(package_json_path) as f:
                package_data = json.load(f)

            main_file = package_data.get("main", "index.js")
            bin_files = package_data.get("bin", {})

            # Create a Python wrapper script
            wrapper_script = f"""#!/usr/bin/env python3
import subprocess
import sys
import os

# Change to the package directory
os.chdir(os.path.join(os.path.dirname(__file__), "node_modules", "{package_name}"))

# Run the Node.js application
try:
    if len(sys.argv) > 1 and sys.argv[1] in {list(bin_files.keys())}:
        # Run specific bin command
        cmd = ["node", bin_files[sys.argv[1]]] + sys.argv[2:]
    else:
        # Run main file
        cmd = ["node", "{main_file}"] + sys.argv[1:]
    
    result = subprocess.run(cmd, check=True)
    sys.exit(result.returncode)
except subprocess.CalledProcessError as e:
    sys.exit(e.returncode)
except KeyboardInterrupt:
    sys.exit(1)
"""

            main_py = install_path / "main.py"
            with open(main_py, "w") as f:
                f.write(wrapper_script)

            # Make it executable
            main_py.chmod(0o755)

    async def _cleanup_directory(self, directory: Path) -> None:
        """Clean up installation directory."""
        try:
            # Remove directory recursively
            await self._run_command(["rm", "-rf", str(directory)])
        except Exception as e:
            logger.warning(f"Failed to cleanup directory {directory}: {e}")
