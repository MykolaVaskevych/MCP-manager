"""Access control middleware."""

import logging
from typing import Tuple, Union

import mcp.types as types

from .client_identifier import ClientIdentifier, ConnectionContext
from .permission_engine import PermissionEngine

logger = logging.getLogger(__name__)


class AccessControlMiddleware:
    """Middleware to enforce access control on all requests."""

    def __init__(
        self, permission_engine: PermissionEngine, identifier: ClientIdentifier
    ):
        self.permission_engine = permission_engine
        self.identifier = identifier

    async def process_request(
        self, request: types.ClientRequest, context: ConnectionContext
    ) -> Tuple[bool, Union[types.ServerResult, types.ErrorData, None]]:
        """
        Process request with access control.

        Returns:
            (allowed, response): If allowed is False, response contains error.
                               If allowed is True, response is None (continue processing).
        """

        # Identify client if not already done
        if not context.client_id:
            await self.identifier.identify_client(context)

        client_id = context.client_id or "default"

        # Handle different request types
        if isinstance(request, types.CallToolRequest):
            return await self._check_tool_call(request, client_id)
        elif isinstance(request, types.ReadResourceRequest):
            return await self._check_resource_read(request, client_id)
        elif isinstance(request, types.ListToolsRequest):
            # List requests are always allowed - filtering happens in response
            return True, None
        elif isinstance(request, types.ListResourcesRequest):
            # List requests are always allowed - filtering happens in response
            return True, None
        else:
            # Unknown request type, allow by default
            logger.warning(f"Unknown request type: {type(request)}")
            return True, None

    async def _check_tool_call(
        self, request: types.CallToolRequest, client_id: str
    ) -> Tuple[bool, Union[types.CallToolResult, types.ErrorData, None]]:
        """Check access for tool call request."""
        tool_name = request.params.name
        server_id, actual_tool_name = self._parse_namespaced_tool(tool_name)

        # Check permission
        if not await self.permission_engine.check_tool_access(
            client_id, server_id, actual_tool_name
        ):
            error = types.ErrorData(
                code=types.INVALID_REQUEST,
                message=f"Access denied to tool: {tool_name}",
            )
            return False, error

        return True, None

    async def _check_resource_read(
        self, request: types.ReadResourceRequest, client_id: str
    ) -> Tuple[bool, Union[types.ReadResourceResult, types.ErrorData, None]]:
        """Check access for resource read request."""
        resource_uri = request.params.uri
        server_id, actual_uri = self._parse_namespaced_resource(resource_uri)

        # Check permission
        if not await self.permission_engine.check_resource_access(
            client_id, server_id, actual_uri
        ):
            error = types.ErrorData(
                code=types.INVALID_REQUEST,
                message=f"Access denied to resource: {resource_uri}",
            )
            return False, error

        return True, None

    def _parse_namespaced_tool(self, tool_name: str) -> Tuple[str, str]:
        """Parse namespaced tool name into server_id and tool_name."""
        if "." in tool_name:
            server_id, actual_tool_name = tool_name.split(".", 1)
            return server_id, actual_tool_name
        else:
            # No namespace, assume default server or pass through
            return "default", tool_name

    def _parse_namespaced_resource(self, resource_uri: str) -> Tuple[str, str]:
        """Parse namespaced resource URI into server_id and actual URI."""
        if resource_uri.startswith("mcp://"):
            # Custom MCP URI format: mcp://server_id/actual_uri
            uri_parts = resource_uri[6:]  # Remove "mcp://" prefix
            if "/" in uri_parts:
                server_id, actual_uri = uri_parts.split("/", 1)
                return server_id, actual_uri
            else:
                return uri_parts, ""
        else:
            # No namespace, assume default server
            return "default", resource_uri
