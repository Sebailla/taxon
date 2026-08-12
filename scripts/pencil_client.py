"""Minimal Pencil MCP client for design tasks.

This client connects to the Pencil MCP server (Pen.app) over stdio and
exposes a high-level API for the design tasks the taxon project needs.

The Pencil MCP server has a non-standard requirement: every JSON-RPC
request must carry a ``client_id`` field in the message envelope. The
official ``mcp`` SDK does not emit that field by default, so this
client monkey-patches :meth:`ClientSession.send_request` to inject a
fixed ``client_id`` into the dumped payload before the SDK serializes
it onto stdout.

Usage example::

    python pencil_client.py guidelines
    python pencil_client.py schema
    python pencil_client.py execute --input '// snippet'
    python pencil_client.py screenshot --node-id document --output /tmp/x.png

This client is intentionally thin so the design task scripts can
call ``await client.call_tool(...)`` directly when needed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.session import ClientSession as ClientSessionClass
from mcp.client.stdio import stdio_client


# Pencil MCP server binary lives inside Pen.app; the path is stable on
# macOS for the desktop app. ``--app desktop`` selects the desktop app
# bridge (versus the VS Code extension bridge).
PENCIL_SERVER = (
    "/Applications/Pen.app/Contents/Resources/"
    "app.asar.unpacked/out/mcp-server-darwin-arm64"
)
PENCIL_AGENT = "openCodeCLI"
# Fixed client_id per session. The Pencil MCP server requires every
# JSON-RPC message to carry this field; reusing the same value keeps
# the server-side session consistent across requests.
CLIENT_ID = "taxon-design-session-001"
DEFAULT_FILE_PATH = "/Users/sebailla/Developer/taxon/taxon.pen"


def _patch_session_for_client_id() -> None:
    """Inject ``client_id`` into every outgoing JSON-RPC request.

    The Pencil MCP server (Pen.app) rejects requests that lack a
    ``client_id`` field in the message envelope with ``Invalid
    request: missing request_id or client_id``. The official SDK
    doesn't emit that field, so we wrap :meth:`ClientSession.send_request`
    to amend the dumped payload before it reaches the writer.
    """
    original_send_request = ClientSessionClass.send_request

    async def patched_send_request(self, request, result_type, **kwargs: Any):
        # Snapshot the original method so we can call it after we
        # rewrite the request's underlying payload. We patch
        # ``model_dump`` on the request itself rather than the class
        # because each request is a pydantic model instance.
        original_model_dump = request.model_dump

        def model_dump_with_client_id(*args: Any, **kw: Any) -> dict[str, Any]:
            data = original_model_dump(*args, **kw)
            if isinstance(data, dict):
                data.setdefault("client_id", CLIENT_ID)
            return data

        request.model_dump = model_dump_with_client_id  # type: ignore[method-assign]
        try:
            return await original_send_request(self, request, result_type, **kwargs)
        finally:
            request.model_dump = original_model_dump  # type: ignore[method-assign]

    ClientSessionClass.send_request = patched_send_request  # type: ignore[method-assign]


class PencilClient:
    """Async context manager wrapping an MCP session with the Pencil server."""

    def __init__(self, file_path: str = DEFAULT_FILE_PATH) -> None:
        self.file_path = file_path
        self._session: ClientSession | None = None
        self._cm: object | None = None

    async def __aenter__(self) -> ClientSession:
        params = StdioServerParameters(
            command=PENCIL_SERVER,
            args=["--app", "desktop", "--agent", PENCIL_AGENT],
        )
        self._cm = stdio_client(params)
        read_stream, write_stream = await self._cm.__aenter__()
        self._session = ClientSession(read_stream, write_stream)
        await self._session.__aenter__()
        await self._session.initialize()
        return self._session

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._session is not None:
            await self._session.__aexit__(exc_type, exc, tb)
        if self._cm is not None:
            await self._cm.__aexit__(exc_type, exc, tb)


async def cmd_guidelines(_args: argparse.Namespace) -> int:
    async with PencilClient() as session:
        result = await session.call_tool(
            "get_guidelines",
            {"filePath": DEFAULT_FILE_PATH},
        )
        for block in result.content:
            if getattr(block, "type", None) == "text":
                print(block.text)
    return 0


async def cmd_schema(_args: argparse.Namespace) -> int:
    async with PencilClient() as session:
        result = await session.call_tool(
            "get_app_state",
            {
                "include_schema": True,
                "include_canvas_design": True,
                "include_scripts_and_shaders": False,
                "filePath": DEFAULT_FILE_PATH,
            },
        )
        for block in result.content:
            if getattr(block, "type", None) == "text":
                print(block.text)
    return 0


async def cmd_execute(args: argparse.Namespace) -> int:
    async with PencilClient() as session:
        result = await session.call_tool(
            "execute",
            {"filePath": DEFAULT_FILE_PATH, "input": args.input},
        )
        for block in result.content:
            if getattr(block, "type", None) == "text":
                print(block.text)
            else:
                print(json.dumps(block.model_dump(), indent=2, default=str))
    return 0


async def cmd_screenshot(args: argparse.Namespace) -> int:
    async with PencilClient() as session:
        result = await session.call_tool(
            "get_screenshot",
            {"filePath": DEFAULT_FILE_PATH, "nodeId": args.node_id},
        )
        for block in result.content:
            if getattr(block, "type", None) == "image":
                data = getattr(block, "data", None) or getattr(block, "bytes", None)
                if data is None:
                    print("No image data returned", file=sys.stderr)
                    return 1
                if isinstance(data, str):
                    Path(args.output).write_bytes(bytes.fromhex(data))
                else:
                    Path(args.output).write_bytes(data)
                print(f"Screenshot written to {args.output}")
                return 0
        print("No image block in response", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("guidelines", help="Load design guidelines")

    sub.add_parser("schema", help="Load .pen file schema")

    execute_p = sub.add_parser("execute", help="Execute a JavaScript snippet")
    execute_p.add_argument("--input", required=True, help="JavaScript snippet")

    screenshot_p = sub.add_parser(
        "screenshot", help="Capture a screenshot of a node"
    )
    screenshot_p.add_argument("--node-id", default="document")
    screenshot_p.add_argument("--output", required=True)

    return parser


async def main_async() -> int:
    parser = build_parser()
    args = parser.parse_args()
    handlers = {
        "guidelines": cmd_guidelines,
        "schema": cmd_schema,
        "execute": cmd_execute,
        "screenshot": cmd_screenshot,
    }
    handler = handlers.get(args.command)
    if handler is None:
        parser.print_help()
        return 2
    return await handler(args)


def main() -> int:
    _patch_session_for_client_id()
    return asyncio.run(main_async())


if __name__ == "__main__":
    sys.exit(main())
