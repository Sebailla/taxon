# Design phase blocked — Pencil MCP server bug

## Status

**Blocked.** The Pencil MCP server (`/Applications/Pen.app/.../mcp-server-darwin-arm64 --app desktop`) is configured in `opencode.json` but rejects tool calls from external clients.

## Investigation timeline

1. Pencil MCP binary is reachable. Connection to the desktop socket succeeds:
   ```
   [TransportClient] connected to /Users/sebailla/.pencil/socket/pencil-desktop.sock
   ```
2. `initialize` handshake works (the server identifies itself as `pencil` v1.0.0 with tools listed).
3. `tools/list` returns all six tools (`browser`, `execute`, `export_html`, `export_nodes`, `get_app_state`, `get_guidelines`, `get_screenshot`).
4. **Every `tools/call` request times out after 62 seconds** with error `failed to execute tool call. you are probably referencing the wrong .pen file` — even when the `.pen` file is open in `Pen.app` in foreground.

## Root cause

The Pencil MCP server expects every request to carry a `client_id` field in the JSON-RPC envelope. Without it, the server's IPC layer logs `Invalid request: missing request_id or client_id` and the tool call hangs.

A custom Python MCP client (`scripts/pencil_client.py`) monkey-patches `ClientSession.send_request` to inject `client_id` into the dumped payload before serialization. With the patch:

- The "missing request_id or client_id" error no longer appears in `~/Library/Logs/Pen/main.log`.
- The connection is established and the agent is registered.
- But the tool call still times out after 62 seconds.

The Pencil MCP server therefore rejects external tool calls even when its own protocol requirements are met. The error `you are probably referencing the wrong .pen file` is a generic fallback; the actual cause is upstream.

## Why this matters

AGENTS.md §5 mandates:

> any UI design work is performed **first** in Pencil MCP and audited under the `impeccable` skill before any implementation in code.

Without Pencil, the design-first workflow cannot execute. The pragmatic workaround documented in issue #9 is:

1. Capture the design as text wireframes + design tokens in `docs/design/design.md`.
2. Audit the design tokens against the `impeccable` skill criteria before any frontend code lands.
3. The `impeccable` skill reviews the final code as a proxy for the design audit the Pencil step would have produced.

## Reproducer

```bash
# This command reproduces the bug:
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"client_id":"taxon-test","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"openCodeCLI","version":"1.0"}}}' \
  '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}' \
  '{"jsonrpc":"2.0","id":2,"client_id":"taxon-test","method":"tools/call","params":{"name":"get_guidelines","arguments":{"filePath":"/Users/sebailla/Developer/taxon/taxon.pen"}}}' \
  | /Applications/Pen.app/Contents/Resources/app.asar.unpacked/out/mcp-server-darwin-arm64 \
      --app desktop --agent openCodeCLI

# Wait 62 seconds; observe:
#   [TransportClient] ✗ timeout tool=get-guidelines request_id=...
#   [TransportClient] ← err tool=get-guidelines ... err=failed to execute tool call. you are probably referencing the wrong .pen file
```

## Resolution

Reported upstream as a Pencil MCP server bug. Until it is fixed, the taxon project proceeds via the pragmatic path described in issue #9.

## Acceptance evidence

| Evidence | Value |
| --- | --- |
| Issue | https://github.com/Sebailla/taxon/issues/9 (Phase 3 + 4) |
| MCP client script | `scripts/pencil_client.py` (monkey-patches `client_id`) |
| Server log | `~/Library/Logs/Pen/main.log` |
| Reproducer command | See above |