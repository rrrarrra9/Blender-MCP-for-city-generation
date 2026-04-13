"""
OSM / Overpass client for the blender-mcp MCP server.

Pure Python — no Blender dependency.  Fetches building data from the
Overpass API, classifies buildings, infers architectural styles, and
constructs procedural-generation payloads ready for the Blender addon.
"""

from __future__ import annotations

import logging
import math
import re
import time
from typing import Any, Optional

import requests

logger = logging.getLogger("BlenderMCPOSMClient")

# ── Constants ─────────────────────────────────────────────────────────────────

OVERPASS_URL  = "https://overpass-api.de/api/interpreter"
OVERPASS_TIMEOUT = 90          # seconds for HTTP request
BATCH_LIMIT   = 500            # max buildings per execution
EARTH_RADIUS  = 6_371_000.0    # metres

# Tags that flag a building as a notable landmark
LANDMARK_TAGS = frozenset({
    "historic", "tourism", "monument", "landmark",
    "heritage", "archaeological_site",
})

# OSM roof:shape values that map to PITCHED roof type
PITCHED_ROOFS = frozenset({
    "gabled", "hipped", "half-hipped", "gambrel",
    "mansard", "dome", "onion", "pyramidal",
})

# building:material → palette id
MATERIAL_MAP: dict[str, str] = {
    "brick":         "BRICK",
    "stone":         "STONE",
    "concrete":      "CONCRETE",
    "glass":         "GLASS_CURTAIN",
    "wood":          "WOOD",
    "metal":         "METAL_PANEL",
    "plaster":       "PLASTER",
    "render":        "PLASTER",
    "stucco":        "PLASTER",
    "sandstone":     "STONE",
    "limestone":     "STONE",
    "granite":       "STONE",
    "steel":         "METAL_PANEL",
    "aluminum":      "METAL_PANEL",
    "aluminium":     "METAL_PANEL",
}

# Default levels when not specified
DEFAULT_LEVELS_RESIDENTIAL  = 4
DEFAULT_LEVELS_COMMERCIAL    = 6
METRES_PER_LEVEL             = 3.5


# ── Geo utilities ──────────────────────────────────────────────────────────────

def latlon_to_xy(
    lat: float, lon: float,
    origin_lat: float, origin_lon: float,
) -> tuple[float, float]:
    """
    Equirectangular projection: 1 unit = 1 metre, matching the addon's
    _latlon_to_xy() implementation exactly.
    """
    x = math.radians(lon - origin_lon) * EARTH_RADIUS * math.cos(math.radians(origin_lat))
    y = math.radians(lat - origin_lat) * EARTH_RADIUS
    return x, y


def _polygon_area_and_centroid(
    coords: list[tuple[float, float]],
) -> tuple[float, tuple[float, float]]:
    """
    Shoelace formula for signed area and centroid of a 2-D polygon.
    Returns (area_m2, (cx, cy)).  Area is always positive.
    """
    n = len(coords)
    if n < 3:
        return 0.0, (0.0, 0.0)
    area2 = 0.0
    cx = cy = 0.0
    for i in range(n):
        j = (i + 1) % n
        cross = coords[i][0] * coords[j][1] - coords[j][0] * coords[i][1]
        area2 += cross
        cx    += (coords[i][0] + coords[j][0]) * cross
        cy    += (coords[i][1] + coords[j][1]) * cross
    area = abs(area2) / 2.0
    if area < 1e-9:
        xs = [c[0] for c in coords]
        ys = [c[1] for c in coords]
        return area, (sum(xs) / n, sum(ys) / n)
    denom = 3.0 * area2   # signed, so centroid formula works for CW and CCW
    cx /= denom
    cy /= denom
    return area, (cx, cy)


# ── Year parsing ───────────────────────────────────────────────────────────────

def _parse_year(raw: str) -> Optional[int]:
    """Extract the first 4-digit year from an OSM date string."""
    m = re.search(r'\b(\d{4})\b', raw)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass
    return None


# ── Building classification ────────────────────────────────────────────────────

