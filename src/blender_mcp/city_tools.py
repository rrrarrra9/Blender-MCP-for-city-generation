"""
City generation MCP tools for blender-mcp.

Each tool sends a JSON command to the Blender addon via the shared socket
connection (same pattern as the rest of server.py).  All Blender-side work
runs in the addon; this module is pure MCP glue.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from mcp.server.fastmcp import Context

from .server import get_blender_connection, mcp
from .telemetry_decorator import telemetry_tool
from . import osm_client

logger = logging.getLogger("BlenderMCPCityTools")


# ── 1. get_scene_graph ────────────────────────────────────────────────────────

@telemetry_tool("get_scene_graph")
@mcp.tool()
def get_scene_graph(ctx: Context) -> str:
    """
    Return a full JSON scene graph of the active Blender scene.

    Includes for every object:
    - name, type, location, rotation, scale, visibility
    - parent / children relationships
    - bounding box (world space, mesh objects only)
    - vertex / edge / face counts (mesh objects only)
    - material slot names
    - active modifier names
    - budget_warning if face count > 50 000
    - health_flags: list of ["no_material", "no_uv", "likely_inverted_normals"]

    Also includes the collection hierarchy and scene totals:
    - totals.vertices, totals.faces, totals.unique_materials
    - totals.estimated_memory_mb  (32 bytes/vertex heuristic)

    Returns a compact JSON string.
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command("get_scene_graph")
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"get_scene_graph error: {e}")
        return json.dumps({"error": str(e)})


# ── 2. validate_geometry ──────────────────────────────────────────────────────

@telemetry_tool("validate_geometry")
@mcp.tool()
def validate_geometry(ctx: Context, object_name: Optional[str] = None) -> str:
    """
    Run mesh validation on one object or the entire scene.

    Parameters:
    - object_name: Name of a specific object to validate.  If omitted, all
      mesh objects in the scene are validated.

    Checks performed (each issue has a 'severity': CRITICAL / WARNING / INFO):
    - Non-manifold edges                    [CRITICAL]
    - Zero-area faces                       [CRITICAL]
    - Duplicate / overlapping faces         [CRITICAL]
    - Inverted normals (heuristic)          [WARNING]
    - Isolated vertices                     [WARNING]
    - Missing UV map                        [WARNING]
    - Low UV coverage (< 5 %)              [WARNING]
    - Object origin outside ±10 000 m      [WARNING]
    - Unapplied scale (scale != 1,1,1)     [WARNING]
    - Origin far from geometry centre      [INFO]
    - Overlapping objects (same centroid ±0.1 m, scene-wide only) [WARNING]

    Returns JSON for a single object:
      { "object": str, "issues": [...], "clean": bool }
    or for a full-scene run:
      { "scene_clean": bool, "objects": [...], "scene_issues": [...] }
    """
    try:
        blender = get_blender_connection()
        params: dict = {}
        if object_name:
            params["object_name"] = object_name
        result = blender.send_command("validate_geometry", params)
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"validate_geometry error: {e}")
        return json.dumps({"error": str(e)})


# ── 3. take_snapshot ──────────────────────────────────────────────────────────

@telemetry_tool("take_snapshot")
@mcp.tool()
def take_snapshot(ctx: Context, snapshot_id: str) -> str:
    """
    Store the current Blender scene state in memory under snapshot_id.

    The snapshot captures per-object: location, rotation, scale, face count,
    bounding box, and material slot names.  It is held in the addon process
    memory and survives as long as the addon is running.

    Parameters:
    - snapshot_id: Arbitrary string key (e.g. "before_materials").

    Returns JSON:
      { "snapshot_id": str, "object_count": int, "timestamp": str (ISO-8601 UTC) }
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command("take_snapshot", {"snapshot_id": snapshot_id})
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"take_snapshot error: {e}")
        return json.dumps({"error": str(e)})


# ── 4. get_scene_diff ─────────────────────────────────────────────────────────

@telemetry_tool("get_scene_diff")
@mcp.tool()
def get_scene_diff(ctx: Context, snapshot_id: str) -> str:
    """
    Compare the current scene to a previously stored snapshot.

    Parameters:
    - snapshot_id: Key used in a prior take_snapshot() call.

    Returns JSON:
      {
        "snapshot_id": str,
        "snapshot_timestamp": str,
        "added":    [ object_name, ... ],
        "deleted":  [ object_name, ... ],
        "modified": [
          { "name": str, "field": str, "before": any, "after": any, ... },
          ...
        ]
      }

    Modified entries include before/after bounding box and poly count when
    the geometry changed.
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command("get_scene_diff", {"snapshot_id": snapshot_id})
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"get_scene_diff error: {e}")
        return json.dumps({"error": str(e)})


