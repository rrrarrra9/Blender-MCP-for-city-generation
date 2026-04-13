

# BlenderMCP - Blender Model Context Protocol Integration

BlenderMCP connects Blender to Claude AI through the Model Context Protocol (MCP), allowing Claude to directly interact with and control Blender. This integration enables prompt assisted 3D modeling, scene creation, and manipulation.

**We have no official website. Any website you see online is unofficial and has no affiliation with this project. Use them at your own risk.**

[Full tutorial](https://www.youtube.com/watch?v=lCyQ717DuzQ)

### Join the Community

Give feedback, get inspired, and build on top of the MCP: [Discord](https://discord.gg/z5apgR8TFU)

### Supporters

[CodeRabbit](https://www.coderabbit.ai/)

**All supporters:**

[Support this project](https://github.com/sponsors/ahujasid)

## Current version(1.5.5)
- Added Hunyuan3D support
- View screenshots for Blender viewport to better understand the scene
- Search and download Sketchfab models
- Support for Poly Haven assets through their API
- Support to generate 3D models using Hyper3D Rodin
- Run Blender MCP on a remote host
- Telemetry for tools executed (completely anonymous)

### Installating a new version (existing users)
- For newcomers, you can go straight to Installation. For existing users, see the points below
- Download the latest addon.py file and replace the older one, then add it to Blender
- Delete the MCP server from Claude and add it back again, and you should be good to go!


## Features

- **Two-way communication**: Connect Claude AI to Blender through a socket-based server
- **Object manipulation**: Create, modify, and delete 3D objects in Blender
- **Material control**: Apply and modify materials and colors
- **Scene inspection**: Get detailed information about the current Blender scene
- **Code execution**: Run arbitrary Python code in Blender from Claude

## Components

The system consists of two main components:

1. **Blender Addon (`addon.py`)**: A Blender addon that creates a socket server within Blender to receive and execute commands
2. **MCP Server (`src/blender_mcp/server.py`)**: A Python server that implements the Model Context Protocol and connects to the Blender addon

## Installation


### Prerequisites

- Blender 3.0 or newer
- Python 3.10 or newer
- uv package manager: 

**If you're on Mac, please install uv as**
```bash
brew install uv
```
**On Windows**
```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex" 
```
and then add uv to the user path in Windows (you may need to restart Claude Desktop after):
```powershell
$localBin = "$env:USERPROFILE\.local\bin"
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
[Environment]::SetEnvironmentVariable("Path", "$userPath;$localBin", "User")
```

Otherwise installation instructions are on their website: [Install uv](https://docs.astral.sh/uv/getting-started/installation/)

**⚠️ Do not proceed before installing UV**

### Environment Variables

The following environment variables can be used to configure the Blender connection:

- `BLENDER_HOST`: Host address for Blender socket server (default: "localhost")
- `BLENDER_PORT`: Port number for Blender socket server (default: 9876)

Example:
```bash
export BLENDER_HOST='host.docker.internal'
export BLENDER_PORT=9876
```

### Claude for Desktop Integration

[Watch the setup instruction video](https://www.youtube.com/watch?v=neoK_WMq92g) (Assuming you have already installed uv)

Go to Claude > Settings > Developer > Edit Config > claude_desktop_config.json to include the following:

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
<details>
<summary>Claude Code</summary>

Use the Claude Code CLI to add the blender MCP server:

```bash
claude mcp add blender uvx blender-mcp
```
</details>

### Cursor integration

[![Install MCP Server](https://cursor.com/deeplink/mcp-install-dark.svg)](https://cursor.com/link/mcp%2Finstall?name=blender&config=eyJjb21tYW5kIjoidXZ4IGJsZW5kZXItbWNwIn0%3D)

For Mac users, go to Settings > MCP and paste the following 

- To use as a global server, use "add new global MCP server" button and paste
- To use as a project specific server, create `.cursor/mcp.json` in the root of the project and paste


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

For Windows users, go to Settings > MCP > Add Server, add a new server with the following settings:

```json
{
    "mcpServers": {
        "blender": {
            "command": "cmd",
            "args": [
                "/c",
                "uvx",
                "blender-mcp"
            ]
        }
    }
}
```

[Cursor setup video](https://www.youtube.com/watch?v=wgWsJshecac)

**⚠️ Only run one instance of the MCP server (either on Cursor or Claude Desktop), not both**

### Visual Studio Code Integration

_Prerequisites_: Make sure you have [Visual Studio Code](https://code.visualstudio.com/) installed before proceeding.

[![Install in VS Code](https://img.shields.io/badge/VS_Code-Install_blender--mcp_server-0098FF?style=flat-square&logo=visualstudiocode&logoColor=ffffff)](vscode:mcp/install?%7B%22name%22%3A%22blender-mcp%22%2C%22type%22%3A%22stdio%22%2C%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22blender-mcp%22%5D%7D)

### Installing the Blender Addon

1. Download the `addon.py` file from this repo
1. Open Blender
2. Go to Edit > Preferences > Add-ons
3. Click "Install..." and select the `addon.py` file
4. Enable the addon by checking the box next to "Interface: Blender MCP"


## Usage

### Starting the Connection
![BlenderMCP in the sidebar](assets/addon-instructions.png)

1. In Blender, go to the 3D View sidebar (press N if not visible)
2. Find the "BlenderMCP" tab
3. Turn on the Poly Haven checkbox if you want assets from their API (optional)
4. Click "Connect to Claude"
5. Make sure the MCP server is running in your terminal

### Using with Claude

Once the config file has been set on Claude, and the addon is running on Blender, you will see a hammer icon with tools for the Blender MCP.

![BlenderMCP in the sidebar](assets/hammer-icon.png)

#### Capabilities

- Get scene and object information 
- Create, delete and modify shapes
- Apply or create materials for objects
- Execute any Python code in Blender
- Download the right models, assets and HDRIs through [Poly Haven](https://polyhaven.com/)
- AI generated 3D models through [Hyper3D Rodin](https://hyper3d.ai/)


### Example Commands

Here are some examples of what you can ask Claude to do:

- "Create a low poly scene in a dungeon, with a dragon guarding a pot of gold" [Demo](https://www.youtube.com/watch?v=DqgKuLYUv00)
- "Create a beach vibe using HDRIs, textures, and models like rocks and vegetation from Poly Haven" [Demo](https://www.youtube.com/watch?v=I29rn92gkC4)
- Give a reference image, and create a Blender scene out of it [Demo](https://www.youtube.com/watch?v=FDRb03XPiRo)
- "Generate a 3D model of a garden gnome through Hyper3D"
- "Get information about the current scene, and make a threejs sketch from it" [Demo](https://www.youtube.com/watch?v=jxbNI5L7AH8)
- "Make this car red and metallic" 
- "Create a sphere and place it above the cube"
- "Make the lighting like a studio"
- "Point the camera at the scene, and make it isometric"

## Hyper3D integration

Hyper3D's free trial key allows you to generate a limited number of models per day. If the daily limit is reached, you can wait for the next day's reset or obtain your own key from hyper3d.ai and fal.ai.

## Troubleshooting

- **Connection issues**: Make sure the Blender addon server is running, and the MCP server is configured on Claude, DO NOT run the uvx command in the terminal. Sometimes, the first command won't go through but after that it starts working.
- **Timeout errors**: Try simplifying your requests or breaking them into smaller steps
- **Poly Haven integration**: Claude is sometimes erratic with its behaviour
- **Have you tried turning it off and on again?**: If you're still having connection errors, try restarting both Claude and the Blender server


## Technical Details

### Communication Protocol

The system uses a simple JSON-based protocol over TCP sockets:

- **Commands** are sent as JSON objects with a `type` and optional `params`
- **Responses** are JSON objects with a `status` and `result` or `message`

## Limitations & Security Considerations

- The `execute_blender_code` tool allows running arbitrary Python code in Blender, which can be powerful but potentially dangerous. Use with caution in production environments. ALWAYS save your work before using it.
- Poly Haven requires downloading models, textures, and HDRI images. If you do not want to use it, please turn it off in the checkbox in Blender. 
- Complex operations might need to be broken down into smaller steps


#### Telemetry Control

BlenderMCP collects anonymous usage data to help improve the tool. You can control telemetry in two ways:

1. **In Blender**: Go to Edit > Preferences > Add-ons > Blender MCP and uncheck the telemetry consent checkbox
   - With consent (checked): Collects anonymized prompts, code snippets, and screenshots
   - Without consent (unchecked): Only collects minimal anonymous usage data (tool names, success/failure, duration)

2. **Environment Variable**: Completely disable all telemetry by running:
```bash
DISABLE_TELEMETRY=true uvx blender-mcp
```

Or add it to your MCP config:
```json
{
    "mcpServers": {
        "blender": {
            "command": "uvx",
            "args": ["blender-mcp"],
            "env": {
                "DISABLE_TELEMETRY": "true"
            }
        }
    }
}
```

All telemetry data is fully anonymized and used solely to improve BlenderMCP.


## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

---

## City Generation Tools

These tools enable Claude to build and iterate on large-scale 3D environments
(cities, terrain, point clouds) through a structured JSON feedback loop — no
screenshots required.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the coordinate system and design.

### Prerequisites

Install the additional dependencies:

```bash
uv sync   # picks up requests, laspy, open3d from pyproject.toml
```

`laspy` and `open3d` are only needed inside Blender's Python for
`import_pointcloud`; everything else uses the standard library or `requests`
(already present in the addon).

---

### `set_geo_origin(lat, lon)`

Sets the geographic reference point for the scene. Must be called before any
tool that converts lat/lon coordinates.

**Input**

| Parameter | Type | Description |
|-----------|------|-------------|
| `lat` | `float` | Latitude in decimal degrees |
| `lon` | `float` | Longitude in decimal degrees |

**Output**

```json
{ "lat": 48.8584, "lon": 2.2945, "stored": true }
```

Stored as scene custom properties (`geo_origin_lat`, `geo_origin_lon`) so the
value survives file saves.

---

### `import_osm_tile(bbox, layer_types)`

Fetches OpenStreetMap data from the Overpass API and creates Blender geometry.

**Input**

| Parameter | Type | Description |
|-----------|------|-------------|
| `bbox` | `dict` | `{ "min_lat", "max_lat", "min_lon", "max_lon" }` |
| `layer_types` | `list[str]` | Any subset of `["buildings","roads","water","parks","railways"]` |

**Output**

```json
{
  "objects_created": 312,
  "layers": { "buildings": 180, "roads": 120, "parks": 12 }
}
```

Buildings are extruded using the OSM `height` tag (metres), `building:levels`
× 3 m, or 10 m as a default.  All objects receive `osm_*` custom properties
for later use by `apply_procedural_materials`.

---

### `get_scene_graph()`

Returns a compact JSON representation of the entire active scene.

**Output**

```json
{
  "scene": "Scene",
  "frame_current": 1,
  "object_count": 412,
  "objects": [
    {
      "name": "osm_123456",
      "type": "MESH",
      "location": [12.3, 45.6, 0.0],
      "rotation_euler": [0, 0, 0],
      "scale": [1, 1, 1],
      "visible": true,
      "parent": null,
      "children": [],
      "materials": ["mat_building_concrete"],
      "modifiers": [],
      "mesh": { "vertices": 16, "edges": 24, "faces": 10 },
      "bbox": [[-5,-5,0], [5,5,12]]
    }
  ],
  "collections": [
    { "name": "buildings", "children": [], "objects": ["osm_123456"] }
  ]
}
```

---

### `validate_geometry(object_name?)`

Runs mesh analysis and returns structured error/warning reports.

**Input**

| Parameter | Type | Description |
|-----------|------|-------------|
| `object_name` | `str \| None` | Object to validate, or `null` for the whole scene |

**Output (single object)**

```json
{
  "object": "osm_123456",
  "errors": [
    { "type": "non_manifold_edges", "count": 4, "indices": [1,2,3,4] },
    { "type": "zero_area_faces", "count": 1, "indices": [7] }
  ],
  "warnings": [
    { "type": "no_uv_map" }
  ],
  "clean": false
}
```

**Output (full scene)**

```json
{
  "scene_clean": false,
  "objects": [ ...per-object reports... ]
}
```

Checks: non-manifold edges, inverted normals, duplicate faces, isolated
vertices, zero-area faces, missing UV map, low UV coverage (< 5 %), object
origin outside ± 10 000 m.

---

### `take_snapshot(snapshot_id)`

Stores the current scene state in memory.

**Input**

| Parameter | Type | Description |
|-----------|------|-------------|
| `snapshot_id` | `str` | Arbitrary key, e.g. `"before_materials"` |

**Output**

```json
{ "snapshot_id": "before_materials", "object_count": 312, "timestamp": "2024-01-01T00:00:00Z" }
```

---

### `get_scene_diff(snapshot_id)`

Compares the current scene to a stored snapshot and returns only what changed.

**Input**

| Parameter | Type | Description |
|-----------|------|-------------|
| `snapshot_id` | `str` | Key from a prior `take_snapshot()` call |

**Output**

```json
{
  "snapshot_id": "before_materials",
  "snapshot_timestamp": "2024-01-01T00:00:00Z",
  "added": ["NewObject"],
  "deleted": ["OldObject"],
  "modified": [
    {
      "name": "osm_123456",
      "field": "face_count",
      "before": 6,
      "after": 10,
      "bbox_before": [[-1,-1,0],[1,1,3]],
      "bbox_after":  [[-1,-1,0],[1,1,6]]
    }
  ]
}
```

---

### `export_usd_tile(output_path, center, radius_m)`

Exports a spatial subset of the scene as a USD file.

**Input**

| Parameter | Type | Description |
|-----------|------|-------------|
| `output_path` | `str` | Absolute path for the `.usdc` / `.usda` file |
| `center` | `[float, float]` | World-space `[x, y]` of the tile centre |
| `radius_m` | `float` | Tile radius in metres |

**Output**

```json
{ "path": "/tmp/city_tile.usdc", "file_size_mb": 14.2, "object_count": 87 }
```

---

### `import_pointcloud(file_path, voxel_size?)`

Imports a LiDAR `.las` / `.laz` file, voxel-downsamples it, and creates a
Blender vertex mesh.

**Input**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `file_path` | `str` | — | Absolute path to `.las` / `.laz` |
| `voxel_size` | `float` | `0.5` | Voxel grid cell size in metres |

**Output**

```json
{
  "points_loaded": 4200000,
  "points_after_voxel": 182000,
  "mesh_created": true
}
```

Requires `laspy` in Blender's Python.  `open3d` is used for voxel downsampling
when available; otherwise falls back to NumPy.

---

### `apply_procedural_materials(ruleset?)`

Assigns Principled BSDF node-tree materials based on `osm_layer` custom
properties.  No image textures — fully procedural.

**Input**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `ruleset` | `str` | `"default"` | Material ruleset name |

**Default ruleset mappings**

| OSM layer | Material | Key nodes |
|-----------|----------|-----------|
| `buildings` | concrete / brick / glass | Principled BSDF + Noise |
| `roads` / `railways` | asphalt | Principled BSDF + Wave (lane markings) |
| `water` | transparent blue | Principled BSDF (Transmission) |
| `parks` | grass | Principled BSDF + Musgrave roughness |

**Output**

```json
{ "ruleset": "default", "materials_applied": 312 }
```

---

### Running the end-to-end test

```bash
blender --background --python tests/test_city_pipeline.py
```

The test script:
1. Sets geo origin to the Eiffel Tower (48.8584, 2.2945)
2. Imports an OSM tile (~400 m radius, buildings + roads + parks)
3. Validates all geometry
4. Takes a snapshot
5. Applies procedural materials
6. Diffs the scene against the snapshot
7. Exports a USD tile
8. Prints a full JSON report of every step

---

## Disclaimer

This is a third-party integration and not made by Blender. Made by [Siddharth](https://x.com/sidahuj)