def _is_landmark(tags: dict[str, str], area_m2: float) -> bool:
    """Return True if the building should be treated as LOD3 / landmark."""
    if area_m2 > 2000.0:
        return True
    for key in LANDMARK_TAGS:
        if key in tags:
            return True
    # tourism / historic values on the *building* tag itself
    building_val = tags.get("building", "").lower()
    if building_val in ("cathedral", "church", "castle", "monastery",
                         "temple", "mosque", "synagogue", "museum",
                         "palace", "ruins"):
        return True
    return False


def _infer_use(tags: dict[str, str]) -> str:
    """Map OSM tags to a simplified use string."""
    bval = tags.get("building", "yes").lower()
    if bval in ("commercial", "retail", "shop", "supermarket",
                "kiosk", "mall"):
        return "commercial"
    if bval in ("office", "government", "civic", "public"):
        return "office"
    if bval in ("industrial", "warehouse", "factory", "garage",
                "storage_tank"):
        return "industrial"
    if bval in ("house", "residential", "apartments", "flat",
                "dormitory", "terrace", "bungalow", "detached",
                "semidetached_house"):
        return "residential"
    # Fallback: amenity tag
    amenity = tags.get("amenity", "").lower()
    if amenity in ("bank", "restaurant", "cafe", "bar", "fast_food",
                   "hotel", "hostel", "marketplace"):
        return "commercial"
    if amenity in ("school", "university", "college", "hospital",
                   "clinic", "police", "fire_station"):
        return "office"
    return "residential"


def _infer_style(
    tags: dict[str, str],
    area_m2: float,
    style_override: Optional[str],
) -> str:
    """Determine architectural style string."""
    if style_override:
        return style_override.upper()

    # Try date-based classification first
    for key in ("start_date", "construction_date", "age", "year_built"):
        raw = tags.get(key, "")
        if raw:
            year = _parse_year(raw)
            if year is not None:
                if year < 1940:
                    return "CLASSICAL_MODERNISTA"
                if year < 1980:
                    return "BRUTALIST"
                return "CONTEMPORARY"

    # Fallback: footprint area heuristic
    if area_m2 < 200.0:
        return "RESIDENTIAL_STANDARD"
    return "COMMERCIAL_STANDARD"


def _calc_height(tags: dict[str, str], use: str) -> float:
    """Derive building height in metres from OSM tags."""
    # Explicit height tag wins
    height_raw = tags.get("height", tags.get("building:height", ""))
    if height_raw:
        m = re.search(r'[\d.]+', height_raw)
        if m:
            try:
                return float(m.group())
            except ValueError:
                pass

    # Level count
    for key in ("building:levels", "levels"):
        raw = tags.get(key, "")
        if raw:
            try:
                return float(raw) * METRES_PER_LEVEL
            except ValueError:
                pass

    # Default by use
    if use == "commercial" or use == "office":
        return DEFAULT_LEVELS_COMMERCIAL * METRES_PER_LEVEL
    return DEFAULT_LEVELS_RESIDENTIAL * METRES_PER_LEVEL


def _roof_type(tags: dict[str, str]) -> str:
    """Map roof:shape tag to a procedural roof identifier."""
    shape = tags.get("roof:shape", "").lower()
    if shape in PITCHED_ROOFS:
        return "PITCHED"
    return "FLAT_WITH_PARAPET"


def _material_palette(tags: dict[str, str], style: str) -> dict[str, str]:
    """
    Build a material-assignment dict.

    Keys are element names (wall, roof, window_frame); values are palette IDs.
    """
    raw_mat = tags.get("building:material", tags.get("material", "")).lower()
    wall_id = MATERIAL_MAP.get(raw_mat)

    # If no explicit material, derive from style
    if wall_id is None:
        if style == "CLASSICAL_MODERNISTA":
            wall_id = "STONE"
        elif style == "BRUTALIST":
            wall_id = "CONCRETE"
        elif style in ("CONTEMPORARY", "COMMERCIAL_STANDARD"):
            wall_id = "GLASS_CURTAIN"
        else:
            wall_id = "BRICK"

    roof_mat_raw = tags.get("roof:material", "").lower()
    roof_id = MATERIAL_MAP.get(roof_mat_raw, "ROOF_GRAVEL")

    return {
        "wall":           wall_id,
        "roof":           roof_id,
        "window_glass":   "WINDOW_GLASS",
        "window_frame":   "WINDOW_FRAME_ALU",
        "balcony":        "BALCONY_CONCRETE",
        "balcony_rail":   "BALCONY_RAILING",
    }