# ── 5. export_usd_tile ────────────────────────────────────────────────────────

@telemetry_tool("export_usd_tile")
@mcp.tool()
def export_usd_tile(
    ctx: Context,
    output_path: str,
    center: list,
    radius_m: float,
) -> str:
    """
    Export a spatial tile as USD (Universal Scene Description).

    Only objects whose world-space origin falls within radius_m metres of
    center are included.  Uses Blender's native USD exporter.

    Parameters:
    - output_path: Absolute filesystem path for the .usd / .usdc / .usda file.
    - center: [x, y] world-space coordinates (Blender units = metres).
    - radius_m: Radius of the tile in metres.

    Returns JSON:
      { "path": str, "file_size_mb": float, "object_count": int }
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command("export_usd_tile", {
            "output_path": output_path,
            "center": center,
            "radius_m": radius_m,
        })
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"export_usd_tile error: {e}")
        return json.dumps({"error": str(e)})


# ── 6. import_osm_tile ────────────────────────────────────────────────────────

@telemetry_tool("import_osm_tile")
@mcp.tool()
def import_osm_tile(
    ctx: Context,
    bbox: dict,
    layer_types: list,
) -> str:
    """
    Import OpenStreetMap data for a lat/lon bounding box from Overpass API.

    Parameters:
    - bbox: { "min_lat": float, "max_lat": float,
               "min_lon": float, "max_lon": float }
    - layer_types: List containing any of:
        "buildings", "roads", "water", "parks", "railways"

    Behaviour:
    - Buildings are extruded using the OSM "height" tag (metres), or
      "building:levels" × 3 m, defaulting to 10 m.
    - Each layer is placed in a dedicated Blender collection.
    - OSM tags and IDs are stored as custom object properties for later use
      by apply_procedural_materials() and other tools.
    - Coordinates are converted from lat/lon to Blender XY using the
      geo-origin set by set_geo_origin() (equirectangular, 1 unit = 1 m).

    Requires set_geo_origin() to have been called first.

    Returns JSON:
      { "objects_created": int, "layers": { layer_name: count, ... } }
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command("import_osm_tile", {
            "bbox": bbox,
            "layer_types": layer_types,
        })
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"import_osm_tile error: {e}")
        return json.dumps({"error": str(e)})


# ── 7. set_geo_origin ─────────────────────────────────────────────────────────

@telemetry_tool("set_geo_origin")
@mcp.tool()
def set_geo_origin(ctx: Context, lat: float, lon: float) -> str:
    """
    Set the geographic origin for the scene.

    All lat/lon coordinates in import_osm_tile() and other tools are
    converted to Blender world-space XY using an equirectangular projection
    relative to this origin (1 Blender unit = 1 metre).

    The origin is stored in scene custom properties and survives file saves.

    Parameters:
    - lat: Latitude in decimal degrees.
    - lon: Longitude in decimal degrees.

    Returns JSON:
      { "lat": float, "lon": float, "stored": true }
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command("set_geo_origin", {"lat": lat, "lon": lon})
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"set_geo_origin error: {e}")
        return json.dumps({"error": str(e)})


# ── 8. import_pointcloud ──────────────────────────────────────────────────────

@telemetry_tool("import_pointcloud")
@mcp.tool()
def import_pointcloud(
    ctx: Context,
    file_path: str,
    voxel_size: float = 0.5,
) -> str:
    """
    Import a LiDAR point cloud (.las or .laz) into Blender.

    Requires laspy to be installed in Blender's Python environment.
    open3d is used for voxel downsampling when available; otherwise a NumPy
    grid-based fallback is used.

    Parameters:
    - file_path: Absolute path to a .las or .laz file.
    - voxel_size: Voxel grid cell size in metres for downsampling (default 0.5).
      Smaller values retain more points; 0.5 works well for urban LiDAR.

    Returns JSON:
      {
        "points_loaded": int,
        "points_after_voxel": int,
        "mesh_created": bool
      }
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command("import_pointcloud", {
            "file_path": file_path,
            "voxel_size": voxel_size,
        })
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"import_pointcloud error: {e}")
        return json.dumps({"error": str(e)})


