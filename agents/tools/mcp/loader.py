"""Load MCP tools/resources/prompts via LangChain MCP adapters."""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from threading import Lock, Thread
from typing import Any, Coroutine, Iterable, TypeVar, cast

from Logging import get_logger
from agents.tools._registry import register_tool, list_tools

from .registry import (
    MCPServerConfig,
    ensure_mcp_config_loaded,
    get_mcp_server,
    list_mcp_servers,
)

logger = get_logger("agents.tools.mcp")


@dataclass
class _MCPBundle:
    signature: str
    server_names: tuple[str, ...]
    client: Any
    tools: list[Any] | None = None
    resources: list[Any] | None = None
    prompts: list[Any] | None = None


_MCP_CACHE_LOCK = Lock()
_MCP_BUNDLES: dict[tuple[str, ...], _MCPBundle] = {}
T = TypeVar("T")


def _signature_for(servers: Iterable[MCPServerConfig]) -> str:
    payload = [srv.cache_payload() for srv in servers]
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _select_servers(
    server_names: Iterable[str] | None,
    *,
    include_disabled: bool,
) -> list[MCPServerConfig]:
    ensure_mcp_config_loaded()

    if server_names:
        servers = [get_mcp_server(name) for name in server_names]
    else:
        servers = [get_mcp_server(name) for name in list_mcp_servers()]

    if not include_disabled:
        servers = [srv for srv in servers if srv.enabled]
    return servers


def _build_client_config(
    servers: Iterable[MCPServerConfig],
) -> dict[str, dict[str, Any]]:
    return {srv.name: srv.to_client_config() for srv in servers}


def _get_bundle(
    servers: Iterable[MCPServerConfig],
    *,
    refresh: bool,
) -> _MCPBundle:
    server_list = list(servers)
    names = tuple(sorted(srv.name for srv in server_list))
    signature = _signature_for(server_list)

    with _MCP_CACHE_LOCK:
        existing = _MCP_BUNDLES.get(names)
        if existing and not refresh and existing.signature == signature:
            return existing

        for key in list(_MCP_BUNDLES):
            if key == names:
                _MCP_BUNDLES.pop(key, None)

        try:
            from langchain_mcp_adapters.client import MultiServerMCPClient
        except ImportError as exc:  # pragma: no cover - dependency missing
            raise ImportError(
                "langchain-mcp-adapters is required for MCP tools. "
                "Install with `uv add langchain-mcp-adapters`."
            ) from exc

        client_config = _build_client_config(server_list)
        client = MultiServerMCPClient(cast(Any, client_config))
        bundle = _MCPBundle(signature=signature, server_names=names, client=client)
        _MCP_BUNDLES[names] = bundle
        return bundle


def _register_loaded_tools(tools: list[Any], *, category: str) -> None:
    existing = set(list_tools())
    for tool in tools:
        name = getattr(tool, "name", None)
        if not name:
            continue
        if name in existing:
            logger.warning(
                "Skipping MCP tool registration due to name collision: %s",
                name,
                action="mcp_tool_collision",
            )
            continue
        register_tool(tool, category=category)
        existing.add(name)


async def load_mcp_tools_async(
    *,
    server_names: Iterable[str] | None = None,
    include_disabled: bool = False,
    refresh: bool = False,
    strict: bool = False,
    register: bool = True,
    category: str = "mcp",
) -> list[Any]:
    """Async MCP tool loader."""
    servers = _select_servers(server_names, include_disabled=include_disabled)
    if not servers:
        return []

    try:
        bundle = _get_bundle(servers, refresh=refresh)
        if bundle.tools is not None and not refresh:
            return bundle.tools
        tools = await bundle.client.get_tools()
        bundle.tools = tools
        if register:
            _register_loaded_tools(tools, category=category)
        return tools
    except Exception as exc:
        logger.error(
            "Failed to load MCP tools: %s",
            exc,
            action="mcp_tools_failed",
        )
        if strict:
            raise
        return []


def _run_async(coro: Coroutine[Any, Any, T]) -> T:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: dict[str, Any] = {}

    def _runner() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except Exception as exc:  # pragma: no cover - event loop edge
            result["error"] = exc

    thread = Thread(target=_runner, daemon=True)
    thread.start()
    thread.join()
    if "error" in result:
        raise result["error"]
    if "value" not in result:
        raise RuntimeError("Async runner returned no value.")
    return cast(T, result["value"])


def load_mcp_tools(
    *,
    server_names: Iterable[str] | None = None,
    include_disabled: bool = False,
    refresh: bool = False,
    strict: bool = False,
    register: bool = True,
    category: str = "mcp",
) -> list[Any]:
    """Sync MCP tool loader."""
    return _run_async(
        load_mcp_tools_async(
            server_names=server_names,
            include_disabled=include_disabled,
            refresh=refresh,
            strict=strict,
            register=register,
            category=category,
        )
    )


async def load_mcp_resources_async(
    *,
    server_names: Iterable[str] | None = None,
    include_disabled: bool = False,
    refresh: bool = False,
    strict: bool = False,
) -> list[Any]:
    """Async MCP resources loader."""
    servers = _select_servers(server_names, include_disabled=include_disabled)
    if not servers:
        return []

    try:
        bundle = _get_bundle(servers, refresh=refresh)
        if bundle.resources is not None and not refresh:
            return bundle.resources
        resources = await bundle.client.get_resources()
        bundle.resources = resources
        return resources
    except Exception as exc:
        logger.error(
            "Failed to load MCP resources: %s",
            exc,
            action="mcp_resources_failed",
        )
        if strict:
            raise
        return []


def load_mcp_resources(
    *,
    server_names: Iterable[str] | None = None,
    include_disabled: bool = False,
    refresh: bool = False,
    strict: bool = False,
) -> list[Any]:
    """Sync MCP resources loader."""
    return _run_async(
        load_mcp_resources_async(
            server_names=server_names,
            include_disabled=include_disabled,
            refresh=refresh,
            strict=strict,
        )
    )


async def load_mcp_prompts_async(
    *,
    server_names: Iterable[str] | None = None,
    include_disabled: bool = False,
    refresh: bool = False,
    strict: bool = False,
) -> list[Any]:
    """Async MCP prompts loader."""
    servers = _select_servers(server_names, include_disabled=include_disabled)
    if not servers:
        return []

    try:
        bundle = _get_bundle(servers, refresh=refresh)
        if bundle.prompts is not None and not refresh:
            return bundle.prompts
        prompts = await bundle.client.get_prompts()
        bundle.prompts = prompts
        return prompts
    except Exception as exc:
        logger.error(
            "Failed to load MCP prompts: %s",
            exc,
            action="mcp_prompts_failed",
        )
        if strict:
            raise
        return []


def load_mcp_prompts(
    *,
    server_names: Iterable[str] | None = None,
    include_disabled: bool = False,
    refresh: bool = False,
    strict: bool = False,
) -> list[Any]:
    """Sync MCP prompts loader."""
    return _run_async(
        load_mcp_prompts_async(
            server_names=server_names,
            include_disabled=include_disabled,
            refresh=refresh,
            strict=strict,
        )
    )
