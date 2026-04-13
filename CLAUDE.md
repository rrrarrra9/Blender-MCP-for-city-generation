# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv sync                  # Install dependencies
uv run blender-mcp       # Run the MCP server
uvx blender-mcp          # Run directly without installing
uv build                 # Build distribution packages
```

There are no tests or lint commands configured in this project.

## Architecture

BlenderMCP is a two-component system that connects Claude AI to Blender via the Model Context Protocol (MCP):

### Component 1: Blender Addon (`addon.py`)
Runs inside Blender as a sidebar panel. Creates a TCP socket server (default: `localhost:9876`) that accepts JSON commands and executes them in Blender's Python environment. The socket server runs in a background thread; actual Blender operations execute in the main thread via timers. No external pip dependencies — only Blender API and stdlib.

### Component 2: MCP Server (`src/blender_mcp/server.py`)
Implements the Model Context Protocol using the `mcp[cli]` library (FastMCP). Connects to the Blender addon via TCP socket. Exposes ~30 MCP tools to Claude, which translate to JSON commands sent to the addon.

### Communication Protocol
JSON over TCP socket. Commands: `{"type": "command_name", "params": {...}}`. Responses: `{"status": "success|error", "result": ..., "message": ...}`. Socket timeout: 180 seconds. Configurable via env vars `BLENDER_HOST` and `BLENDER_PORT`.

### Key Source Files
- `addon.py` — Blender addon with socket server and all command handlers
- `src/blender_mcp/server.py` — MCP server, `BlenderConnection` class, all MCP tool definitions
- `src/blender_mcp/telemetry.py` — Anonymous telemetry via Supabase; disabled by setting `BLENDER_MCP_DISABLE_TELEMETRY=1`
- `src/blender_mcp/telemetry_decorator.py` — `@telemetry_tool` decorator wrapping all MCP tools
- `src/blender_mcp/config.py` — Not tracked in git; contains Supabase credentials for telemetry

### MCP Tool Categories
- **Scene inspection**: `get_scene_info`, `get_object_info`, `get_viewport_screenshot`
- **Code execution**: `execute_blender_code` (runs arbitrary Python in Blender)
- **PolyHaven**: search/download HDRIs, textures, models
- **Sketchfab**: search/download 3D models
- **Hyper3D Rodin**: AI text/image-to-3D generation
- **Hunyuan3D**: AI 3D model generation
- **Status checks**: per-integration enable/disable status

Each integration (PolyHaven, Sketchfab, Hyper3D, Hunyuan3D) can be independently toggled in the Blender sidebar UI. The MCP server includes an `asset_creation_strategy` prompt that guides Claude on which asset source to use.

### City Generation Tools
`src/blender_mcp/city_tools.py` adds 9 tools for large-scale 3D environments:
`get_scene_graph`, `validate_geometry`, `take_snapshot`, `get_scene_diff`,
`export_usd_tile`, `import_osm_tile`, `set_geo_origin`, `import_pointcloud`,
`apply_procedural_materials`.

The module is imported at the bottom of `server.py` as a side-effect import so
its `@mcp.tool()` decorators register against the shared `mcp` instance.
See [ARCHITECTURE.md](ARCHITECTURE.md) for the coordinate system and feedback loop design.

### Adding a New Tool
1. Add a command handler in `addon.py` (in `_execute_command_internal()` dispatcher, under `city_handlers` or a new block)
2. Add the corresponding MCP tool in `server.py` or a separate module using `@mcp.tool()` + `@telemetry_tool("tool_name")`
3. The tool calls `blender.send_command("command_type", {...params})` via `get_blender_connection()`