# ── 9. apply_procedural_materials ─────────────────────────────────────────────

@telemetry_tool("apply_procedural_materials")
@mcp.tool()
def apply_procedural_materials(
    ctx: Context,
    ruleset: str = "default",
) -> str:
    """
    Assign procedural Principled BSDF materials to city objects.

    Materials are chosen based on the object's osm_layer custom property
    (set by import_osm_tile) and additional OSM tag properties:

    - buildings  → concrete / brick / glass depending on osm_building tag
    - roads      → dark asphalt with wave-texture lane markings
    - railways   → same asphalt shader as roads
    - water      → semi-transparent blue Principled BSDF
    - parks      → green Principled BSDF with Musgrave roughness variation

    All materials use node trees; no image textures are required.
    Materials are shared across objects of the same type (by name) to keep
    the .blend file compact.

    Parameters:
    - ruleset: Material ruleset name.  Currently only "default" is supported;
      additional rulesets can be added as JSON files.

    Returns JSON:
      { "ruleset": str, "materials_applied": int }
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command("apply_procedural_materials", {
            "ruleset": ruleset,
        })
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"apply_procedural_materials error: {e}")
        return json.dumps({"error": str(e)})


# ── 10. add_street_detail ─────────────────────────────────────────────────────

@telemetry_tool("add_street_detail")
@mcp.tool()
def add_street_detail(ctx: Context) -> str:
    """
    Add sidewalks, road markings, and curbs to all road objects in the scene.

    For each road object (osm_layer == "roads"):
    - Sidewalk: 2 m wide strip offset from road edge, extruded 0.15 m high,
      concrete/stone material (mat_sidewalk).
    - Road markings: thin emission planes (white, strength=0.3) along road
      centre lines at z=0.01 m.
    - Curb: 0.1 m high, 0.2 m wide strip at road edges (mat_curb).

    Requires roads to have been imported via import_osm_tile() first.

    Returns JSON:
      { "objects_created": int, "roads_processed": int }
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command("add_street_detail")
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"add_street_detail error: {e}")
        return json.dumps({"error": str(e)})


# ── 11. add_vegetation ────────────────────────────────────────────────────────

@telemetry_tool("add_vegetation")
@mcp.tool()
def add_vegetation(ctx: Context, density: float = 0.5) -> str:
    """
    Place LOD trees along road edges in the scene.

    Each tree consists of:
    - Trunk: 8-segment cone/cylinder, radius=0.3 m, height=4 m,
      dark brown Principled BSDF (roughness=0.9).
    - Canopy: subdivided icosphere (2 levels), radius randomly 3–6 m,
      Noise texture driving green color variation
      (0.1,0.4,0.05) → (0.2,0.55,0.1), Translucency/Subsurface=0.3.

    Trees are spaced every 8–12 m along road edges with ±1 m random lateral
    offset so no two rows are perfectly aligned.

    Parameters:
    - density: Fraction of roads that receive trees (0.0–1.0). Default 0.5.

    Returns JSON:
      { "trees_created": int, "roads_sampled": int, "total_roads": int }
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command("add_vegetation", {"density": float(density)})
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"add_vegetation error: {e}")
        return json.dumps({"error": str(e)})


# ── 12. add_ground_detail ─────────────────────────────────────────────────────

@telemetry_tool("add_ground_detail")
@mcp.tool()
def add_ground_detail(ctx: Context) -> str:
    """
    Apply layered ground materials to ground-plane objects based on OSM zone types.

    Zone → material mapping:
    - osm_layer == "roads" / osm_highway in (footway, path):
        footways → pavement stone (0.62,0.60,0.57)
        roads    → dark asphalt with subtle normal bump
    - osm_layer == "parks" / osm_landuse == "grass":
        grass texture (0.10,0.38,0.07)
    - osm_leisure in (plaza, square):
        standard stone tile (0.72,0.70,0.66)
    - Plaça Catalunya (detected by osm_name containing "catalunya"):
        special radial stone-tile material with RINGS wave texture and
        atan2-based UV mapping for concentric tile pattern

    Also sets the GroundPlane fallback mesh (created by render_viewport) to
    the asphalt material.

    Returns JSON:
      { "objects_updated": int }
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command("add_ground_detail")
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"add_ground_detail error: {e}")
        return json.dumps({"error": str(e)})


