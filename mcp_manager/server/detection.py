"""Server type detection and execution strategy."""

import json
import logging
import shutil
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import toml

logger = logging.getLogger(__name__)


class ServerType(Enum):
    """Types of MCP servers we can detect."""

    NODEJS = "nodejs"
    PYTHON = "python"
    RUST = "rust"
    GO = "go"
    BINARY = "binary"
    SHELL_SCRIPT = "shell_script"
    UNKNOWN = "unknown"


class ConfigMethod(Enum):
    """How the server prefers to receive configuration."""

    CLI_ARGS = "cli_args"
    ENV_VARS = "env_vars"
    CONFIG_FILE = "config_file"
    NO_CONFIG = "no_config"


@dataclass
class ExecutableInfo:
    """Information about how to execute a server."""

    command: str
    args: List[str]
    cwd: Optional[Path] = None
    env: Optional[Dict[str, str]] = None


@dataclass
class ServerInfo:
    """Complete information about an MCP server."""

    server_type: ServerType
    executable_info: ExecutableInfo
    config_method: ConfigMethod
    config_format: Optional[str] = None  # "json", "yaml", "toml"
    package_name: Optional[str] = None
    entry_point: Optional[Path] = None
    bin_entries: Dict[str, str] = None

    def __post_init__(self):
        if self.bin_entries is None:
            self.bin_entries = {}


