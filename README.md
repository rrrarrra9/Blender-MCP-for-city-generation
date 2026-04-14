# BlenderMCP - Blender Model Context Protocol Integration

BlenderMCP connects Claude AI to Blender through the Model Context Protocol (MCP), allowing Claude to directly interact with and control Blender. This integration enables prompt-assisted 3D modeling, scene creation, large-scale city generation, and procedural manipulations.

**We have no official website. Any website you see online is unofficial and has no affiliation with this project. Use them at your own risk.**

[Full tutorial](https://www.youtube.com/watch?v=lCyQ717DuzQ)

### Join the Community

Give feedback, get inspired, and build on top of the MCP: [Discord](https://discord.gg/z5apgR8TFU)

### Supporters

[CodeRabbit](https://www.coderabbit.ai/)

**All supporters:**

[Support this project](https://github.com/sponsors/ahujasid)

## Current version (1.5.5)
- Support to generate and procedurally detail huge Cities using OpenStreetMap (OSM) data.
- Added Hunyuan3D support
- View screenshots for Blender viewport to better understand the scene
- Search and download Sketchfab models
- Support for Poly Haven assets through their API
- Support to generate 3D models using Hyper3D Rodin
- Run Blender MCP on a remote host
- Telemetry for tools executed (completely anonymous)

### Installing a new version (existing users)
- Download the latest `addon.py` file and replace the older one, then add it to Blender.
- Delete the MCP server from your client (Claude, Cursor, etc.) and add it back again.

## Features & Integrations

- **Two-way communication**: Connect Claude AI to Blender through a socket-based server.
- **City Generation & Procedural Environments**: Build and iterate on large-scale 3D environments (cities, terrain, point clouds) through a structured JSON feedback loop using **Claude Code**.
- **Object Manipulation**: Create, modify, and delete 3D objects in Blender.
- **Material Control**: Apply and modify materials and colors.
- **Scene Inspection & Diffing**: Get detailed information about the current Blender scene, take snapshots, and identify step-by-step diffs.
- **Code Execution**: Run arbitrary Python code in Blender from Claude.

## Architecture & Components

The system consists of two main components:
1. **Blender Addon (`addon.py`)**: A Blender addon that creates a socket server within Blender to receive and execute commands.
2. **MCP Server (`src/blender_mcp/server.py` & tools)**: A Python server that implements the Model Context Protocol, bundling general 3D operations and specialized city/terrain tools.

See [ARCHITECTURE.md](ARCHITECTURE.md) for deeper details on coordinate systems and specific tool design schemas.

## Installation

### Prerequisites

- Blender 3.0 or newer
- Python 3.10 or newer
- `uv` package manager

**Mac Installation:**
```bash
brew install uv
```
**Windows Installation:**
```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex" 
```
and then add uv to the user path in Windows (you may need to restart Claude Desktop after):
```powershell
$localBin = "$env:USERPROFILE\.local\bin"
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
[Environment]::SetEnvironmentVariable("Path", "$userPath;$localBin", "User")
```
Otherwise, see official docs: [Install uv](https://docs.astral.sh/uv/getting-started/installation/)

**⚠️ Do not proceed before installing UV**

To use City Generation Tools, install the extra dependencies before running:
```bash
uv sync
```
*(NOTE: `laspy` and `open3d` are only needed inside Blender's Python if you wish to use `import_pointcloud`)*

### Environment Variables

The following environment variables configure the Blender connection:
- `BLENDER_HOST`: Host address for Blender socket server (default: "localhost")
- `BLENDER_PORT`: Port number for Blender socket server (default: 9876)

Example:
```bash
export BLENDER_HOST='host.docker.internal'
export BLENDER_PORT=9876
```

### Claude Code Integration (Recommended for City Generation)

You can easily integrate BlenderMCP into **Claude Code** to programmatically architect complex landscapes over multiple steps.

```bash
claude mcp add blender uvx blender-mcp
```

### Claude for Desktop Integration

[Watch the setup instruction video](https://www.youtube.com/watch?v=neoK_WMq92g) (Assuming you have already installed uv)

Go to Claude > Settings > Developer > Edit Config (`claude_desktop_config.json`) and include:

```json
{
    "mcpServers": {
        "blender": {
            "command": "uvx",
            "args": [
                "blender-mcp"
            ]
        }
    }
}
```

### Cursor Integration

[![Install MCP Server](https://cursor.com/deeplink/mcp-install-dark.svg)](https://cursor.com/link/mcp%2Finstall?name=blender&config=eyJjb21tYW5kIjoidXZ4IGJsZW5kZXItbWNwIn0%3D)

For Mac users, go to Settings > MCP and paste the following snippet. For Windows, configure through Settings > MCP > Add Server.

```json
{
    "mcpServers": {
        "blender": {
            "command": "uvx",
            "args": [
                "blender-mcp"
            ]
        }
    }
}
```
*(On Windows, you may need to use `cmd` with arguments `/c`, `uvx`, `blender-mcp` if execution fails).*

[Cursor setup video](https://www.youtube.com/watch?v=wgWsJshecac)

**⚠️ Only run one instance of the MCP server (either on Cursor or Claude Desktop or Claude Code), not multiple simultaneously.**

### Visual Studio Code Integration

[![Install in VS Code](https://img.shields.io/badge/VS_Code-Install_blender--mcp_server-0098FF?style=flat-square&logo=visualstudiocode&logoColor=ffffff)](vscode:mcp/install?%7B%22name%22%3A%22blender-mcp%22%2C%22type%22%3A%22stdio%22%2C%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22blender-mcp%22%5D%7D)

### Installing the Blender Addon

1. Download the `addon.py` file from this repo.
2. Open Blender.
3. Go to Edit > Preferences > Add-ons.
4. Click "Install..." and select the `addon.py` file.
5. Enable the addon by checking the box next to "Interface: Blender MCP".

## Usage

### Starting the Connection
![BlenderMCP in the sidebar](assets/addon-instructions.png)

1. In Blender, go to the 3D View sidebar (press `N` if not visible).
2. Find the "BlenderMCP" tab.
3. Check Poly Haven or other integrations if you want external API assets (optional).
4. Click "Connect to Claude".
5. Make sure the MCP server is running in your terminal/client.

### Using with Claude

Once configured, your AI client will expose Blender tools.

![BlenderMCP in the sidebar](assets/hammer-icon.png)

#### General Example Commands
- "Create a low poly scene in a dungeon, with a dragon guarding a pot of gold"
- "Create a beach vibe using HDRIs, textures, and models like rocks and vegetation from Poly Haven"
- "Generate a 3D model of a garden gnome through Hyper3D"
- "Get information about the current scene, and make a three.js sketch from it"
- "Make this car red and metallic"

#### City Generation Workflows (Claude Code Native)
You can directly prompt Claude to run complex, orchestrated city generation sequences because it can analyze the environment dynamically using snapshots and scene graphs. Example:

1. **"Set the scene's geographic origin to Paris (48.8584, 2.2945)."**
2. **"Import the matching OSM tile bounding box including buildings, roads, parks, and water layers."**
3. **"Run `validate_geometry` to check for non-manifold edges."**
4. **"Take a snapshot `pre_details`, then apply procedural facade geometry, street details, and vegetation across the tile."**
5. **"Bake ambient occlusion and export a local USD tile."**

These logic loops let Claude refine geometry based on spatial data without requiring screenshots.

## Tool Details & API Reference

### City Generation Tools (Module `city_tools.py`)
- **`set_geo_origin(lat, lon)`**: Sets the geographic reference point for coordinate translation.
- **`import_osm_tile(bbox, layer_types)`**: Fetches OSM via Overpass API and creates default geometry layers.
- **`get_scene_graph()`**: Full state output of the Blender hierarchy, objects, vertices, bounding boxes, and performance health metrics.
- **`validate_geometry(object_name?)`**: Runs mesh analysis returning arrays of missing UVs, non-manifold edges, isolated vertices, etc.
- **`take_snapshot` / `get_scene_diff`**: Capture iterative states and delta checks after generative processes.
- **`export_usd_tile(output_path, center, radius_m)`**: Export bounding-radius specific scenes to universal standards.
- **`import_pointcloud(file_path, voxel_size?)`**: Build meshes from LiDAR (`.las` / `.laz`) arrays.
- **Procedural Builders**: Build detail atop of simple meshes instantly
  - `apply_procedural_materials` (OSM tags to Principled BSDFs)
  - `add_street_detail`, `add_vegetation`, `add_ground_detail`
  - `add_facade_textures`, `generate_facade_geometry` (Physical depth detailing)
  - `add_ambient_occlusion`, `add_road_geometry`, `add_lighting_setup`, `render_viewport`

### AI Asset Integration
- **Hyper3D integration**: Hyper3D's free trial key allows you to generate a limited number of models per day. If the daily limit is reached, you can wait for the next day's reset or obtain your own key from `hyper3d.ai` and `fal.ai`.
- **Hunyuan3D**: Text/Image to 3D capability using local or official API.
- **Poly Haven / Sketchfab**: Fetches high-quality models, textures, and HDRIs directly to the interface.

## Troubleshooting

- **Connection issues**: Make sure the Blender addon server is running, and the MCP server is configured in your client. DO NOT run `uvx` standalone without the client configuration. The first command occasionally drops, just try again.
- **Timeout errors**: Simplfy your requests or break them down into steps.
- **Poly Haven integration**: Operations might be erratic depending on Claude's immediate planning logic.
- **Have you tried turning it off and on again?**: Restart both the client and the Blender Server if socket connections hang.

## Technical Details

### Communication Protocol
The system uses a simple JSON-based protocol over TCP sockets:
- **Commands**: JSON objects with a `type` and optional `params`.
- **Responses**: JSON objects with a `status` and `result` or `message`.

## Limitations & Security Considerations

- **Code Execution**: The `execute_blender_code` tool allows running arbitrary Python code in Blender, which can be powerful but potentially dangerous. Use with caution in production environments. ALWAYS save your work before using it.
- **Downloads**: Integrations require downloading models via HTTP. Please toggle them off if constrained.
- **Performance**: High fidelity cities using `generate_facade_geometry` on enormous OSM tiles will crash Blender if poly counts exceed system RAM limits. Use `import_osm_tile` in chunks and monitor `get_scene_graph()` performance readouts.

## Telemetry Control

BlenderMCP collects anonymous usage data to help improve the tool. You can control telemetry in two ways:

1. **In Blender**: Go to Edit > Preferences > Add-ons > Blender MCP and uncheck the telemetry consent checkbox.
   - Checked: Collects anonymized prompts, code snippets, and screenshots.
   - Unchecked: Minimal anonymous usage data (tool names, success/failure, duration).
2. **Environment Variable**: 
   Disable completely: `DISABLE_TELEMETRY=true uvx blender-mcp` or inside your `mcpServers` json `env` object.

All data is strictly anonymized.

## Contributing
Contributions are welcome! Please feel free to submit a Pull Request.

---

## Disclaimer
This is a third-party integration and not made by Blender. Made by [Siddharth](https://x.com/sidahuj).
