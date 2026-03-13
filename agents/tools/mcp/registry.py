"""MCP server registry and config normalization."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from threading import RLock
from typing import Any, Iterable, Mapping

from Logging import get_logger
from env import config

logger = get_logger("agents.tools.mcp")


@dataclass(frozen=True)
class MCPServerConfig:
    """Normalized MCP server configuration.

    This is intentionally close to the LangChain MCP client schema so we can
    pass it through with minimal translation.
    """

    name: str
    transport: str
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    auth: Any | None = None
    enabled: bool = True
    description: str | None = None
    source: str = "code"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_client_config(self) -> dict[str, Any]:
        """Convert to a MultiServerMCPClient-compatible config dict."""
        payload: dict[str, Any] = {"transport": self.transport}

        if self.transport == "stdio":
            if not self.command:
                raise ValueError(
                    f"MCP server {self.name!r} uses stdio but has no command."
                )
            payload["command"] = self.command
            if self.args:
                payload["args"] = list(self.args)
            if self.env:
                payload["env"] = dict(self.env)
        else:
            if not self.url:
                raise ValueError(
                    f"MCP server {self.name!r} uses {self.transport!r} but has no url."
                )
            payload["url"] = self.url
            if self.headers:
                payload["headers"] = dict(self.headers)
            if self.auth is not None:
                payload["auth"] = self.auth

        for key, value in self.metadata.items():
            if key not in payload:
                payload[key] = value
        return payload

    def cache_payload(self) -> dict[str, Any]:
        """Return a JSON-safe payload for caching/signature checks."""
        auth_key = None
        if self.auth is not None:
            auth_key = (
                f"{self.auth.__class__.__module__}.{self.auth.__class__.__name__}"
            )
        return {
            "name": self.name,
            "transport": self.transport,
            "command": self.command,
            "args": list(self.args),
            "env": dict(self.env),
            "url": self.url,
            "headers": dict(self.headers),
            "auth": auth_key,
            "enabled": self.enabled,
            "metadata": dict(self.metadata),
        }


_MCP_REGISTRY: dict[str, MCPServerConfig] = {}
_MCP_REGISTRY_LOCK = RLock()
_MCP_CONFIG_LOADED = False


def _normalize_transport(raw: str | None) -> str | None:
    if raw is None:
        return None
    cleaned = re.sub(r"[^a-z0-9]+", "", raw.strip().lower())
    if not cleaned:
        return None
    if cleaned in ("streamablehttp", "http"):
        return "http"
    if cleaned in ("sse", "serversentevents", "eventsource"):
        return "sse"
    if cleaned == "stdio":
        return "stdio"
    return raw.strip().lower()


def _stringify_map(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    return {str(k): str(v) for k, v in value.items()}


def normalize_mcp_server_config(
    name: str,
    raw: Mapping[str, Any],
    *,
    enabled: bool | None = None,
    source: str = "code",
) -> MCPServerConfig:
    """Normalize raw MCP config (code or JSON) into MCPServerConfig."""
    data = dict(raw)

    description = data.get("description")
    if not description:
        description = data.get("name")

    if enabled is None:
        enabled = bool(
            data.get("enabled", data.get("isActive", data.get("active", True)))
        )

    transport_info = data.get("transport")
    transport = None
    url = None
    headers = None

    if isinstance(transport_info, Mapping):
        transport = transport_info.get("type") or transport_info.get("name")
        url = transport_info.get("url") or transport_info.get("baseUrl")
        if url is None:
            url = transport_info.get("base_url")
        headers = transport_info.get("headers")
    elif isinstance(transport_info, str):
        transport = transport_info

    if transport is None:
        transport = data.get("type") or data.get("transport")

    url = url or data.get("url") or data.get("baseUrl") or data.get("base_url")
    headers = headers or data.get("headers")

    command = data.get("command")
    args = data.get("args") or []
    env = data.get("env") or {}
    auth = data.get("auth")

    normalized_transport = _normalize_transport(transport)
    if normalized_transport is None:
        if command:
            normalized_transport = "stdio"
        elif url:
            normalized_transport = "http"

    if normalized_transport is None:
        raise ValueError(
            f"MCP server {name!r} missing transport info (type/transport/command/url)."
        )

    args_list = [str(arg) for arg in (args or [])]
    env_map = _stringify_map(env)
    header_map = _stringify_map(headers)

    reserved = {
        "transport",
        "type",
        "url",
        "baseUrl",
        "base_url",
        "command",
        "args",
        "env",
        "headers",
        "auth",
        "name",
        "description",
        "enabled",
        "isActive",
        "active",
    }
    metadata = {k: v for k, v in data.items() if k not in reserved}

    return MCPServerConfig(
        name=name,
        transport=normalized_transport,
        command=str(command) if command else None,
        args=args_list,
        env=env_map,
        url=str(url) if url else None,
        headers=header_map,
        auth=auth,
        enabled=bool(enabled),
        description=str(description) if description else None,
        source=source,
        metadata=metadata,
    )


def register_mcp_server(
    name: str,
    config_data: Mapping[str, Any] | MCPServerConfig,
    *,
    enabled: bool | None = None,
    source: str = "code",
    overwrite: bool = True,
) -> MCPServerConfig:
    """Register an MCP server definition."""
    if isinstance(config_data, MCPServerConfig):
        if config_data.name != name:
            raise ValueError(
                f"MCP server name mismatch: {name!r} != {config_data.name!r}"
            )
        server = config_data
        if enabled is not None or source != server.source:
            server = replace(
                server,
                enabled=server.enabled if enabled is None else enabled,
                source=source,
            )
    else:
        server = normalize_mcp_server_config(
            name,
            config_data,
            enabled=enabled,
            source=source,
        )

    with _MCP_REGISTRY_LOCK:
        if not overwrite and name in _MCP_REGISTRY:
            return _MCP_REGISTRY[name]
        _MCP_REGISTRY[name] = server

    logger.info(
        "Registered MCP server  name=%s transport=%s enabled=%s source=%s",
        name,
        server.transport,
        server.enabled,
        server.source,
        action="mcp_register",
        meta={"name": name, "transport": server.transport, "enabled": server.enabled},
    )
    return server


def register_mcp_servers(
    servers: Mapping[str, Mapping[str, Any] | MCPServerConfig],
    *,
    source: str = "code",
    overwrite: bool = True,
) -> list[MCPServerConfig]:
    """Register multiple MCP servers at once."""
    registered: list[MCPServerConfig] = []
    for name, payload in servers.items():
        registered.append(
            register_mcp_server(
                name,
                payload,
                source=source,
                overwrite=overwrite,
            )
        )
    return registered


def list_mcp_servers(*, include_disabled: bool = True) -> list[str]:
    """List registered MCP server names."""
    with _MCP_REGISTRY_LOCK:
        items = list(_MCP_REGISTRY.values())
    if not include_disabled:
        items = [cfg for cfg in items if cfg.enabled]
    return sorted(cfg.name for cfg in items)


def get_mcp_server(name: str) -> MCPServerConfig:
    """Get a registered MCP server config."""
    with _MCP_REGISTRY_LOCK:
        server = _MCP_REGISTRY.get(name)
    if server is None:
        available = ", ".join(list_mcp_servers()) or "(none)"
        raise KeyError(f"Unknown MCP server: {name!r}. Registered: {available}")
    return server


def enable_mcp_server(name: str) -> MCPServerConfig:
    """Enable a registered MCP server."""
    with _MCP_REGISTRY_LOCK:
        server = _MCP_REGISTRY.get(name)
        if server is None:
            available = ", ".join(list_mcp_servers()) or "(none)"
            raise KeyError(f"Unknown MCP server: {name!r}. Registered: {available}")
        updated = replace(server, enabled=True)
        _MCP_REGISTRY[name] = updated
    return updated


def disable_mcp_server(name: str) -> MCPServerConfig:
    """Disable a registered MCP server."""
    with _MCP_REGISTRY_LOCK:
        server = _MCP_REGISTRY.get(name)
        if server is None:
            available = ", ".join(list_mcp_servers()) or "(none)"
            raise KeyError(f"Unknown MCP server: {name!r}. Registered: {available}")
        updated = replace(server, enabled=False)
        _MCP_REGISTRY[name] = updated
    return updated


def load_mcp_servers_from_file(
    path: str | Path, *, overwrite: bool = True
) -> list[MCPServerConfig]:
    """Load MCP servers from a JSON config file (Claude-style mcpServers)."""
    resolved = Path(path)
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    servers = payload.get("mcpServers") or payload.get("mcp_servers") or {}
    if not isinstance(servers, Mapping):
        raise ValueError("MCP config file must contain a 'mcpServers' mapping.")

    return register_mcp_servers(
        servers,
        source=str(resolved),
        overwrite=overwrite,
    )


def ensure_mcp_config_loaded() -> None:
    """Load MCP servers from MCP_CONFIG_PATH once (if set)."""
    global _MCP_CONFIG_LOADED
    if _MCP_CONFIG_LOADED:
        return
    _MCP_CONFIG_LOADED = True

    path = config.MCP_CONFIG_PATH
    if not path:
        return

    try:
        load_mcp_servers_from_file(path)
        logger.info(
            "Loaded MCP config from %s",
            path,
            action="mcp_config_load",
        )
    except Exception as exc:
        logger.warning(
            "Failed to load MCP config from %s: %s",
            path,
            exc,
            action="mcp_config_load_failed",
        )
