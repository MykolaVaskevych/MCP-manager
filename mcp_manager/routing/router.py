"""Main request routing engine."""

import asyncio
import logging
from typing import Dict, Tuple, Union

import mcp.types as types

from ..access.client_identifier import ConnectionContext
from ..access.permission_engine import PermissionEngine
from ..server.manager import MCPServerManager
from .aggregator import ResponseAggregator
from .cache import ResponseCache

logger = logging.getLogger(__name__)


class MCPRouter:
    """Main routing engine for MCP requests."""

    def __init__(
        self, server_manager: MCPServerManager, permission_engine: PermissionEngine
    ):
        self.server_manager = server_manager
        self.permission_engine = permission_engine
        self.aggregator = ResponseAggregator(server_manager)
        self.cache = ResponseCache()

    async def start(self) -> None:
        """Start the router and its components."""
        await self.cache.start()

    async def stop(self) -> None:
        """Stop the router and its components."""
        await self.cache.stop()

    async def route_request(
        self, request: types.ClientRequest, context: ConnectionContext
    ) -> types.ServerResult:
        """Main routing logic for all MCP requests."""

        client_id = context.client_id or "default"

        try:
            if isinstance(request, types.CallToolRequest):
                return await self._route_tool_call(request, client_id)
            elif isinstance(request, types.ListToolsRequest):
                return await self._route_list_tools(request, client_id)
            elif isinstance(request, types.ReadResourceRequest):
                return await self._route_read_resource(request, client_id)
            elif isinstance(request, types.ListResourcesRequest):
                return await self._route_list_resources(request, client_id)
            elif isinstance(request, types.ListPromptsRequest):
                return await self._route_list_prompts(request, client_id)
            elif isinstance(request, types.GetPromptRequest):
                return await self._route_get_prompt(request, client_id)
            else:
                return types.ErrorData(
                    code=types.METHOD_NOT_FOUND,
                    message=f"Unsupported request type: {type(request).__name__}",
                )

        except Exception as e:
            logger.error(f"Routing error for {type(request).__name__}: {e}")
            return types.ErrorData(
                code=types.INTERNAL_ERROR, message=f"Internal routing error: {str(e)}"
            )

    async def _route_tool_call(
        self, request: types.CallToolRequest, client_id: str
    ) -> Union[types.CallToolResult, types.ErrorData]:
        """Route tool call to appropriate backend server."""
        tool_name = request.params.name
        server_id, actual_tool_name = self._parse_namespaced_tool(tool_name)

        # Check cache first (for idempotent operations)
        cache_key = self.cache.generate_cache_key(
            server_id,
            "call_tool",
            {"name": actual_tool_name, "arguments": request.params.arguments},
        )

        cached_result = await self.cache.get(cache_key)
        if cached_result:
            logger.debug(f"Returning cached result for tool call: {tool_name}")
            return cached_result

        # Route to backend server
        try:
            result = await asyncio.wait_for(
                self.server_manager.call_tool(
                    server_id, actual_tool_name, request.params.arguments
                ),
                timeout=30.0,
            )

            # Cache successful results (avoid caching errors)
            if isinstance(result, types.CallToolResult):
                await self.cache.set(cache_key, result, ttl=300)  # 5 minute cache

            return result

        except asyncio.TimeoutError:
            return types.ErrorData(
                code=types.INTERNAL_ERROR, message=f"Tool call timeout: {tool_name}"
            )
        except ValueError as e:
            # Server not found or not running
            return types.ErrorData(code=types.INVALID_REQUEST, message=str(e))
        except Exception as e:
            return types.ErrorData(
                code=types.INTERNAL_ERROR, message=f"Backend error: {str(e)}"
            )

    async def _route_list_tools(
        self, request: types.ListToolsRequest, client_id: str
    ) -> Union[types.ListToolsResult, types.ErrorData]:
        """Route list tools request - aggregate from all servers."""
        try:
            # Check cache first (disabled for debugging)
            # cache_key = self.cache.generate_cache_key("all", "list_tools", client_id)
            # cached_result = await self.cache.get(cache_key)
            # if cached_result:
            #     return cached_result

            # Aggregate tools from all servers
            all_tools = await self.aggregator.aggregate_tools(client_id)
            logger.info(f"Aggregated tools: {all_tools}")
            logger.info(
                f"First tool type: {type(all_tools[0]) if all_tools else 'None'}"
            )

            # Filter based on client permissions
            filtered_tools = []
            for tool in all_tools:
                logger.info(f"Processing tool: {tool}, type: {type(tool)}")
                server_id, actual_tool_name = self._parse_namespaced_tool(tool.name)
                if await self.permission_engine.check_tool_access(
                    client_id, server_id, actual_tool_name
                ):
                    filtered_tools.append(tool)

            logger.info(f"Creating ListToolsResult with {len(filtered_tools)} tools")
            result = types.ListToolsResult(tools=filtered_tools)

            # Cache the result (disabled for debugging)
            # await self.cache.set(cache_key, result, ttl=60)  # 1 minute cache

            return result

        except Exception as e:
            return types.ErrorData(
                code=types.INTERNAL_ERROR, message=f"Error listing tools: {str(e)}"
            )

    async def _route_read_resource(
        self, request: types.ReadResourceRequest, client_id: str
    ) -> Union[types.ReadResourceResult, types.ErrorData]:
        """Route resource read to appropriate backend server."""
        resource_uri = request.params.uri
        server_id, actual_uri = self._parse_namespaced_resource(resource_uri)

        # Check cache first
        cache_key = self.cache.generate_cache_key(
            server_id, "read_resource", actual_uri
        )
        cached_result = await self.cache.get(cache_key)
        if cached_result:
            return cached_result

        try:
            result = await asyncio.wait_for(
                self.server_manager.read_resource(server_id, actual_uri), timeout=30.0
            )

            # Cache successful results
            if isinstance(result, types.ReadResourceResult):
                await self.cache.set(cache_key, result, ttl=300)  # 5 minute cache

            return result

        except asyncio.TimeoutError:
            return types.ErrorData(
                code=types.INTERNAL_ERROR,
                message=f"Resource read timeout: {resource_uri}",
            )
        except ValueError as e:
            return types.ErrorData(code=types.INVALID_REQUEST, message=str(e))
        except Exception as e:
            return types.ErrorData(
                code=types.INTERNAL_ERROR, message=f"Backend error: {str(e)}"
            )

    async def _route_list_resources(
        self, request: types.ListResourcesRequest, client_id: str
    ) -> Union[types.ListResourcesResult, types.ErrorData]:
        """Route list resources request - aggregate from all servers."""
        try:
            # Check cache first
            cache_key = self.cache.generate_cache_key(
                "all", "list_resources", client_id
            )
            cached_result = await self.cache.get(cache_key)
            if cached_result:
                return cached_result

            # Aggregate resources from all servers
            all_resources = await self.aggregator.aggregate_resources(client_id)

            # Filter based on client permissions
            filtered_resources = []
            for resource in all_resources:
                server_id, actual_uri = self._parse_namespaced_resource(resource.uri)
                if await self.permission_engine.check_resource_access(
                    client_id, server_id, actual_uri
                ):
                    filtered_resources.append(resource)

            result = types.ListResourcesResult(resources=filtered_resources)

            # Cache the result
            await self.cache.set(cache_key, result, ttl=60)  # 1 minute cache

            return result

        except Exception as e:
            return types.ErrorData(
                code=types.INTERNAL_ERROR, message=f"Error listing resources: {str(e)}"
            )

    async def _route_list_prompts(
        self, request: types.ListPromptsRequest, client_id: str
    ) -> Union[types.ListPromptsResult, types.ErrorData]:
        """Route list prompts request - aggregate from all servers."""
        try:
            # Check cache first
            cache_key = self.cache.generate_cache_key("all", "list_prompts", client_id)
            cached_result = await self.cache.get(cache_key)
            if cached_result:
                return cached_result

            # Aggregate prompts from all servers
            all_prompts = await self.aggregator.aggregate_prompts(client_id)

            result = types.ListPromptsResult(prompts=all_prompts)

            # Cache the result
            await self.cache.set(cache_key, result, ttl=60)  # 1 minute cache

            return result

        except Exception as e:
            return types.ErrorData(
                code=types.INTERNAL_ERROR, message=f"Error listing prompts: {str(e)}"
            )

    async def _route_get_prompt(
        self, request: types.GetPromptRequest, client_id: str
    ) -> Union[types.GetPromptResult, types.ErrorData]:
        """Route get prompt to appropriate backend server."""
        prompt_name = request.params.name
        server_id, actual_prompt_name = self._parse_namespaced_tool(
            prompt_name
        )  # Same parsing logic

        try:
            # This would need to be implemented in the server manager
            # For now, return not implemented
            return types.ErrorData(
                code=types.METHOD_NOT_FOUND, message="Get prompt not yet implemented"
            )

        except Exception as e:
            return types.ErrorData(
                code=types.INTERNAL_ERROR, message=f"Error getting prompt: {str(e)}"
            )

    def _parse_namespaced_tool(self, tool_name: str) -> Tuple[str, str]:
        """Parse namespaced tool name into server_id and tool_name."""
        if "." in tool_name:
            server_id, actual_tool_name = tool_name.split(".", 1)
            return server_id, actual_tool_name
        else:
            # No namespace, need to find which server has this tool
            # For now, return error
            raise ValueError(f"Tool name must be namespaced: {tool_name}")

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
            # No namespace, need to find which server has this resource
            raise ValueError(f"Resource URI must be namespaced: {resource_uri}")

    def get_stats(self) -> Dict:
        """Get routing statistics."""
        return {
            "cache_stats": self.cache.get_stats(),
            "active_servers": len(self.server_manager.get_active_sessions()),
            "server_status": self.server_manager.get_all_status(),
        }
