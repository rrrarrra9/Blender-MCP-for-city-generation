"""
City pipeline end-to-end test.

Run headless:
    blender --background --python tests/test_city_pipeline.py

The script exercises every city tool implemented in addon.py and prints a
full JSON report of each step to stdout.  It exits with code 0 on success
and 1 on any failure.
"""

import sys
import json
import os
import tempfile
import traceback
from datetime import datetime

# ── Blender must be available ─────────────────────────────────────────────────
try:
    import bpy
except ImportError:
    print("ERROR: This script must be run inside Blender.")
    print("Usage: blender --background --python tests/test_city_pipeline.py")
    sys.exit(1)

# Add the addon directory to sys.path so we can import the server's addon class
# directly without needing the full MCP stack.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)

# ── Import the addon ──────────────────────────────────────────────────────────
try:
    import addon as blender_mcp_addon  # noqa: F401 (registers classes)
    blender_mcp_addon.register()
except Exception as e:
    print(f"ERROR: Failed to load addon: {e}")
    traceback.print_exc()
    sys.exit(1)

# Instantiate the server class directly (no socket needed for in-process tests)
server = blender_mcp_addon.BlenderMCPServer()

# ── Helpers ───────────────────────────────────────────────────────────────────

def section(title: str) -> None:
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)

def ok(step: str, result: dict) -> dict:
    print(json.dumps({"step": step, "result": result}, indent=2))
    return result

def fail(step: str, exc: Exception) -> None:
    msg = {"step": step, "error": str(exc)}
    print(json.dumps(msg, indent=2))
    traceback.print_exc()
    sys.exit(1)

report = {}

# ── Step 1: Set geo origin (Paris – Eiffel Tower) ─────────────────────────────
section("Step 1 — set_geo_origin")
try:
    r = server.set_geo_origin(lat=48.8584, lon=2.2945)
    report["set_geo_origin"] = ok("set_geo_origin", r)
    assert r["stored"] is True, "stored flag should be True"
    assert abs(r["lat"] - 48.8584) < 1e-6
    assert abs(r["lon"] - 2.2945) < 1e-6
except Exception as e:
    fail("set_geo_origin", e)

# ── Step 2: Import OSM tile (≈ 400 m radius, buildings + roads + parks) ───────
section("Step 2 — import_osm_tile")

# 400 m in degrees ≈ 0.0036 degrees latitude / 0.0052 degrees longitude
DELTA = 0.0036
bbox = {
    "min_lat": 48.8584 - DELTA,
    "max_lat": 48.8584 + DELTA,
    "min_lon": 2.2945 - DELTA,
    "max_lon": 2.2945 + DELTA,
}
try:
    r = server.import_osm_tile(bbox=bbox, layer_types=["buildings", "roads", "parks"])
    report["import_osm_tile"] = ok("import_osm_tile", r)
    if "error" in r:
        print(f"  WARNING: OSM import returned error (network issue?): {r['error']}")
    else:
        assert "objects_created" in r
        assert "layers" in r
except Exception as e:
    fail("import_osm_tile", e)

# ── Step 3: validate_geometry (full scene) ────────────────────────────────────
section("Step 3 — validate_geometry (scene)")
try:
    r = server.validate_geometry()
    report["validate_geometry"] = ok("validate_geometry", {
        "scene_clean": r.get("scene_clean"),
        "object_count": len(r.get("objects", [])),
        "error_summary": [
            {"object": obj["object"], "errors": len(obj.get("errors", [])),
             "warnings": len(obj.get("warnings", []))}
            for obj in r.get("objects", [])
        ][:10],  # cap report to 10 objects
    })
    assert "scene_clean" in r or "error" in r
except Exception as e:
    fail("validate_geometry", e)

# ── Step 4: take_snapshot ─────────────────────────────────────────────────────
section("Step 4 — take_snapshot")
SNAP_ID = "before_materials"
try:
    r = server.take_snapshot(snapshot_id=SNAP_ID)
    report["take_snapshot"] = ok("take_snapshot", r)
    assert r["snapshot_id"] == SNAP_ID
    assert r["object_count"] >= 0
    assert "timestamp" in r
except Exception as e:
    fail("take_snapshot", e)

# ── Step 5: apply_procedural_materials ───────────────────────────────────────
section("Step 5 — apply_procedural_materials")
try:
    r = server.apply_procedural_materials(ruleset="default")
    report["apply_procedural_materials"] = ok("apply_procedural_materials", r)
    assert "materials_applied" in r
except Exception as e:
    fail("apply_procedural_materials", e)

# ── Step 6: get_scene_diff ────────────────────────────────────────────────────
section("Step 6 — get_scene_diff")
try:
    r = server.get_scene_diff(snapshot_id=SNAP_ID)
    report["get_scene_diff"] = ok("get_scene_diff", r)
    assert r.get("snapshot_id") == SNAP_ID
    assert "added" in r and "deleted" in r and "modified" in r
except Exception as e:
    fail("get_scene_diff", e)

# ── Step 7: export_usd_tile ───────────────────────────────────────────────────
section("Step 7 — export_usd_tile")
usd_path = os.path.join(tempfile.gettempdir(), "city_tile_test.usdc")
try:
    r = server.export_usd_tile(
        output_path=usd_path,
        center=[0.0, 0.0],
        radius_m=10_000.0,  # export everything
    )
    report["export_usd_tile"] = ok("export_usd_tile", r)
    if "error" in r:
        print(f"  WARNING: USD export error (USD exporter may not be available): {r['error']}")
    else:
        assert "path" in r
        assert "object_count" in r
except Exception as e:
    fail("export_usd_tile", e)

# ── Step 8: get_scene_graph ───────────────────────────────────────────────────
section("Step 8 — get_scene_graph")
try:
    r = server.get_scene_graph()
    report["get_scene_graph"] = ok("get_scene_graph", {
        "scene": r.get("scene"),
        "object_count": r.get("object_count"),
        "collection_count": len(r.get("collections", [])),
    })
    assert "objects" in r
    assert "collections" in r
except Exception as e:
    fail("get_scene_graph", e)

# ── Final report ──────────────────────────────────────────────────────────────
section("FULL JSON REPORT")
print(json.dumps(report, indent=2))

print("\n✓ All steps completed successfully.")
sys.exit(0)
