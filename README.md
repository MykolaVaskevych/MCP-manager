# MCP Manager

A centralized [Model Context Protocol](https://modelcontextprotocol.io/) server management and routing system built before Docker MCP Toolkit existed as an official solution. Manages multiple MCP servers through a single interface with fine-grained per-client access control.

## Features

- **Centralized Management**: Manage multiple MCP servers from a single YAML config
- **Access Control**: Rule-based allow/deny permissions per client (VSCode, Claude Desktop, etc.)
- **Auto-Installation**: Automatic discovery and installation from NPM, GitHub, or local sources
- **Hot Reload**: Configuration changes without service restart
- **Health Monitoring**: Automatic health checks and server restart
- **Request Routing**: Intelligent routing to appropriate backend servers
- **Response Caching**: Configurable TTL for performance
- **CLI**: Full command-line interface for management operations

## Quick Start

```bash
uv sync
cp mcp-manager.example.yaml mcp-manager.yaml
# edit mcp-manager.yaml
mcp-manager start --config mcp-manager.yaml
```

Connect your MCP clients (VSCode, Claude Desktop, etc.) to the manager instead of individual servers.

## Configuration

```yaml
manager:
  name: "central-mcp-manager"
  log_level: "info"

servers:
  weather:
    source: "npm:@weather/mcp-weather"
    transport: "stdio"
    auto_install: true

  filesystem:
    source: "github:anthropics/mcp-filesystem"
    transport: "stdio"
    config:
      allowed_paths: ["/home/user/documents"]

clients:
  vscode:
    identify_by:
      - client_info.name: "vscode-mcp"
    allow:
      - server: "filesystem"
        tools: ["read_file", "write_file"]
    deny:
      - server: "weather"

  claude_desktop:
    identify_by:
      - client_info.name: "claude-desktop"
    allow:
      - server: "weather"
        tools: ["get_weather"]
      - server: "filesystem"
        tools: ["read_file"]
```

## Client Integration

### VSCode

```json
{
  "mcp.servers": {
    "manager": {
      "command": "python",
      "args": ["/path/to/MCP-manager/main.py", "/path/to/mcp-manager.yaml"],
      "transport": "stdio"
    }
  }
}
```

### Claude Desktop

```json
{
  "mcpServers": {
    "manager": {
      "command": "python",
      "args": ["/path/to/MCP-manager/main.py", "/path/to/mcp-manager.yaml"],
      "transport": "stdio"
    }
  }
}
```

## CLI

```bash
mcp-manager start --config mcp-manager.yaml
mcp-manager status
mcp-manager server list
mcp-manager server install weather
mcp-manager client permissions vscode
mcp-manager config validate
mcp-manager config show
```

## Architecture

```
[MCP Client] <---> [MCP Manager] <---> [MCP Server 1]
                        |
                        +-----------> [MCP Server 2]
                        |
                        +-----------> [MCP Server N]
```

The manager acts as both an MCP server (exposes tools to clients) and an MCP client (connects to backend servers).

```
mcp_manager/
├── config/       # Configuration management
├── server/       # MCP server lifecycle
├── access/       # Access control
├── routing/      # Request routing
├── installers/   # Auto-installation
├── cli/          # CLI
└── core/         # Main application
```

## Supported Server Sources

- `npm:package-name` or `npm:@scope/package-name`
- `github:owner/repo` (optional branch)
- `local:/absolute/path` or `local:./relative/path`

## License

MIT
