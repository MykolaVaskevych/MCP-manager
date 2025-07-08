"""MCP process management."""

import asyncio
import logging
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional

import mcp.types as types
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from ..config.adaptation import ConfigurationAdaptationSystem
from ..config.models import ServerConfig
from .detection import ServerDetector

logger = logging.getLogger(__name__)


class ProcessStatus(Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    FAILED = "failed"
    NOT_CONFIGURED = "not_configured"


class HealthStatus(Enum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class MCPProcess:
    def __init__(self, server_id: str, config: ServerConfig, install_path: Path):
        self.server_id = server_id
        self.config = config
        self.install_path = install_path
        self.process: Optional[asyncio.subprocess.Process] = None
        self.session: Optional[ClientSession] = None
        self.status = ProcessStatus.STOPPED
        self.start_time: Optional[datetime] = None
        self.request_count = 0
        self.error_count = 0
        self.last_activity = datetime.now()

        # Context managers for proper cleanup
        self._stdio_context = None
        self._session_context = None

        # Configuration adaptation system
        self._config_adapter = ConfigurationAdaptationSystem()

    async def start(self) -> None:
        """Start MCP server process and establish session."""
        if self.status != ProcessStatus.STOPPED:
            return

        self.status = ProcessStatus.STARTING
        logger.info(f"Starting MCP server: {self.server_id}")

        try:
            if self.config.transport == "stdio":
                await self._start_stdio()
            elif self.config.transport == "sse":
                await self._start_sse()
            elif self.config.transport == "websocket":
                await self._start_websocket()
            else:
                raise ValueError(f"Unsupported transport: {self.config.transport}")

            self.status = ProcessStatus.RUNNING
            self.start_time = datetime.now()
            logger.info(f"MCP server {self.server_id} started successfully")

        except Exception as e:
            self.status = ProcessStatus.FAILED
            logger.error(f"Failed to start MCP server {self.server_id}: {e}")
            raise

    async def _start_stdio(self) -> None:
        """Start STDIO-based MCP server using proper MCP SDK abstractions."""
        # Universal package extraction - works with any source type
        requested_package = None
        if ":" in self.config.source:
            source_type, package_name = self.config.source.split(":", 1)
            if source_type in ["npm", "uvx", "pip"]:
                requested_package = package_name

        # Detect server type and execution info
        detector = ServerDetector()
        server_info = detector.detect_server(self.install_path, requested_package)

        logger.debug(f"Detected server type: {server_info.server_type}")

        # Build command and args based on detection
        command = server_info.executable_info.command
        args = server_info.executable_info.args.copy()

        # Universal configuration - works with any MCP server
        env_vars = None
        if self.config.config:
            # Use universal adapter for any MCP server
            adapted_config = self._config_adapter.adapt_config(
                self.config.config, server_info
            )

            # Apply configuration (universal system uses environment variables)
            if adapted_config.get("env_vars"):
                env_vars = adapted_config["env_vars"]
                logger.debug(
                    f"Applied {len(env_vars)} environment variables for {self.server_id}"
                )

        logger.debug(f"Starting server with command: {command} {' '.join(args)}")

        # Create server parameters for MCP SDK
        # Merge environment variables (server-specific + config-specific)
        final_env = {}
        if server_info.executable_info.env:
            final_env.update(server_info.executable_info.env)
        if env_vars:
            final_env.update(env_vars)

        server_params = StdioServerParameters(
            command=command,
            args=args,
            cwd=server_info.executable_info.cwd or self.install_path,
            env=final_env if final_env else None,
        )

        # Use proper MCP SDK stdio_client
        try:
            # Store the context manager for later cleanup
            self._stdio_context = stdio_client(server_params)
            read_stream, write_stream = await self._stdio_context.__aenter__()

            # Create session with proper MCP streams
            self._session_context = ClientSession(read_stream, write_stream)
            self.session = await self._session_context.__aenter__()
            await self.session.initialize()

        except Exception as e:
            # Clean up on failure
            if self._session_context and self.session:
                try:
                    await self._session_context.__aexit__(type(e), e, e.__traceback__)
                except Exception:
                    pass
                self.session = None
                self._session_context = None

            if self._stdio_context:
                try:
                    await self._stdio_context.__aexit__(type(e), e, e.__traceback__)
                except Exception:
                    pass
                self._stdio_context = None

            self.status = ProcessStatus.FAILED
            logger.error(f"Failed to start MCP server {self.server_id}: {e}")
            raise e

    async def _start_sse(self) -> None:
        """Start SSE-based MCP server."""
        # This would use mcp.client.sse
        raise NotImplementedError("SSE transport not yet implemented")

    async def _start_websocket(self) -> None:
        """Start WebSocket-based MCP server."""
        # This would use mcp.client.websocket
        raise NotImplementedError("WebSocket transport not yet implemented")

    def _get_executable_path(self) -> Path:
        """Get the executable path for the MCP server."""
        # Try common patterns
        candidates = [
            self.install_path / "main.py",
            self.install_path / "__main__.py",
            self.install_path / "server.py",
            self.install_path / "src" / "main.py",
        ]

        for candidate in candidates:
            if candidate.exists():
                return candidate

        # If no standard file found, look for any Python file
        python_files = list(self.install_path.glob("*.py"))
        if python_files:
            return python_files[0]

        raise FileNotFoundError(f"No executable found in {self.install_path}")

    async def stop(self) -> None:
        """Gracefully stop MCP server process."""
        if self.status not in [ProcessStatus.RUNNING, ProcessStatus.STARTING]:
            return

        self.status = ProcessStatus.STOPPING
        logger.info(f"Stopping MCP server: {self.server_id}")

        session_exception = None
        stdio_exception = None

        try:
            # Close session context manager first
            if self._session_context and self.session:
                try:
                    await self._session_context.__aexit__(None, None, None)
                except Exception as e:
                    session_exception = e
                    logger.debug(
                        f"Exception during session cleanup for {self.server_id}: {e}"
                    )
                finally:
                    self.session = None
                    self._session_context = None

            # Close stdio context manager
            if self._stdio_context:
                try:
                    await self._stdio_context.__aexit__(None, None, None)
                except Exception as e:
                    stdio_exception = e
                    logger.debug(
                        f"Exception during stdio cleanup for {self.server_id}: {e}"
                    )
                finally:
                    self._stdio_context = None

            # Clean up configuration adapter temp files
            if self._config_adapter:
                try:
                    self._config_adapter.cleanup()
                except Exception as e:
                    logger.debug(
                        f"Exception during config cleanup for {self.server_id}: {e}"
                    )

            # Process cleanup is handled by the stdio_client context manager
            self.process = None
            self.status = ProcessStatus.STOPPED
            logger.info(f"MCP server {self.server_id} stopped")

        except Exception as e:
            self.status = ProcessStatus.FAILED
            logger.error(f"Error stopping MCP server {self.server_id}: {e}")

            # If we had cleanup exceptions, log them but don't re-raise
            if session_exception:
                logger.debug(
                    f"Session cleanup exception for {self.server_id}: {session_exception}"
                )
            if stdio_exception:
                logger.debug(
                    f"Stdio cleanup exception for {self.server_id}: {stdio_exception}"
                )

    async def restart(self) -> None:
        """Restart MCP server process."""
        logger.info(f"Restarting MCP server: {self.server_id}")
        await self.stop()
        await asyncio.sleep(1)  # Brief pause
        await self.start()

    async def health_check(self) -> HealthStatus:
        """Check if MCP server is responding correctly."""
        if not self.session or self.status != ProcessStatus.RUNNING:
            return HealthStatus.UNHEALTHY

        try:
            if (
                self.config.health_check
                and self.config.health_check.method == "tool_call"
            ):
                # Use specific tool call for health check
                tool_name = self.config.health_check.tool
                args = self.config.health_check.args or {}

                await asyncio.wait_for(
                    self.session.call_tool(tool_name, args),
                    timeout=self.config.health_check.timeout,
                )
            else:
                # Default: try listing tools as basic health check
                await asyncio.wait_for(self.session.list_tools(), timeout=5.0)

            return HealthStatus.HEALTHY

        except Exception as e:
            logger.warning(f"Health check failed for {self.server_id}: {e}")
            return HealthStatus.UNHEALTHY

    async def call_tool(self, name: str, arguments: dict) -> types.CallToolResult:
        """Call a tool on this MCP server."""
        if not self.session:
            raise RuntimeError(f"MCP server {self.server_id} not running")

        self.request_count += 1
        self.last_activity = datetime.now()

        try:
            result = await asyncio.wait_for(
                self.session.call_tool(name, arguments), timeout=30.0
            )
            return result
        except asyncio.TimeoutError:
            self.error_count += 1
            error_msg = f"Timeout calling tool {name} on server {self.server_id}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        except Exception as e:
            self.error_count += 1
            error_msg = f"Error calling tool {name} on server {self.server_id}: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

    async def list_tools(self) -> types.ListToolsResult:
        """List tools available on this MCP server."""
        if not self.session:
            raise RuntimeError(f"MCP server {self.server_id} not running")

        self.last_activity = datetime.now()
        try:
            result = await asyncio.wait_for(self.session.list_tools(), timeout=10.0)
            return result
        except asyncio.TimeoutError:
            error_msg = f"Timeout listing tools from server {self.server_id}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        except Exception as e:
            error_msg = f"Error listing tools from server {self.server_id}: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

    async def read_resource(self, uri: str) -> types.ReadResourceResult:
        """Read a resource from this MCP server."""
        if not self.session:
            raise RuntimeError(f"MCP server {self.server_id} not running")

        self.last_activity = datetime.now()
        try:
            result = await asyncio.wait_for(
                self.session.read_resource(uri), timeout=15.0
            )
            return result
        except asyncio.TimeoutError:
            error_msg = f"Timeout reading resource {uri} from server {self.server_id}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        except Exception as e:
            error_msg = (
                f"Error reading resource {uri} from server {self.server_id}: {e}"
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg)

    async def list_resources(self) -> types.ListResourcesResult:
        """List resources available on this MCP server."""
        if not self.session:
            raise RuntimeError(f"MCP server {self.server_id} not running")

        self.last_activity = datetime.now()
        try:
            result = await asyncio.wait_for(self.session.list_resources(), timeout=10.0)
            return result
        except asyncio.TimeoutError:
            error_msg = f"Timeout listing resources from server {self.server_id}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        except Exception as e:
            error_msg = f"Error listing resources from server {self.server_id}: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

    @property
    def uptime(self) -> Optional[timedelta]:
        """Get process uptime."""
        if self.start_time and self.status == ProcessStatus.RUNNING:
            return datetime.now() - self.start_time
        return None

    @property
    def is_healthy(self) -> bool:
        """Check if process is in a healthy state."""
        return self.status == ProcessStatus.RUNNING