# ── 13. add_facade_textures ───────────────────────────────────────────────────

@telemetry_tool("add_facade_textures")
@mcp.tool()
def add_facade_textures(ctx: Context) -> str:
    """
    Apply detailed facade materials and geometry to all building objects.

    Per building:
    - UV-projects the real-world footprint coordinates onto facade faces
      (U = world-X normalised by bbox width, V = world-Z normalised by height).
    - Assigns an era-appropriate facade material based on the OSM start_date tag:
        start_date < 1940  → baroque stone (Voronoi bump, roughness 0.80)
        1940–1980          → brutalist concrete (Musgrave roughness 0.80–0.98)
        > 1980 / unknown   → modern glass/panel (IOR 1.52, Fresnel roughness,
                              partial transmission 0.6)
    - Adds a dark aluminium window-frame material (metallic 0.80, roughness 0.30)
      to small inset side-faces (area 0.05–3.0 m²).
    - Assigns a floor-band material to narrow faces near floor-cut heights and
      extrudes those faces 0.1 m outward to create a visible ledge.

    Each building gets three material slots: [facade, window_frame, floor_band].

    Returns JSON:
      { "processed": int, "skipped_count": int, "skipped": [...] }
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command("add_facade_textures")
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"add_facade_textures error: {e}")
        return json.dumps({"error": str(e)})


# ── 14. add_ambient_occlusion ─────────────────────────────────────────────────

@telemetry_tool("add_ambient_occlusion")
@mcp.tool()
def add_ambient_occlusion(ctx: Context) -> str:
    """
    Bake ambient occlusion into vertex colours and wire it into all materials.

    Steps performed:
    1. Temporarily switches to Cycles with 32 samples.
    2. Bakes AO into the "Col" vertex-colour attribute on every mesh object.
    3. In every material that has a Principled BSDF node, inserts a
       MixRGB-Multiply node (factor 0.7) between the existing Base Color
       output and the BSDF input, with the AO vertex-colour feeding Color2.
    4. Restores the previous render engine.

    This fakes contact shadows between buildings without a full path-traced
    render, and is compatible with both Cycles and EEVEE at display time.

    Returns JSON:
      { "baked_count": int, "materials_wired": int,
        "skipped_count": int, "skipped": [...] }
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command("add_ambient_occlusion")
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"add_ambient_occlusion error: {e}")
        return json.dumps({"error": str(e)})


# ── 15. add_road_geometry ─────────────────────────────────────────────────────

@telemetry_tool("add_road_geometry")
@mcp.tool()
def add_road_geometry(ctx: Context) -> str:
    """
    Convert thin road-edge objects into proper-width road meshes.

    Width is determined by the osm_highway custom property on each road object:
      motorway / trunk              → 14 m
      primary / secondary           → 10 m
      tertiary / residential        → 6 m
      footway / path / cycleway     → 2 m
      (other / unclassified)        → 6 m

    For each road object:
    - Builds a quad-strip road surface with a 2 % camber (cross-slope)
      so the centre is slightly higher than the edges for drainage.
    - Creates a separate lane-marking mesh: dashed white emission strips
      (0.15 m wide, strength=0.5) every 3 m along the centre line.
      Footways and paths do not receive lane markings.
    - Tags each new mesh object with osm_layer="roads" so subsequent tools
      (add_street_detail, add_ground_detail, etc.) recognise it.

    Returns JSON:
      { "road_meshes_created": int, "marking_meshes_created": int,
        "roads_processed": int }
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command("add_road_geometry")
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"add_road_geometry error: {e}")
        return json.dumps({"error": str(e)})


# ── 16. add_lighting_setup ────────────────────────────────────────────────────

@telemetry_tool("add_lighting_setup")
@mcp.tool()
def add_lighting_setup(
    ctx: Context,
    time_of_day: str = "golden_hour",
) -> str:
    """
    Configure scene lighting for the requested time of day.

    Parameters:
    - time_of_day: One of "morning", "noon", "golden_hour", "night".

    Preset details:
    - "golden_hour": Sun elevation 8°, warm orange-gold (1.0,0.85,0.6),
                     energy 3, long low shadows.
    - "noon":        Sun elevation 70°, near-white (1.0,1.0,0.98), energy 5.
    - "morning":     Sun elevation 20°, cool blue-white (0.85,0.92,1.0), energy 4.
    - "night":       No sun lamp. Adds:
                     • Point street lamps every 20 m along road edges
                       (warm 2700 K, energy=100, radius=0.3 m).
                     • Night-emission material variants for 30 % of window/glass
                       materials (warm interior glow, strength=2).

    All presets add a subtle hemisphere sky fill light (blue, strength=0.5).
    Previously added city lights are removed before applying new ones.

    Returns JSON:
      { "time_of_day": str, "lights_added": int }
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command("add_lighting_setup", {
            "time_of_day": time_of_day,
        })
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"add_lighting_setup error: {e}")
        return json.dumps({"error": str(e)})


