"""MCP server manager."""

import asyncio
import logging
from pathlib import Path
from typing import Dict, Optional

from ..config.models import MCPManagerConfig, ServerConfig
from ..installers import get_universal_installer
from .process import HealthStatus, MCPProcess, ProcessStatus

logger = logging.getLogger(__name__)


class MCPServerManager:
    def __init__(self, config: MCPManagerConfig):
        self.config = config
        self.processes: Dict[str, MCPProcess] = {}
        self.health_check_task: Optional[asyncio.Task] = None

        # Initialize universal installer
        self.base_install_dir = Path.cwd() / "mcp-servers"
        self.installer = get_universal_installer(self.base_install_dir)

    async def start_all_servers(self) -> None:
        """Start all configured servers."""
        logger.info("Starting all MCP servers")

        tasks = []
        for server_id, server_config in self.config.servers.items():
            if server_config.enabled:
                task = asyncio.create_task(
                    self.start_server(server_id), name=f"start_{server_id}"
                )
                tasks.append(task)

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Log any failures
            for server_id, result in zip(self.config.servers.keys(), results):
                if isinstance(result, Exception):
                    logger.error(f"Failed to start server {server_id}: {result}")

        # Start health checking
        if self.config.runtime.health_check_enabled:
            self.health_check_task = asyncio.create_task(self._health_check_loop())

    async def start_server(self, server_id: str) -> None:
        """Start a specific server."""
        if server_id in self.processes:
            logger.warning(f"Server {server_id} already running")
            return

        server_config = self.config.servers.get(server_id)
        if not server_config:
            raise ValueError(f"Server {server_id} not configured")

        if not server_config.enabled:
            logger.info(f"Server {server_id} is disabled, skipping")
            return

        logger.info(f"Starting server: {server_id}")

        try:
            # Ensure server is installed
            install_path = await self._ensure_server_installed(server_id, server_config)

            # Create and start process
            process = MCPProcess(server_id, server_config, install_path)
            await process.start()

            self.processes[server_id] = process
            logger.info(f"Server {server_id} started successfully")

        except Exception as e:
            logger.error(f"Failed to start server {server_id}: {e}")
            raise

    async def stop_server(self, server_id: str) -> None:
        """Stop a specific server."""
        process = self.processes.get(server_id)
        if not process:
            logger.warning(f"Server {server_id} not running")
            return

        logger.info(f"Stopping server: {server_id}")
        await process.stop()
        del self.processes[server_id]

    async def restart_server(self, server_id: str) -> None:
        """Restart a specific server."""
        logger.info(f"Restarting server: {server_id}")

        if server_id in self.processes:
            await self.stop_server(server_id)

        await self.start_server(server_id)

    async def stop_all_servers(self) -> None:
        """Stop all running servers."""
        logger.info("Stopping all MCP servers")

        # Stop health checking
        if self.health_check_task:
            self.health_check_task.cancel()
            try:
                await self.health_check_task
            except asyncio.CancelledError:
                pass

        # Stop all processes
        tasks = []
        for server_id in list(self.processes.keys()):
            task = asyncio.create_task(
                self.stop_server(server_id), name=f"stop_{server_id}"
            )
            tasks.append(task)

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _ensure_server_installed(
        self, server_id: str, server_config: ServerConfig
    ) -> Path:
        """Ensure server is installed and return installation path."""
        # Check if already installed
        if (
            self.installer.is_installed(server_id, server_config)
            and not server_config.auto_install
        ):
            return self.installer.get_install_path(server_id, server_config)

        # Install if needed
        if server_config.auto_install:
            logger.info(f"Installing server: {server_id}")
            install_path = await self.installer.install(server_id, server_config)
            logger.info(f"Server {server_id} installed to: {install_path}")
            return install_path
        else:
            return self.installer.get_install_path(server_id, server_config)

    async def _health_check_loop(self) -> None:
        """Background task for health checking all servers."""
        while True:
            try:
                await self._perform_health_checks()
                await asyncio.sleep(60)  # Check every minute
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in health check loop: {e}")
                await asyncio.sleep(60)

    async def _perform_health_checks(self) -> None:
        """Perform health checks on all running servers."""
        tasks = []

        for server_id, process in self.processes.items():
            if process.status == ProcessStatus.RUNNING:
                task = asyncio.create_task(
                    self._check_server_health(server_id, process),
                    name=f"health_check_{server_id}",
                )
                tasks.append(task)

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _check_server_health(self, server_id: str, process: MCPProcess) -> None:
        """Check health of a specific server."""
        try:
            health = await process.health_check()

            if health == HealthStatus.UNHEALTHY:
                logger.warning(f"Server {server_id} is unhealthy")

                if self.config.runtime.auto_restart_failed_servers:
                    logger.info(f"Auto-restarting unhealthy server: {server_id}")
                    await self.restart_server(server_id)

        except Exception as e:
            logger.error(f"Health check failed for {server_id}: {e}")

    def get_server_status(self, server_id: str) -> Optional[Dict]:
        """Get status information for a server."""
        process = self.processes.get(server_id)
        if not process:
            return None

        return {
            "status": process.status.value,
            "uptime": process.uptime.total_seconds() if process.uptime else 0,
            "request_count": process.request_count,
            "error_count": process.error_count,
            "last_activity": process.last_activity.isoformat(),
            "healthy": process.is_healthy,
        }

    def get_all_status(self) -> Dict[str, Dict]:
        """Get status for all servers."""
        return {
            server_id: self.get_server_status(server_id)
            for server_id in self.config.servers.keys()
        }

    def get_active_sessions(self) -> Dict[str, MCPProcess]:
        """Get all active MCP sessions."""
        return {
            server_id: process
            for server_id, process in self.processes.items()
            if process.status == ProcessStatus.RUNNING and process.session
        }

    async def call_tool(self, server_id: str, tool_name: str, arguments: dict):
        """Call a tool on a specific server."""
        process = self.processes.get(server_id)
        if not process:
            raise ValueError(f"Server {server_id} not running")

        return await process.call_tool(tool_name, arguments)

    async def list_tools(self, server_id: str):
        """List tools for a specific server."""
        process = self.processes.get(server_id)
        if not process:
            raise ValueError(f"Server {server_id} not running")

        return await process.list_tools()

    async def list_resources(self, server_id: str):
        """List resources for a specific server."""
        process = self.processes.get(server_id)
        if not process:
            raise ValueError(f"Server {server_id} not running")

        return await process.list_resources()

    async def read_resource(self, server_id: str, uri: str):
        """Read a resource from a specific server."""
        process = self.processes.get(server_id)
        if not process:
            raise ValueError(f"Server {server_id} not running")

        return await process.read_resource(uri)
