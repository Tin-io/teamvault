"""TeamVault MCP server — stdio transport for Claude Code / Codex.

Exposes six tools to the host agent, each an HTTP shim to the sidecar:
  - vault_search(query, top_k=10, purpose=None)   # purpose v0.1+ — audit signal
  - vault_publish(slug, content, tags=[])
  - vault_status()
  - vault_packs()                                 # v0.1+ — knowledge_topics surface
  - vault_cite(query_id, paths_used=[], note=None)# v0.1+ — closes the search→cite loop
  - vault_query_log(since, until, action, limit)  # v0.1+ — retrospective surface

Launched by the host (Claude Code) via the MCP server registration.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

from sidecar import config


SIDECAR_URL = os.environ.get("TEAMVAULT_SIDECAR_URL", f"http://localhost:{config.TEAMVAULT_PORT}")


class NoSpaceRegistered(RuntimeError):
    """Raised when the sidecar has no spaces registered and no override was given."""


def _default_space() -> str:
    """Resolve active space. Order: env override → only registered space → error.

    Fails loudly if no space is registered, so the host sees a real error instead of
    queries silently routing to a non-existent "default" space.
    """
    import httpx

    if env := os.environ.get("TEAMVAULT_SPACE"):
        return env
    r = httpx.get(f"{SIDECAR_URL}/healthz", timeout=5)
    r.raise_for_status()
    spaces = r.json().get("spaces") or []
    if not spaces:
        raise NoSpaceRegistered(
            f"sidecar at {SIDECAR_URL} has no spaces registered. "
            f"Did you set TEAMVAULT_SPACE_ROOT and ensure space.yaml exists?"
        )
    return spaces[0]["name"]


def _build_server():
    try:
        from mcp.server import Server
        import mcp.types as types
    except ImportError:
        print("ERROR: mcp package not installed. pip install mcp", file=sys.stderr)
        sys.exit(1)

    server = Server("teamvault")

    @server.list_tools()
    async def _tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="vault_search",
                description=(
                    "Hybrid (BM25 + vector + RRF) search over the team's TeamVault KB. "
                    "Returns a `query_id` (use it with `vault_cite` to record which results "
                    "shaped your decision) and ranked chunks with scores and source paths. "
                    "Use when the user asks about past decisions, team policies, prior incidents, "
                    "or 'how did we handle X before'. Pass `purpose` to record what you're "
                    "trying to decide — the audit log captures it verbatim for retrospectives."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Natural-language query"},
                        "top_k": {"type": "integer", "default": 10, "description": "Max hits (default 10)"},
                        "purpose": {
                            "type": "string",
                            "description": (
                                "Free-text statement of what you're trying to decide or accomplish "
                                "with this query. Recorded verbatim in the audit log for "
                                "retrospective review."
                            ),
                        },
                    },
                    "required": ["query"],
                },
            ),
            types.Tool(
                name="vault_publish",
                description=(
                    "Write a new entry to the team's TeamVault KB. Markdown body + YAML frontmatter. "
                    "Sidecar commits, pushes (unless dry-run), and reindexes. Use when the user wants "
                    "to publish a note, decision, postmortem, or finding for the team."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "slug": {"type": "string", "description": "Short kebab-case identifier"},
                        "content": {"type": "string", "description": "Markdown body"},
                        "tags": {"type": "array", "items": {"type": "string"}, "default": []},
                    },
                    "required": ["slug", "content"],
                },
            ),
            types.Tool(
                name="vault_status",
                description=(
                    "Return TeamVault sidecar status: version, registered spaces, last pull times, "
                    "last errors. Use to diagnose connectivity or sync issues."
                ),
                inputSchema={"type": "object", "properties": {}},
            ),
            types.Tool(
                name="vault_packs",
                description=(
                    "Return the knowledge domains this team's TeamVault has accumulated "
                    "prior art on. Call this at the start of any substantive task to "
                    "learn which domains warrant a `vault_search` before finalizing "
                    "decisions. Each pack's `knowledge_topics` is the team's declaration "
                    "of 'we care about this domain' — search the KB before finalizing a "
                    "decision that touches one of these topics."
                ),
                inputSchema={"type": "object", "properties": {}},
            ),
            types.Tool(
                name="vault_cite",
                description=(
                    "Record which KB entries informed (or didn't inform) a decision after a "
                    "`vault_search`. Call this AFTER applying or rejecting search results. "
                    "`paths_used=[]` is valid and means 'I searched and nothing was useful.' This "
                    "closes the audit loop and lets the team later see which KB entries "
                    "actually shaped decisions vs. which were retrieved but ignored. Always cite "
                    "when you searched before a substantive decision — even when the result was "
                    "'nothing useful.'"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query_id": {
                            "type": "string",
                            "description": "UUID4 hex returned by a prior vault_search.",
                        },
                        "paths_used": {
                            "type": "array",
                            "items": {"type": "string"},
                            "default": [],
                            "description": "Paths of KB entries that informed the decision. Empty = 'nothing useful.'",
                        },
                        "note": {
                            "type": "string",
                            "description": "Optional free-text rationale (what shaped the decision, what was missing).",
                        },
                    },
                    "required": ["query_id"],
                },
            ),
            types.Tool(
                name="vault_query_log",
                description=(
                    "Review what the team (or this session) has searched, cited, and published in "
                    "the TeamVault KB recently. Useful for retrospectives ('we searched X 5 times "
                    "and never cited a result — KB gap'), end-of-task summaries, and "
                    "pre-task orientation ('what was the last session looking into?'). Returns "
                    "audit rows; cross-reference search rows with cite rows via `metadata.query_id`."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "since": {
                            "type": "string",
                            "description": "ISO 8601 lower bound on entry ts (inclusive).",
                        },
                        "until": {
                            "type": "string",
                            "description": "ISO 8601 upper bound on entry ts (inclusive).",
                        },
                        "action": {
                            "type": "string",
                            "description": (
                                "Comma-separated whitelist of actions. Default: "
                                "search,cite,publish,publish_blocked."
                            ),
                        },
                        "limit": {
                            "type": "integer",
                            "default": 50,
                            "description": "Max rows returned, capped at 500. Keeps the most recent.",
                        },
                    },
                },
            ),
        ]

    @server.call_tool()
    async def _call(name: str, arguments: dict[str, Any] | None) -> list[types.TextContent]:
        import httpx

        args = arguments or {}
        space = _default_space()
        try:
            if name == "vault_search":
                r = httpx.post(
                    f"{SIDECAR_URL}/search",
                    json={
                        "query": args["query"],
                        "top_k": args.get("top_k", 10),
                        "space": space,
                        "purpose": args.get("purpose"),
                    },
                    timeout=30,
                )
                r.raise_for_status()
                return [types.TextContent(type="text", text=json.dumps(r.json(), indent=2))]

            if name == "vault_publish":
                r = httpx.post(
                    f"{SIDECAR_URL}/publish",
                    json={
                        "space": space,
                        "slug": args["slug"],
                        "content": args["content"],
                        "frontmatter": {"tags": args.get("tags") or []},
                    },
                    timeout=30,
                )
                r.raise_for_status()
                return [types.TextContent(type="text", text=json.dumps(r.json(), indent=2))]

            if name == "vault_status":
                r = httpx.get(f"{SIDECAR_URL}/healthz", timeout=5)
                r.raise_for_status()
                return [types.TextContent(type="text", text=json.dumps(r.json(), indent=2))]

            if name == "vault_packs":
                r = httpx.get(f"{SIDECAR_URL}/packs", params={"space": space}, timeout=5)
                r.raise_for_status()
                return [types.TextContent(type="text", text=json.dumps(r.json(), indent=2))]

            if name == "vault_cite":
                r = httpx.post(
                    f"{SIDECAR_URL}/cite",
                    json={
                        "space": space,
                        "query_id": args["query_id"],
                        "paths_used": args.get("paths_used") or [],
                        "note": args.get("note"),
                    },
                    timeout=10,
                )
                r.raise_for_status()
                return [types.TextContent(type="text", text=json.dumps(r.json(), indent=2))]

            if name == "vault_query_log":
                params: dict[str, Any] = {"space": space}
                for k in ("since", "until", "action"):
                    if args.get(k) is not None:
                        params[k] = args[k]
                if args.get("limit") is not None:
                    params["limit"] = args["limit"]
                r = httpx.get(f"{SIDECAR_URL}/query_log", params=params, timeout=10)
                r.raise_for_status()
                return [types.TextContent(type="text", text=json.dumps(r.json(), indent=2))]

            return [types.TextContent(type="text", text=json.dumps({"error": f"unknown tool: {name}"}))]
        except Exception as e:
            return [types.TextContent(type="text", text=json.dumps({"error": str(e)}))]

    return server


async def _main() -> None:
    from mcp.server.stdio import stdio_server

    server = _build_server()
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