# ── 17. generate_facade_geometry ─────────────────────────────────────────────

@telemetry_tool("generate_facade_geometry")
@mcp.tool()
def generate_facade_geometry(
    ctx: Context,
    object_name: Optional[str] = None,
) -> str:
    """
    Generate full procedural 3D facade relief geometry on buildings.

    Creates real vertices — not textures — for every architectural element.
    If object_name is omitted, all buildings (osm_layer == "buildings") are
    processed.  Buildings with footprint > 1 000 m² or fewer than 4 wall faces
    are skipped and reported.

    Processing pipeline per building:

    Step 1 — Wall panels
      Vertical faces (|normal.z| < 0.15) are identified and grouped by floor
      level (every 3 m of building height).

    Step 2 — Window openings
      Each panel wider than 1.5 m receives inset+reveal windows:
        residential    → 0.9 m × 1.4 m, spaced every 2.5 m
        commercial GF  → shopfront 80 % of panel width
        office         → ribbon 70 % width × 0.8 m tall
      Each window: inset border (frame), inner face extruded 0.12 m inward
      (wall reveal), child sill mesh 0.06 m outward.

    Step 3 — Balconies  (residential, south-facing, every 2nd floor)
      Slab 0.9 m deep × 0.15 m thick; vertical railing bars every 0.15 m,
      1.0 m tall, r = 0.02 m; connecting top rail.

    Step 4 — Era ornament  (from OSM start_date tag)
      pre-1940:    Voronoi-bump stone wall; pilasters every 3–4 m; 3-step
                   cornice extruded at roof level.
      1940–1980:   Musgrave concrete; horizontal brise-soleil fins 0.3 m
                   deep above windows; flat roof parapet 0.4 m tall.
      post-1980:   Fresnel glass curtain wall; top-20 % setback 0.5 m;
                   rooftop mechanical box 40 % footprint area × 2 m tall.

    Step 5 — Roof details
      All styles: parapet ring 0.3 m tall at roofline.
      Residential: water tank cylinder + TV antenna pole.
      Commercial:  AC unit boxes (2–5, random size) + skylight panel.

    Step 6 — Materials (shared named materials, node-based)
      facade_wall_stone / _brick / _concrete / _glass_curtain
      facade_window_glass (transmission 0.90)
      facade_window_frame_aluminium (metallic 0.90, roughness 0.20)
      facade_balcony_concrete / facade_balcony_railing_metal
      facade_cornice_stone / facade_roof_gravel / facade_brise_soleil

    Returns JSON:
      {
        "buildings_processed": int,
        "total_windows":       int,
        "total_balconies":     int,
        "reports": [
          {
            "object":          str,
            "faces_before":    int,
            "faces_after":     int,
            "style":           "pre1940" | "brutalist" | "contemporary",
            "windows_created": int,
            "balconies_created": int,
            "errors":          [str, ...]
          },
          ...
        ]
      }
    """
    try:
        blender = get_blender_connection()
        params: dict = {}
        if object_name:
            params["object_name"] = object_name
        result = blender.send_command("generate_facade_geometry", params)
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"generate_facade_geometry error: {e}")
        return json.dumps({"error": str(e)})