class ServerDetector:
    """Detects server type and execution requirements."""

    def __init__(self):
        # Order matters - check more specific types first
        self.detectors = [
            (ServerType.NODEJS, self._detect_nodejs),
            (ServerType.RUST, self._detect_rust),
            (ServerType.GO, self._detect_go),
            (ServerType.PYTHON, self._detect_python),
            (ServerType.BINARY, self._detect_binary),
            (ServerType.SHELL_SCRIPT, self._detect_shell_script),
        ]

    def detect_server(
        self, install_path: Path, requested_package: Optional[str] = None
    ) -> ServerInfo:
        """Detect server type and return execution information."""
        logger.debug(
            f"Detecting server type for: {install_path} (requested: {requested_package})"
        )

        # Try each detector in order of likelihood
        for server_type, detector in self.detectors:
            try:
                # Pass requested_package if the detector supports it
                if server_type in [ServerType.NODEJS, ServerType.PYTHON]:
                    server_info = detector(install_path, requested_package)
                else:
                    server_info = detector(install_path)

                if server_info:
                    logger.info(
                        f"Detected {server_type.value} server at {install_path}"
                    )
                    return server_info
            except Exception as e:
                logger.debug(f"Detector {server_type.value} failed: {e}")
                continue

        # Fallback to unknown type
        logger.warning(f"Could not detect server type for {install_path}")
        return ServerInfo(
            server_type=ServerType.UNKNOWN,
            executable_info=ExecutableInfo(command="python", args=[str(install_path)]),
            config_method=ConfigMethod.CLI_ARGS,
        )

    def _detect_nodejs(
        self, install_path: Path, requested_package: Optional[str] = None
    ) -> Optional[ServerInfo]:
        """Detect Node.js based MCP servers."""
        package_json = install_path / "package.json"

        # Universal fix: Always prefer the actual requested package over wrapper
        if requested_package:
            node_modules = install_path / "node_modules"
            if node_modules.exists():
                # Try to find the exact requested package
                if requested_package.startswith("@"):
                    # Scoped package: @scope/name
                    scope, name = requested_package.split("/", 1)
                    target_path = node_modules / scope / name / "package.json"
                else:
                    # Regular package
                    target_path = node_modules / requested_package / "package.json"

                # Universal approach: Use the actual package if it exists
                if target_path.exists():
                    logger.debug(f"Found actual requested package at {target_path}")
                    package_json = target_path
                    install_path = target_path.parent
                else:
                    logger.debug(
                        f"Requested package {requested_package} not found in node_modules"
                    )

        # Fallback: look for any MCP package with bin entries (executable servers)
        if not package_json.exists():
            node_modules = install_path / "node_modules"
            if node_modules.exists():
                for potential_package in node_modules.rglob("package.json"):
                    if self._is_executable_mcp_package(potential_package):
                        package_json = potential_package
                        install_path = potential_package.parent
                        break

        # If we have a wrapper main.py but also node_modules, prefer Node.js
        if (install_path / "main.py").exists() and (
            install_path / "node_modules"
        ).exists():
            node_modules = install_path / "node_modules"
            # Same logic as above
            if requested_package:
                if requested_package.startswith("@"):
                    scope, name = requested_package.split("/", 1)
                    target_path = node_modules / scope / name / "package.json"
                else:
                    target_path = node_modules / requested_package / "package.json"

                # FIXED: Use the exact requested package even if MCP detection fails
                if target_path.exists():
                    logger.debug(f"Found requested package at {target_path}")
                    package_json = target_path
                    install_path = target_path.parent

        if not package_json.exists():
            return None

        try:
            with open(package_json, "r") as f:
                package_data = json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

        # Check if it's an MCP package
        # For universal compatibility, be more lenient if we have a requested package
        is_mcp_package = self._is_mcp_package_data(package_data)

        if not is_mcp_package and not requested_package:
            return None

        # Universal fallback: If we have a requested package and bin entries, trust it
        # This allows any NPM package to work without complex detection
        if requested_package and package_data.get("bin"):
            logger.info(
                f"Using universal NPM package detection for {requested_package}"
            )
            is_mcp_package = True

        package_name = package_data.get("name", "")
        bin_entries = package_data.get("bin", {})

        # Determine entry point - use universal npx approach when possible
        if bin_entries and requested_package:
            # Universal approach: Use npx to run the package directly
            # This handles all the complexity of finding and running the binary
            logger.info(f"Using universal npx execution for {requested_package}")
            command = "npx"
            args = [requested_package]
            entry_point = install_path / "package.json"  # Reference point
        elif bin_entries:
            # Use first bin entry as default
            first_bin = list(bin_entries.keys())[0]
            entry_file = bin_entries[first_bin]
            entry_point = install_path / entry_file
            command = "node"
            args = [str(entry_point)]
        else:
            # Use main entry point or fallbacks
            main_file = package_data.get("main", "index.js")
            entry_point = install_path / main_file

            # If main file doesn't exist, try common patterns
            if not entry_point.exists():
                common_entry_points = [
                    "index.js",
                    "server.js",
                    "main.js",
                    "cli.js",
                    "app.js",
                ]
                for candidate in common_entry_points:
                    candidate_path = install_path / candidate
                    if candidate_path.exists():
                        main_file = candidate
                        entry_point = candidate_path
                        break

            command = "node"
            args = [str(entry_point)]

        return ServerInfo(
            server_type=ServerType.NODEJS,
            executable_info=ExecutableInfo(
                command=command, args=args, cwd=install_path
            ),
            config_method=ConfigMethod.CLI_ARGS,
            package_name=package_name,
            entry_point=entry_point,
            bin_entries=bin_entries,
        )

    def _detect_python(
        self, install_path: Path, requested_package: Optional[str] = None
    ) -> Optional[ServerInfo]:
        """Detect Python based MCP servers."""

        # Universal UVX detection: If this looks like a uvx directory, use uvx directly
        package_marker = install_path / "package_name.txt"
        if package_marker.exists() and requested_package:
            # This is a uvx package - use universal uvx execution
            logger.info(f"Using universal uvx execution for {requested_package}")
            return ServerInfo(
                server_type=ServerType.PYTHON,
                executable_info=ExecutableInfo(
                    command="uvx", args=[requested_package], cwd=install_path
                ),
                config_method=ConfigMethod.ENV_VARS,  # UVX packages typically use env vars
                package_name=requested_package,
            )

        # Check for Python package indicators
        pyproject_toml = install_path / "pyproject.toml"
        setup_py = install_path / "setup.py"

        if pyproject_toml.exists():
            try:
                with open(pyproject_toml, "r") as f:
                    pyproject_data = toml.load(f)

                # Check if it's an MCP package
                if not self._is_mcp_pyproject(pyproject_data):
                    return None

                # Check for script entries
                scripts = pyproject_data.get("project", {}).get("scripts", {})
                if scripts:
                    # Use first script entry
                    script_name = list(scripts.keys())[0]
                    return ServerInfo(
                        server_type=ServerType.PYTHON,
                        executable_info=ExecutableInfo(
                            command="python", args=["-m", script_name.replace("-", "_")]
                        ),
                        config_method=ConfigMethod.CLI_ARGS,
                        package_name=pyproject_data.get("project", {}).get("name", ""),
                    )

            except (toml.TomlDecodeError, IOError):
                pass

        # Check for common Python entry points
        entry_points = [
            install_path / "main.py",
            install_path / "__main__.py",
            install_path / "server.py",
            install_path / "src" / "main.py",
        ]

        for entry_point in entry_points:
            if entry_point.exists() and self._is_mcp_python_file(entry_point):
                return ServerInfo(
                    server_type=ServerType.PYTHON,
                    executable_info=ExecutableInfo(
                        command="python", args=[str(entry_point)], cwd=install_path
                    ),
                    config_method=ConfigMethod.CLI_ARGS,
                    entry_point=entry_point,
                )

        return None

    def _detect_rust(self, install_path: Path) -> Optional[ServerInfo]:
        """Detect Rust based MCP servers."""
        cargo_toml = install_path / "Cargo.toml"
        if not cargo_toml.exists():
            return None

        try:
            with open(cargo_toml, "r") as f:
                cargo_data = toml.load(f)
        except (toml.TomlDecodeError, IOError):
            return None

        # Check if it's an MCP package
        if not self._is_mcp_cargo(cargo_data):
            return None

        # Look for built binary
        target_dir = install_path / "target" / "release"
        package_name = cargo_data.get("package", {}).get("name", "")

        binary_path = target_dir / package_name
        if binary_path.exists():
            return ServerInfo(
                server_type=ServerType.RUST,
                executable_info=ExecutableInfo(
                    command=str(binary_path), args=[], cwd=install_path
                ),
                config_method=ConfigMethod.CLI_ARGS,
                package_name=package_name,
                entry_point=binary_path,
            )

        # If no binary, need to build
        if shutil.which("cargo"):
            return ServerInfo(
                server_type=ServerType.RUST,
                executable_info=ExecutableInfo(
                    command="cargo", args=["run", "--release", "--"], cwd=install_path
                ),
                config_method=ConfigMethod.CLI_ARGS,
                package_name=package_name,
            )

        return None

    def _detect_go(self, install_path: Path) -> Optional[ServerInfo]:
        """Detect Go based MCP servers."""
        go_mod = install_path / "go.mod"
        if not go_mod.exists():
            return None

        # Check if it looks like an MCP server
        main_go = install_path / "main.go"
        if main_go.exists() and self._is_mcp_go_file(main_go):
            return ServerInfo(
                server_type=ServerType.GO,
                executable_info=ExecutableInfo(
                    command="go", args=["run", "main.go"], cwd=install_path
                ),
                config_method=ConfigMethod.CLI_ARGS,
                entry_point=main_go,
            )

        return None

    def _detect_binary(self, install_path: Path) -> Optional[ServerInfo]:
        """Detect pre-compiled binary MCP servers."""
        # Look for executable files
        for item in install_path.iterdir():
            if item.is_file() and item.stat().st_mode & 0o111:  # Executable
                # Check if it's likely an MCP server binary
                if self._is_mcp_binary(item):
                    return ServerInfo(
                        server_type=ServerType.BINARY,
                        executable_info=ExecutableInfo(
                            command=str(item), args=[], cwd=install_path
                        ),
                        config_method=ConfigMethod.CLI_ARGS,
                        entry_point=item,
                    )

        return None

    def _detect_shell_script(self, install_path: Path) -> Optional[ServerInfo]:
        """Detect shell script based MCP servers."""
        script_extensions = [".sh", ".bash", ".zsh"]

        for item in install_path.iterdir():
            if item.is_file() and any(
                item.name.endswith(ext) for ext in script_extensions
            ):
                if self._is_mcp_script(item):
                    return ServerInfo(
                        server_type=ServerType.SHELL_SCRIPT,
                        executable_info=ExecutableInfo(
                            command="bash", args=[str(item)], cwd=install_path
                        ),
                        config_method=ConfigMethod.ENV_VARS,
                        entry_point=item,
                    )

        return None

    def _is_mcp_package(self, package_json_path: Path) -> bool:
        """Check if a package.json indicates an MCP server."""
        try:
            with open(package_json_path, "r") as f:
                data = json.load(f)
            return self._is_mcp_package_data(data)
        except:
            return False

    def _is_mcp_package_data(self, package_data: Dict[str, Any]) -> bool:
        """Check if package.json data indicates an MCP server."""
        # Check dependencies
        all_deps = {}
        all_deps.update(package_data.get("dependencies", {}))
        all_deps.update(package_data.get("devDependencies", {}))

        mcp_indicators = ["@modelcontextprotocol/sdk", "mcp", "model-context-protocol"]

        # Check if it has MCP dependencies
        for indicator in mcp_indicators:
            if indicator in all_deps:
                return True

        # Check description
        description = package_data.get("description", "").lower()
        if "mcp" in description or "model context protocol" in description:
            return True

        # Check keywords
        keywords = package_data.get("keywords", [])
        for keyword in keywords:
            if isinstance(keyword, str) and (
                "mcp" in keyword.lower() or "model-context" in keyword.lower()
            ):
                return True

        return False

    def _is_mcp_pyproject(self, pyproject_data: Dict[str, Any]) -> bool:
        """Check if pyproject.toml indicates an MCP server."""
        dependencies = pyproject_data.get("project", {}).get("dependencies", [])

        mcp_indicators = ["mcp", "model-context-protocol"]

        for dep in dependencies:
            if isinstance(dep, str):
                dep_name = dep.split(">=")[0].split("==")[0].strip()
                if any(indicator in dep_name.lower() for indicator in mcp_indicators):
                    return True

        return False

    def _is_mcp_cargo(self, cargo_data: Dict[str, Any]) -> bool:
        """Check if Cargo.toml indicates an MCP server."""
        dependencies = cargo_data.get("dependencies", {})

        mcp_indicators = ["mcp", "model-context-protocol"]

        for dep_name in dependencies.keys():
            if any(indicator in dep_name.lower() for indicator in mcp_indicators):
                return True

        return False

    def _is_mcp_python_file(self, file_path: Path) -> bool:
        """Check if a Python file looks like an MCP server."""
        try:
            with open(file_path, "r") as f:
                content = f.read(2000)  # Read first 2KB

            mcp_indicators = [
                "import mcp",
                "from mcp",
                "mcp.server",
                "mcp.client",
                "model_context_protocol",
            ]

            return any(indicator in content for indicator in mcp_indicators)
        except:
            return False

    def _is_mcp_go_file(self, file_path: Path) -> bool:
        """Check if a Go file looks like an MCP server."""
        try:
            with open(file_path, "r") as f:
                content = f.read(2000)

            mcp_indicators = ['"mcp"', "model-context-protocol", "ModelContextProtocol"]

            return any(indicator in content for indicator in mcp_indicators)
        except:
            return False

    def _is_executable_mcp_package(self, package_json_path: Path) -> bool:
        """Check if this is an executable MCP package (has bin entries and MCP deps)."""
        try:
            with open(package_json_path, "r") as f:
                data = json.load(f)
        except:
            return False

        # Must have executable entries (bin) and be an MCP package
        return "bin" in data and self._is_mcp_package_data(data)

    def _is_mcp_binary(self, binary_path: Path) -> bool:
        """Check if a binary looks like an MCP server."""
        # For now, just check if it's executable and has "mcp" in the name
        name_lower = binary_path.name.lower()
        return (
            "mcp" in name_lower
            or "server" in name_lower
            or binary_path.stat().st_mode & 0o111
        )

    def _is_mcp_script(self, script_path: Path) -> bool:
        """Check if a shell script looks like an MCP server."""
        try:
            with open(script_path, "r") as f:
                content = f.read(1000)

            mcp_indicators = ["mcp", "model-context-protocol", "stdio", "json-rpc"]

            return any(indicator in content.lower() for indicator in mcp_indicators)
        except:
            return False
