"""Configuration data models."""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class HealthCheckConfig(BaseModel):
    method: Literal["tool_call", "ping"] = "ping"
    tool: Optional[str] = None
    args: Optional[Dict[str, Any]] = None
    interval: int = 300  # seconds
    timeout: int = 10


class ServerConfig(BaseModel):
    source: str  # npm:package, github:repo, local:path
    version: Optional[str] = None
    branch: Optional[str] = None
    transport: Literal["stdio", "sse", "websocket"] = "stdio"
    endpoint: Optional[str] = None  # For SSE/WebSocket
    config: Optional[Dict[str, Any]] = Field(default_factory=dict)
    health_check: Optional[HealthCheckConfig] = None
    auto_install: bool = True
    enabled: bool = True


class AccessRule(BaseModel):
    server: str
    tools: Optional[List[str]] = None  # None means all tools
    resources: Optional[List[str]] = None  # None means all resources


class ClientRule(BaseModel):
    identify_by: List[Dict[str, str]]
    allow: List[AccessRule] = Field(default_factory=list)
    deny: List[AccessRule] = Field(default_factory=list)
    deny_all_except_allowed: bool = False


class ManagerConfig(BaseModel):
    name: str = "mcp-manager"
    version: str = "1.0.0"
    port: Optional[int] = None  # For HTTP-based management
    log_level: Literal["debug", "info", "warning", "error"] = "info"


class SourceConfig(BaseModel):
    registry: Optional[str] = None
    base_url: Optional[str] = None
    auth_token: Optional[str] = None
    base_path: Optional[str] = None


class RuntimeConfig(BaseModel):
    max_concurrent_requests: int = 100
    request_timeout: int = 30
    backend_pool_size: int = 10
    health_check_enabled: bool = True
    metrics_enabled: bool = True
    auto_restart_failed_servers: bool = True
    cache_ttl: int = 300  # seconds


class MCPManagerConfig(BaseModel):
    manager: ManagerConfig = Field(default_factory=ManagerConfig)
    servers: Dict[str, ServerConfig] = Field(default_factory=dict)
    clients: Dict[str, ClientRule] = Field(default_factory=dict)
    sources: Dict[str, SourceConfig] = Field(default_factory=dict)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