# ── 18. generate_building_detail ──────────────────────────────────────────────

@telemetry_tool("generate_building_detail")
@mcp.tool()
def generate_building_detail(
    ctx: Context,
    object_name: Optional[str] = None,
    lod: Optional[int] = None,
) -> str:
    """
    Apply LOD-based geometric detail to one building object or all buildings.

    Parameters:
    - object_name: Name of a specific building object. If omitted, all buildings
      in the scene are processed.
    - lod: Level of detail (0, 1, or 2). If omitted, auto-selected by footprint area:
        area > 500 m²  → lod 0 (simple box, no modification)
        100–500 m²     → lod 1 (floor subdivisions + window insets)
        < 100 m²       → lod 2 (floor cuts + windows + cornice + balconies)

    LOD descriptions:
    - lod 0: No change. Fast path for large/complex footprints.
    - lod 1: Horizontal loop cuts every 3 m of height; window insets per facade panel
             (depth=0.15 m, thickness varies by use: commercial=larger).
             Industrial/warehouse/garage buildings get no windows.
    - lod 2: All of lod 1, plus rooftop cornice (0.3 m outward extrusion) and
             balconies on residential buildings (inset slab every other floor).

    After each object: recalculates normals, removes zero-area faces, and
    runs Smart UV Project unwrap. Objects that fail validation are skipped and
    logged in the response.

    Returns JSON:
      { "processed": int, "skipped_count": int, "skipped": [...] }
    """
    try:
        blender = get_blender_connection()
        params: dict = {}
        if object_name:
            params["object_name"] = object_name
        if lod is not None:
            params["lod"] = int(lod)
        result = blender.send_command("generate_building_detail", params)
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"generate_building_detail error: {e}")
        return json.dumps({"error": str(e)})


# ── 18. set_render_settings ───────────────────────────────────────────────────

