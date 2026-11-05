# Canva MCP Setup

Server: `https://mcp.canva.com/mcp` (HTTP transport, registered under the name `Canva`)

Canva's official remote MCP server lets Claude Code search, create, edit, and export Canva designs. It authenticates with OAuth against the user's own Canva account.

## Setup steps

1. Register the server at **user scope** so it is available in every project:

   ```
   claude mcp add --scope user --transport http Canva https://mcp.canva.com/mcp
   ```

   Without `--scope user` the server is saved at local scope and only appears in the project folder where the command was run.

2. Restart the session. Servers added with `claude mcp add` are not loaded into a running session. `claude --continue` restarts in the same folder and keeps the conversation.

3. Run `/mcp`, select **Canva**, and choose Authenticate. Sign in to Canva in the browser and approve access.

4. Confirm the status with `claude mcp list` (it should show connected) or `claude mcp get Canva` (it should show `Scope: User config`).

## Verification result

Two read-only calls succeeded on 2026-11-05:

- `list-brand-kits` returned 0 brand kits (none are set up on the account).
- `search-designs` returned the three most recent designs (all posters).

## Available tools

After authentication the server exposes 45 tools, named `mcp__Canva__<tool>`. See `canva-mcp-tools.md` for the full list with purposes, required inputs, selection rules, and the asynchronous and editing workflows.

## Troubleshooting

- **Canva is missing from `/mcp`:** the session was started before the server was added. Restart it.
- **Canva only appears in one folder:** it was registered at local scope. Remove it with `claude mcp remove Canva -s local` and add it again with `--scope user`.
- **Status shows "Needs authentication":** run `/mcp` and complete the browser login.
- **Do not confuse it with the Canva Dev MCP server** (`@canva/cli mcp`), which is a separate tool for building Canva apps.

## Sources

- https://www.canva.dev/docs/connect/canva-mcp-server-setup
- https://www.canva.dev/docs/mcp