# ── Overpass fetch ─────────────────────────────────────────────────────────────

def fetch_buildings(
    bbox: list[float],
    origin_lat: Optional[float] = None,
    origin_lon: Optional[float] = None,
    retries: int = 2,
) -> dict[str, Any]:
    """
    Query Overpass for all buildings in *bbox* = [min_lat, min_lon, max_lat, max_lon].

    Returns a dict:
      {
        "elements":  list of raw OSM element dicts (ways + nodes),
        "nodes":     { osm_id: (lat, lon) },
        "ways":      [ { id, tags, node_ids, footprint_xy?, area_m2?, centroid? } ],
        "error":     str | None,
      }

    If origin_lat/origin_lon are supplied, footprint_xy coordinates (in metres
    relative to that origin) are added to each way entry.
    """
    min_lat, min_lon, max_lat, max_lon = bbox
    bbox_str = f"{min_lat},{min_lon},{max_lat},{max_lon}"

    query = f"""
[out:json][timeout:60];
(
  way["building"]({bbox_str});
  relation["building"]({bbox_str});
);
out body;
>;
out skel qt;
"""

    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = requests.post(
                OVERPASS_URL,
                data={"data": query},
                timeout=OVERPASS_TIMEOUT,
                headers={"User-Agent": "blender-mcp/1.0"},
            )
            resp.raise_for_status()
            raw = resp.json()
            break
        except Exception as exc:
            last_exc = exc
            logger.warning(f"Overpass attempt {attempt+1} failed: {exc}")
            if attempt < retries:
                time.sleep(2 ** attempt)   # 1s, 2s back-off
    else:
        return {"elements": [], "nodes": {}, "ways": [],
                "error": f"Overpass request failed: {last_exc}"}

    # Index all nodes
    nodes: dict[int, tuple[float, float]] = {}
    for el in raw.get("elements", []):
        if el["type"] == "node":
            nodes[el["id"]] = (el["lat"], el["lon"])

    # Process ways
    ways: list[dict[str, Any]] = []
    for el in raw.get("elements", []):
        if el["type"] != "way":
            continue
        node_ids  = el.get("nodes", [])
        tags      = el.get("tags", {})
        # Resolve lat/lon for each node ref
        latlon_pts = [nodes[n] for n in node_ids if n in nodes]
        if len(latlon_pts) < 3:
            continue

        entry: dict[str, Any] = {
            "id":       el["id"],
            "tags":     tags,
            "node_ids": node_ids,
            "latlon":   latlon_pts,
        }

        # XY projection if origin is known
        if origin_lat is not None and origin_lon is not None:
            xy = [latlon_to_xy(lat, lon, origin_lat, origin_lon)
                  for lat, lon in latlon_pts]
            area, centroid = _polygon_area_and_centroid(xy)
            entry["footprint_xy"] = [[round(x, 3), round(y, 3)] for x, y in xy]
            entry["area_m2"]      = round(area, 2)
            entry["centroid"]     = [round(centroid[0], 3), round(centroid[1], 3)]
        else:
            # Approximate area in m² from lat/lon directly
            xy_approx = [
                latlon_to_xy(lat, lon,
                             latlon_pts[0][0], latlon_pts[0][1])
                for lat, lon in latlon_pts
            ]
            area, centroid_approx = _polygon_area_and_centroid(xy_approx)
            entry["area_m2"] = round(area, 2)
            # Store geographic centroid
            clat = sum(p[0] for p in latlon_pts) / len(latlon_pts)
            clon = sum(p[1] for p in latlon_pts) / len(latlon_pts)
            entry["centroid_latlon"] = [round(clat, 7), round(clon, 7)]

        ways.append(entry)

    return {"elements": raw.get("elements", []), "nodes": nodes,
            "ways": ways, "error": None}