@telemetry_tool("set_render_settings")
@mcp.tool()
def set_render_settings(ctx: Context) -> str:
    """
    Configure the Blender scene for a high-quality Cycles render.

    Settings applied:
    - Render engine: CYCLES, samples=256, denoising ON
    - Resolution: 1920×1080
    - World: Hosek-Wilkie Sky Texture, sun elevation=25°,
             sun rotation derived from scene geo_origin longitude
    - Sun lamp: SUN type, energy=5, angle=0.5°, rotation matches sky
    - Exposure: 0.5, Color management: Filmic / High Contrast

    Returns JSON with all applied settings.
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command("set_render_settings")
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"set_render_settings error: {e}")
        return json.dumps({"error": str(e)})


# ── 19. render_viewport ───────────────────────────────────────────────────────

@telemetry_tool("render_viewport")
@mcp.tool()
def render_viewport(
    ctx: Context,
    output_path: str,
    camera_preset: str = "isometric",
) -> str:
    """
    Render the city scene to a PNG file using a preset camera.

    Parameters:
    - output_path: Absolute filesystem path for the output .png file.
    - camera_preset: One of:
        "street_level" — perspective camera at z=1.8 m, 50 mm focal length,
                         pointing along the first detected road axis.
        "aerial"       — orthographic camera at z=500 m pointing straight down,
                         ortho scale covering the full scene bounding box.
        "isometric"    — perspective camera at 45° angle, z=200+ m, 85 mm lens,
                         covering the full scene diagonal.

    Uses the current render engine and sample settings (call set_render_settings()
    first for best quality).

    Returns JSON:
      { "output_path": str, "camera_preset": str,
        "render_time_s": float, "file_size_mb": float }
    """
    try:
        blender = get_blender_connection()
        result = blender.send_command("render_viewport", {
            "output_path": output_path,
            "camera_preset": camera_preset,
        })
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"render_viewport error: {e}")
        return json.dumps({"error": str(e)})


# ── 20. orchestrate_procedural_buildings ──────────────────────────────────────

@telemetry_tool("orchestrate_procedural_buildings")
@mcp.tool()
def orchestrate_procedural_buildings(
    ctx: Context,
    bbox: list,
    style_override: Optional[str] = None,
    origin_lat: Optional[float] = None,
    origin_lon: Optional[float] = None,
    page: int = 0,
) -> str:
    """
    Fetch OSM building data for a bounding box, classify every building,
    infer architectural styles, and return a procedural-generation payload
    ready for the Blender addon.

    This tool runs entirely in the MCP server process (no Blender socket call).
    It calls the Overpass API directly, so Blender does not need to be open.

    Parameters
    ----------
    bbox : [min_lat, min_lon, max_lat, max_lon]
        Geographic bounding box in decimal degrees.
        Example: [41.383, 2.168, 41.390, 2.178]  (part of Barcelona Eixample)
    style_override : str | None
        If supplied, every procedural building receives this style string
        instead of the auto-inferred one.  Accepted values (case-insensitive):
          CLASSICAL_MODERNISTA, BRUTALIST, CONTEMPORARY,
          RESIDENTIAL_STANDARD, COMMERCIAL_STANDARD
    origin_lat, origin_lon : float | None
        If supplied, footprint coordinates in the dispatch payload are
        projected to Blender world-space metres using the same equirectangular
        formula as import_osm_tile().  If omitted, raw lat/lon pairs are
        returned instead and the caller must project them before use.
    page : int
        Zero-based page index for pagination.  Each page returns at most 500
        buildings.  Check has_more / next_page in the response to continue.

    Pipeline
    --------
    Step 1 — Fetch
        Queries Overpass API for all ways/relations tagged building=*.
        Resolves node references, projects coordinates, calculates footprint
        area (shoelace formula) and centroid.

    Step 2 — Classify
        Buildings are tagged LOD3_TARGET if:
          • any of historic / tourism / monument / landmark / heritage tags
            are present, OR
          • footprint area > 2 000 m², OR
          • building value is cathedral / church / castle / palace / museum etc.
        All others are tagged LOD2_PROCEDURAL and proceed.

    Step 3 — Infer style
        If style_override is set, use it.  Otherwise:
          start_date < 1940       → CLASSICAL_MODERNISTA
          1940 ≤ start_date < 1980 → BRUTALIST
          start_date ≥ 1980       → CONTEMPORARY
          No date + area < 200 m² → RESIDENTIAL_STANDARD
          No date + area ≥ 200 m² → COMMERCIAL_STANDARD

    Step 4 — Parameters
        Height:    height tag > levels × 3.5 m > default (14 m / 21 m).
        Roof:      roof:shape gabled/hipped/… → PITCHED, else FLAT_WITH_PARAPET.
        Materials: building:material mapped to palette IDs; style-based fallback.

    Step 5 — Payload assembly
        Each building becomes a JSON object:
          osm_id, footprint [[x,y],…], centroid [x,y], area_m2,
          height, use, style, roof_type,
          materials {wall, roof, window_glass, window_frame, balcony,
                     balcony_rail},
          osm_tags {building, building:levels, start_date,
                    building:material, roof:shape, name}

    Step 6 — Performance
        Maximum 500 buildings per call.  If more exist, has_more=true and
        next_page gives the index to pass on the next call.

    Returns JSON
    ------------
    {
      "processed_count":   int,   // buildings in this batch
      "skipped_landmarks": int,   // LOD3_TARGET buildings excluded
      "total_found":       int,   // total ways found by Overpass
      "has_more":          bool,
      "next_page":         int | null,
      "dispatch_batch": [
        {
          "osm_id":     str,
          "footprint":  [[x, y], ...],
          "centroid":   [x, y],
          "area_m2":    float,
          "height":     float,
          "use":        str,
          "style":      str,
          "roof_type":  str,
          "materials":  { wall, roof, window_glass, window_frame,
                          balcony, balcony_rail },
          "osm_tags":   { building, building:levels, start_date,
                          building:material, roof:shape, name }
        },
        ...
      ],
      "errors": [str, ...]
    }
    """
    try:
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            return json.dumps({
                "error": "bbox must be [min_lat, min_lon, max_lat, max_lon]"})

        bbox_f = [float(v) for v in bbox]

        result = osm_client.orchestrate(
            bbox=bbox_f,
            style_override=style_override,
            origin_lat=float(origin_lat) if origin_lat is not None else None,
            origin_lon=float(origin_lon) if origin_lon is not None else None,
            page=int(page),
        )
        return json.dumps(result, indent=2)

    except Exception as e:
        logger.error(f"orchestrate_procedural_buildings error: {e}")
        return json.dumps({"error": str(e)})
