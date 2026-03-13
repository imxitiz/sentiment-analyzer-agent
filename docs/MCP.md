# MCP Integration

This project supports the Model Context Protocol (MCP) for attaching external
tools/resources/prompts to agents. We integrate MCP via LangChain's
`langchain-mcp-adapters` package and expose MCP tools just like built-in
LangChain tools.

## What We Support

- Stdio MCP servers (spawned as subprocesses)
- HTTP MCP servers (streamable HTTP)
- MCP tools in agent tool loops (React agents)
- Optional access to MCP resources and prompts
- Future-ready JSON config loading (Claude-style `mcpServers`)

## Dependencies

Install/update dependencies:

```bash
uv sync
```

MCP tooling depends on `langchain-mcp-adapters` (added to `pyproject.toml`).

## Key Modules

- `agents/tools/mcp/registry.py` is the MCP server registry and config parser.
- `agents/tools/mcp/loader.py` loads tools/resources/prompts from MCP servers.
- `agents/tools/mcp/servers/` contains built-in MCP server registrations.

## Register MCP Servers in Code

Register a server once, then enable it when you want to use it.

```python
from agents.tools.mcp import register_mcp_server, enable_mcp_server

register_mcp_server(
    "my_mcp_http",
    {
        "transport": "http",
        "url": "http://localhost:3333/mcp",
        "headers": {"Authorization": "Bearer TOKEN"},
    },
    enabled=False,
)

enable_mcp_server("my_mcp_http")
```

Stdio example:

```python
register_mcp_server(
    "my_mcp_stdio",
    {
        "transport": "stdio",
        "command": "python",
        "args": ["-m", "my_mcp_server"],
        "env": {"MY_API_KEY": "xyz"},
    },
)
```

## Load MCP Tools and Use in Agents

MCP tools load as regular LangChain tools.

```python
from agents.tools.mcp import load_mcp_tools
from agents.orchestrator import OrchestratorAgent

tools = load_mcp_tools()
agent = OrchestratorAgent(extra_tools=tools)
```

You can also enable MCP tools directly on any agent:

```python
agent = OrchestratorAgent(mcp_enabled=True)
```

Use `mcp_server_names=[...]` to limit which MCP servers are loaded.

## mcp.json Support (Optional)

We support Claude-style config files with `mcpServers`.

```json
{
  "mcpServers": {
    "web-search": {
      "type": "http",
      "url": "http://localhost:3000/mcp"
    }
  }
}
```

Load this file manually:

```python
from agents.tools.mcp import load_mcp_servers_from_file

load_mcp_servers_from_file("mcp.json")
```

Or set `MCP_CONFIG_PATH` in your environment to auto-load when MCP tools are
first requested:

```bash
export MCP_CONFIG_PATH=/path/to/mcp.json
```

The loader accepts multiple config shapes, including nested `transport` blocks:

```json
{
  "mcpServers": {
    "web-search": {
      "transport": {
        "type": "streamableHttp",
        "url": "http://localhost:3000/mcp"
      }
    }
  }
}
```

## Open WebSearch MCP (Example)

We ship two disabled entries in `agents/tools/mcp/servers/open_websearch.py`:

- `open_websearch_stdio`
- `open_websearch_http`

This server requires Node.js (npx).

Enable one, then run the server:

Stdio:

```bash
MODE=stdio npx -y open-websearch@latest
```

HTTP:

```bash
MODE=http PORT=3000 npx -y open-websearch@latest
```

Then enable the corresponding MCP server:

```python
from agents.tools.mcp import enable_mcp_server

enable_mcp_server("open_websearch_stdio")
```

## Notes

- MCP tools are registered under the `mcp` category in the tool registry.
- Tool name collisions are detected; colliding tools are skipped in the
  registry but still usable if directly attached to an agent.
- MCP failures are non-fatal by default; pass `mcp_strict=True` to raise.