# ── Main orchestration ─────────────────────────────────────────────────────────

def orchestrate(
    bbox: list[float],
    style_override: Optional[str],
    origin_lat: Optional[float] = None,
    origin_lon: Optional[float] = None,
    page: int = 0,
) -> dict[str, Any]:
    """
    Full pipeline: fetch → classify → style → parameters → payload.

    Returns:
      {
        "processed_count":   int,
        "skipped_landmarks": int,
        "total_found":       int,
        "has_more":          bool,
        "next_page":         int | None,
        "dispatch_batch":    [ BuildingPayload, ... ],
        "errors":            [ str, ... ],
      }
    """
    errors: list[str] = []

    # ── Step 1: fetch ─────────────────────────────────────────────────────────
    fetch_result = fetch_buildings(bbox, origin_lat, origin_lon)
    if fetch_result.get("error"):
        return {
            "processed_count":   0,
            "skipped_landmarks": 0,
            "total_found":       0,
            "has_more":          False,
            "next_page":         None,
            "dispatch_batch":    [],
            "errors":            [fetch_result["error"]],
        }

    ways = fetch_result["ways"]
    total_found = len(ways)

    # ── Step 2: classify ──────────────────────────────────────────────────────
    lod2_ways: list[dict[str, Any]] = []
    skipped_landmarks = 0

    for way in ways:
        tags     = way["tags"]
        area_m2  = way.get("area_m2", 0.0)
        if _is_landmark(tags, area_m2):
            skipped_landmarks += 1
            way["priority"] = "LOD3_TARGET"
        else:
            way["priority"] = "LOD2_PROCEDURAL"
            lod2_ways.append(way)

    # ── Pagination ────────────────────────────────────────────────────────────
    start    = page * BATCH_LIMIT
    end      = start + BATCH_LIMIT
    has_more = end < len(lod2_ways)
    batch    = lod2_ways[start:end]

    # ── Steps 3–5: per-building classification & payload assembly ─────────────
    dispatch_batch: list[dict[str, Any]] = []

    for way in batch:
        try:
            tags    = way["tags"]
            area_m2 = way.get("area_m2", 0.0)
            use     = _infer_use(tags)
            style   = _infer_style(tags, area_m2, style_override)
            height  = _calc_height(tags, use)
            roof    = _roof_type(tags)
            palette = _material_palette(tags, style)

            # Footprint: prefer projected XY, fall back to lat/lon
            if "footprint_xy" in way:
                footprint = way["footprint_xy"]
                centroid  = way["centroid"]
            else:
                # No origin provided — return geographic lat/lon pairs
                footprint = [[round(p[1], 7), round(p[0], 7)]
                             for p in way["latlon"]]   # [lon, lat] convention
                centroid  = way.get("centroid_latlon", [0.0, 0.0])

            payload: dict[str, Any] = {
                "osm_id":     str(way["id"]),
                "footprint":  footprint,
                "centroid":   centroid,
                "area_m2":    area_m2,
                "height":     round(height, 2),
                "use":        use,
                "style":      style,
                "roof_type":  roof,
                "materials":  palette,
                # Pass through useful OSM tags for the Blender addon
                "osm_tags": {
                    "building":          tags.get("building", "yes"),
                    "building:levels":   tags.get("building:levels", ""),
                    "start_date":        tags.get("start_date", ""),
                    "building:material": tags.get("building:material", ""),
                    "roof:shape":        tags.get("roof:shape", ""),
                    "name":              tags.get("name", ""),
                },
            }
            dispatch_batch.append(payload)

        except Exception as exc:
            errors.append(f"osm_id={way.get('id', '?')}: {exc}")

    return {
        "processed_count":   len(dispatch_batch),
        "skipped_landmarks": skipped_landmarks,
        "total_found":       total_found,
        "has_more":          has_more,
        "next_page":         (page + 1) if has_more else None,
        "dispatch_batch":    dispatch_batch,
        "errors":            errors,
    }
