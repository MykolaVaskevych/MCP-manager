"""Main MCP Manager application."""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.shared.context import RequestContext

from ..access.client_identifier import ClientIdentifier, ConnectionContext
from ..access.middleware import AccessControlMiddleware
from ..access.permission_engine import PermissionEngine
from ..config.manager import ConfigManager
from ..routing.router import MCPRouter
from ..server.manager import MCPServerManager
from .config_watcher import ConfigWatcher

logger = logging.getLogger(__name__)


class MCPManager:
    """Main MCP Manager application that acts as both client and server."""

    def __init__(self, config_path: str):
        self.config_path = Path(config_path)
        self.config_manager = ConfigManager(str(self.config_path))
        self.config = self.config_manager.load_config()

        # Core components
        self.server_manager = MCPServerManager(self.config)
        self.permission_engine = PermissionEngine(self.config)
        self.client_identifier = ClientIdentifier(self.config)
        self.router = MCPRouter(self.server_manager, self.permission_engine)
        self.access_middleware = AccessControlMiddleware(
            self.permission_engine, self.client_identifier
        )

        # MCP Server setup
        self.mcp_server = Server(self.config.manager.name)
        self._setup_mcp_handlers()

        # Runtime state
        self.start_time: Optional[datetime] = None
        self.active_clients: Dict[str, ConnectionContext] = {}
        self.config_watcher: Optional[ConfigWatcher] = None

        # Setup logging
        self._setup_logging()

    def _setup_logging(self):
        """Setup logging configuration."""
        level = getattr(logging, self.config.manager.log_level.upper())
        logging.basicConfig(
            level=level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

    def _setup_mcp_handlers(self):
        """Set up MCP server handlers that route to backends."""

        @self.mcp_server.list_tools()
        async def list_tools() -> list[types.Tool]:
            """List all available tools from backend servers."""
            logger.info("Received list_tools request")
            try:
                # Access request context properly
                ctx = self.mcp_server.request_context
                context = self._create_connection_context(ctx)

                # Route request
                request = types.ListToolsRequest(method="tools/list")
                logger.info("Routing list_tools request")
                result = await self.router.route_request(request, context)
                logger.info(f"Router result: {type(result)}")

                if isinstance(result, types.ListToolsResult):
                    logger.info(f"Returning {len(result.tools)} tools")
                    return result.tools
                else:
                    # Return empty list on error
                    logger.error(f"Error listing tools: {result}")
                    return []
            except Exception as e:
                logger.error(f"Exception in list_tools: {e}", exc_info=True)
                return []

        @self.mcp_server.call_tool()
        async def call_tool(
            name: str, arguments: dict
        ) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
            """Call a tool on backend servers."""
            try:
                ctx = self.mcp_server.request_context
                context = self._create_connection_context(ctx)

                # Create request object from parameters
                request = types.CallToolRequest(
                    method="tools/call",
                    params=types.CallToolRequestParams(name=name, arguments=arguments),
                )

                # Check access control
                allowed, error_response = await self.access_middleware.process_request(
                    request, context
                )
                if not allowed:
                    # Convert ErrorData to error content
                    return [
                        types.TextContent(
                            type="text", text=f"Access denied: {error_response.message}"
                        )
                    ]

                # Route request
                result = await self.router.route_request(request, context)

                if isinstance(result, types.CallToolResult):
                    return result.content
                elif isinstance(result, types.ErrorData):
                    return [
                        types.TextContent(type="text", text=f"Error: {result.message}")
                    ]
                else:
                    return [
                        types.TextContent(type="text", text="Unknown error occurred")
                    ]
            except Exception as e:
                logger.error(f"Exception in call_tool: {e}", exc_info=True)
                return [
                    types.TextContent(type="text", text=f"Internal error: {str(e)}")
                ]

        @self.mcp_server.list_resources()
        async def list_resources() -> list[types.Resource]:
            """List all available resources from backend servers."""
            try:
                ctx = self.mcp_server.request_context
                context = self._create_connection_context(ctx)

                # Route request
                request = types.ListResourcesRequest(method="resources/list")
                result = await self.router.route_request(request, context)

                if isinstance(result, types.ListResourcesResult):
                    return result.resources
                else:
                    logger.error(f"Error listing resources: {result}")
                    return []
            except Exception as e:
                logger.error(f"Exception in list_resources: {e}", exc_info=True)
                return []

        @self.mcp_server.read_resource()
        async def read_resource(uri: str) -> str | bytes:
            """Read a resource from backend servers."""
            try:
                ctx = self.mcp_server.request_context
                context = self._create_connection_context(ctx)

                # Create request object from URI
                request = types.ReadResourceRequest(
                    method="resources/read",
                    params=types.ReadResourceRequestParams(uri=uri),
                )

                # Check access control
                allowed, error_response = await self.access_middleware.process_request(
                    request, context
                )
                if not allowed:
                    return f"Access denied: {error_response.message}"

                # Route request
                result = await self.router.route_request(request, context)

                if isinstance(result, types.ReadResourceResult):
                    # Return first content or empty string
                    if result.contents:
                        first_content = result.contents[0]
                        if hasattr(first_content, "text"):
                            return first_content.text
                        elif hasattr(first_content, "blob"):
                            return first_content.blob
                    return ""
                elif isinstance(result, types.ErrorData):
                    return f"Error: {result.message}"
                else:
                    return "Unknown error occurred"
            except Exception as e:
                logger.error(f"Exception in read_resource: {e}", exc_info=True)
                return f"Internal error: {str(e)}"

    def _create_connection_context(self, ctx: RequestContext) -> ConnectionContext:
        """Create connection context from MCP request context."""
        context = ConnectionContext()

        try:
            # Extract client information from session if available
            if hasattr(ctx, "session") and ctx.session is not None:
                session = ctx.session

                # Try to get client parameters
                if (
                    hasattr(session, "client_params")
                    and session.client_params is not None
                ):
                    client_params = session.client_params
                    context.client_info = client_params

                    # Extract client ID from client info if available
                    if (
                        hasattr(client_params, "clientInfo")
                        and client_params.clientInfo is not None
                    ):
                        client_info = client_params.clientInfo
                        if hasattr(client_info, "name"):
                            context.client_id = client_info.name
                        elif hasattr(client_info, "version"):
                            # Fallback to version if name not available
                            context.client_id = f"client_{client_info.version}"

                    # Check capabilities if available
                    if hasattr(client_params, "capabilities"):
                        context.capabilities = client_params.capabilities

            # Fallback client identification
            if not context.client_id:
                context.client_id = "default"
                logger.debug("Using default client ID due to missing client info")

            # Set other context fields
            context.transport_type = "stdio"
            context.timestamp = datetime.now()

            # Add request metadata if available
            if hasattr(ctx, "request_id"):
                context.request_id = ctx.request_id
            if hasattr(ctx, "meta"):
                context.meta = ctx.meta

        except Exception as e:
            logger.warning(f"Error extracting context information: {e}")
            # Provide minimal working context
            context.client_id = "default"
            context.transport_type = "stdio"
            context.timestamp = datetime.now()

        return context

    async def start(self) -> None:
        """Start the MCP manager."""
        self.start_time = datetime.now()
        logger.info("Starting MCP Manager")

        try:
            # Start router
            await self.router.start()

            # Start all backend servers
            await self.server_manager.start_all_servers()

            # Start the MCP server and config watcher in the same context
            logger.info(f"MCP Manager '{self.config.manager.name}' ready")
            from mcp.server.stdio import stdio_server

            async with stdio_server() as streams:
                # Start config file watcher within the stdio context
                self.config_watcher = ConfigWatcher(str(self.config_path), self)
                config_watch_task = asyncio.create_task(
                    self.config_watcher.start_watching()
                )

                try:
                    import mcp.types as types
                    from mcp.server.lowlevel.server import InitializationOptions

                    init_options = InitializationOptions(
                        server_name=self.config.manager.name,
                        server_version=self.config.manager.version,
                        capabilities=types.ServerCapabilities(
                            tools=types.ToolsCapability(listChanged=True),
                            resources=types.ResourcesCapability(listChanged=True),
                        ),
                        instructions=None,
                    )

                    await self.mcp_server.run(
                        *streams, initialization_options=init_options
                    )
                finally:
                    # Ensure config watcher is properly cancelled
                    if config_watch_task and not config_watch_task.done():
                        config_watch_task.cancel()
                        try:
                            await config_watch_task
                        except asyncio.CancelledError:
                            pass

        except Exception as e:
            logger.error(f"Error starting MCP manager: {e}", exc_info=True)
            await self.stop()
            raise

    async def stop(self) -> None:
        """Stop the MCP manager."""
        logger.info("Stopping MCP Manager")

        try:
            # Stop config watcher
            if self.config_watcher:
                await self.config_watcher.stop()

            # Stop router
            await self.router.stop()

            # Stop all backend servers
            await self.server_manager.stop_all_servers()

        except Exception as e:
            logger.error(f"Error stopping MCP manager: {e}")

    async def reload_config(self) -> None:
        """Reload configuration and apply changes."""
        logger.info("Reloading configuration")

        try:
            # Load new configuration
            old_config = self.config
            new_config = self.config_manager.reload_config()

            # Apply changes
            await self._apply_config_changes(old_config, new_config)

            # Update components with new config
            self.config = new_config
            self.server_manager.config = new_config
            self.permission_engine = PermissionEngine(new_config)
            self.client_identifier = ClientIdentifier(new_config)

            logger.info("Configuration reloaded successfully")

        except Exception as e:
            logger.error(f"Failed to reload configuration: {e}")
            raise

    async def _apply_config_changes(self, old_config, new_config):
        """Apply configuration changes without full restart."""

        # Compare server configurations
        old_servers = set(old_config.servers.keys())
        new_servers = set(new_config.servers.keys())

        # Stop removed servers
        for server_id in old_servers - new_servers:
            logger.info(f"Removing server: {server_id}")
            await self.server_manager.stop_server(server_id)

        # Start new servers
        for server_id in new_servers - old_servers:
            logger.info(f"Adding server: {server_id}")
            # Update config first
            self.server_manager.config = new_config
            await self.server_manager.start_server(server_id)

        # Restart modified servers
        for server_id in old_servers & new_servers:
            old_server_config = old_config.servers[server_id]
            new_server_config = new_config.servers[server_id]

            # Compare relevant fields that would require restart
            if (
                old_server_config.source != new_server_config.source
                or old_server_config.version != new_server_config.version
                or old_server_config.transport != new_server_config.transport
                or old_server_config.config != new_server_config.config
            ):
                logger.info(f"Restarting modified server: {server_id}")
                await self.server_manager.restart_server(server_id)

    def get_status(self) -> Dict:
        """Get overall manager status."""
        uptime = (
            (datetime.now() - self.start_time).total_seconds() if self.start_time else 0
        )

        return {
            "manager": {
                "name": self.config.manager.name,
                "version": self.config.manager.version,
                "uptime_seconds": uptime,
                "start_time": self.start_time.isoformat() if self.start_time else None,
            },
            "servers": self.server_manager.get_all_status(),
            "routing": self.router.get_stats(),
            "active_clients": len(self.active_clients),
        }

    def get_config_summary(self) -> Dict:
        """Get configuration summary."""
        return {
            "servers": {
                "total": len(self.config.servers),
                "enabled": sum(1 for s in self.config.servers.values() if s.enabled),
                "disabled": sum(
                    1 for s in self.config.servers.values() if not s.enabled
                ),
            },
            "clients": {
                "total": len(self.config.clients),
                "rules": sum(
                    len(c.allow) + len(c.deny) for c in self.config.clients.values()
                ),
            },
            "runtime": {
                "max_concurrent_requests": self.config.runtime.max_concurrent_requests,
                "health_check_enabled": self.config.runtime.health_check_enabled,
                "auto_restart_enabled": self.config.runtime.auto_restart_failed_servers,
            },
        }
