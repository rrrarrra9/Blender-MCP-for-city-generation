# Architecture: Structured Feedback Loop for City Generation

## Problem

The base blender-mcp has no feedback loop. Claude can execute Python inside
Blender and capture stdout, but receives no structured information about the
resulting scene state: what objects exist, whether geometry is valid, how the
scene changed.  Screenshots are imprecise and token-expensive.

## Solution: Structured Data Layer

Instead of images, every city tool returns compact JSON that gives Claude
precise, token-efficient answers about the scene:

```
Claude ──► MCP tool call
             │
             ▼
         city_tools.py  (src/blender_mcp/city_tools.py)
         – thin MCP glue
         – serialises parameters, calls send_command()
             │  JSON over TCP socket  (localhost:9876)
             ▼
         addon.py BlenderMCPServer._execute_command_internal()
         – dispatches to city handler method
         – runs in Blender main thread (via bpy.app.timers)
         – returns structured dict
             │
             ▼
         JSON response back up the socket
             │
             ▼
         MCP tool returns JSON string to Claude
```

Claude never needs to look at a render to know:
- What objects are in the scene and where (`get_scene_graph`)
- Whether the geometry is valid (`validate_geometry`)
- What changed between two iterations (`take_snapshot` / `get_scene_diff`)

## Coordinate System

### Geo-origin

All geographic work starts with a single `set_geo_origin(lat, lon)` call.
This stores the reference point in `bpy.context.scene["geo_origin_lat"]` and
`bpy.context.scene["geo_origin_lon"]` — scene custom properties that survive
file saves.

### Equirectangular projection

Every subsequent lat/lon pair is converted to Blender world-space XY by the
static helper `BlenderMCPServer._latlon_to_xy`:

```python
R = 6_371_000  # Earth radius in metres
x = radians(lon - origin_lon) * R * cos(radians(origin_lat))
y = radians(lat  - origin_lat) * R
```

**1 Blender unit = 1 metre.**  Z is elevation (0 = ground plane).

This projection is accurate to < 1 % error within ± 50 km of the origin, which
is sufficient for city-scale scenes.  For larger regions, replace with a proper
UTM or EPSG projection.

### OSM data flow

```
Overpass API (JSON) ──► node index (id → (x, y)) ──► Blender mesh
                                                       │
                                                  custom props:
                                                  obj["osm_id"]
                                                  obj["osm_layer"]
                                                  obj["osm_building"]
                                                  obj["osm_height"]
                                                  …
```

Custom properties survive file saves and are read by
`apply_procedural_materials` to choose the right shader.

## Snapshot / Diff System

Snapshots are held in `BlenderMCPServer._snapshots` — a class-level dict that
lives in the addon process memory.  Each snapshot is a plain dict:

```json
{
  "timestamp": "2024-01-01T00:00:00Z",
  "objects": {
    "Cube": {
      "type": "MESH",
      "location": [0, 0, 0],
      "mesh": { "vertices": 8, "faces": 6 },
      "bbox": [[-1,-1,-1], [1,1,1]]
    }
  }
}
```

`get_scene_diff` walks both dicts and emits only the delta — added, deleted,
and modified objects — so Claude sees exactly what changed after each operation
without re-reading the entire scene.

## City Tool Responsibilities

| Tool | Who does the work | Output |
|------|------------------|--------|
| `set_geo_origin` | Blender (stores props) | ack |
| `import_osm_tile` | Blender (Overpass fetch + mesh build) | counts |
| `get_scene_graph` | Blender (iterates scene) | full JSON graph |
| `validate_geometry` | Blender (bmesh analysis) | error/warning lists |
| `take_snapshot` | Blender (snapshot dict) | ack + count |
| `get_scene_diff` | Blender (dict diff) | delta |
| `export_usd_tile` | Blender (native USD exporter) | path + size |
| `import_pointcloud` | Blender (laspy + optional open3d) | point counts |
| `apply_procedural_materials` | Blender (node-tree builder) | count |

All Blender-side work executes in the main thread via `bpy.app.timers` — the
same pattern used by the existing addon handlers.

## Statelessness

Tools are stateless **except**:
- `_snapshots` dict (in-process, cleared on addon restart)
- `geo_origin_lat` / `geo_origin_lon` scene custom properties (persistent)

No files or databases are used for state.

## Adding More Rulesets to apply_procedural_materials

The `ruleset` parameter is forwarded to the addon.  To add a new ruleset:

1. Add a JSON file `src/blender_mcp/material_rulesets/<name>.json` that maps
   `osm_layer` → BSDF parameters.
2. Load and parse the file in the `apply_procedural_materials` addon handler.
3. Fall back to `"default"` if the file is not found.
