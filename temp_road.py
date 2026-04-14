def add_road_geometry(self):
        """Convert road-edge objects into proper width meshes with camber and lane markings."""
        import bmesh as _bm
        import math

        scene = bpy.context.scene

        # Width table (metres) keyed on osm_highway value
        WIDTHS = {
            "motorway": 14.0, "motorway_link": 10.0,
            "trunk": 14.0,    "trunk_link": 10.0,
            "primary": 10.0,  "primary_link": 8.0,
            "secondary": 10.0,"secondary_link": 8.0,
            "tertiary": 6.0,  "tertiary_link": 5.0,
            "residential": 6.0, "living_street": 5.0,
            "service": 4.0,   "track": 3.0,
            "footway": 2.0,   "path": 2.0,
            "cycleway": 2.0,  "pedestrian": 4.0,
            "steps": 1.5,     "unclassified": 6.0,
        }
        DEFAULT_WIDTH = 6.0
        CAMBER = 0.02   # 2 % cross-slope

        def _road_mat():
            name = "mat_road_proper"
            if name in bpy.data.materials:
                return bpy.data.materials[name]
            mat = bpy.data.materials.new(name)
            mat.use_nodes = True
            nt = mat.node_tree; nt.nodes.clear()
            out  = nt.nodes.new("ShaderNodeOutputMaterial"); out.location  = (500,0)
            bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled"); bsdf.location = (200,0)
            bsdf.inputs["Base Color"].default_value = (0.07, 0.07, 0.07, 1.0)
            bsdf.inputs["Roughness"].default_value  = 0.95
            noise = nt.nodes.new("ShaderNodeTexNoise"); noise.location = (-200,-100)
            noise.inputs["Scale"].default_value = 50.0
            bump  = nt.nodes.new("ShaderNodeBump");   bump.location  = (0,-150)
            bump.inputs["Strength"].default_value = 0.08
            nt.links.new(noise.outputs["Fac"],  bump.inputs["Height"])
            nt.links.new(bump.outputs["Normal"],bsdf.inputs["Normal"])
            nt.links.new(bsdf.outputs["BSDF"],  out.inputs["Surface"])
            return mat

        def _marking_mat():
            name = "mat_lane_marking"
            if name in bpy.data.materials:
                return bpy.data.materials[name]
            mat = bpy.data.materials.new(name)
            mat.use_nodes = True
            nt = mat.node_tree; nt.nodes.clear()
            out = nt.nodes.new("ShaderNodeOutputMaterial"); out.location = (400,0)
            em  = nt.nodes.new("ShaderNodeEmission");      em.location  = (200,0)
            em.inputs["Color"].default_value    = (0.95, 0.95, 0.90, 1.0)
            em.inputs["Strength"].default_value = 0.5
            nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
            return mat

        mat_road    = _road_mat()
        mat_marking = _marking_mat()

        road_objs = [o for o in scene.objects
                     if o.type == "MESH" and o.get("osm_layer") == "roads"]

        roads_created   = 0
        markings_created = 0

        for src_obj in road_objs:
            hw_tag = str(src_obj.get("osm_highway", "")).lower()
            width  = WIDTHS.get(hw_tag, DEFAULT_WIDTH)
            hw     = hw_tag

            mesh = src_obj.data
            bme  = _bm.new()
            bme.from_mesh(mesh)
            bme.transform(src_obj.matrix_world)
            bme.edges.ensure_lookup_table()
            bme.verts.ensure_lookup_table()

            road_verts  = []
            road_faces  = []
            mark_verts  = []
            mark_faces  = []
            vi = 0

            for edge in bme.edges:
                v0 = edge.verts[0].co.copy()
                v1 = edge.verts[1].co.copy()
                seg = v1 - v0
                seg_len = seg.length
                if seg_len < 0.1:
                    continue
                seg_dir = seg.normalized()
                perp    = mathutils.Vector((-seg_dir.y, seg_dir.x, 0.0))

                half_w = width / 2.0
                # Road surface with camber: centre higher than edges
                # Left edge: p0 - perp*half_w, z -= camber*half_w
                # Right edge: p0 + perp*half_w, z -= camber*half_w
                def _pt(base, side, z_off):
                    return mathutils.Vector((
                        base.x + perp.x * side,
                        base.y + perp.y * side,
                        max(base.z + z_off, 0.0),
                    ))

                # 5-vert cross-section: left edge, left shoulder, centre, right shoulder, right edge
                sections = [
                    (_pt(v0, -half_w,       -CAMBER * half_w),
                     _pt(v0,  0.0,           0.0),
                     _pt(v0,  half_w,        -CAMBER * half_w)),
                    (_pt(v1, -half_w,       -CAMBER * half_w),
                     _pt(v1,  0.0,           0.0),
                     _pt(v1,  half_w,        -CAMBER * half_w)),
                ]
                # Left half quad
                road_verts.extend([sections[0][0], sections[0][1],
                                   sections[1][1], sections[1][0]])
                road_faces.append([vi, vi+1, vi+2, vi+3]); vi += 4
                # Right half quad
                road_verts.extend([sections[0][1], sections[0][2],
                                   sections[1][2], sections[1][1]])
                road_faces.append([vi, vi+1, vi+2, vi+3]); vi += 4

                # Lane markings: dashed centreline, 0.15 m wide, every 3 m
                if hw not in ("footway", "path", "steps"):
                    t = 0.0
                    dash = True  # alternate dash / gap
                    while t < seg_len:
                        next_t = min(t + 1.5, seg_len)
                        if dash:
                            frac0 = t      / seg_len
                            frac1 = next_t / seg_len
                            c0 = v0.lerp(v1, frac0)
                            c1 = v0.lerp(v1, frac1)
                            p0 = c0 + perp * (-0.075) + mathutils.Vector((0,0,0.01))
                            p1 = c1 + perp * (-0.075) + mathutils.Vector((0,0,0.01))
                            p2 = c1 + perp * ( 0.075) + mathutils.Vector((0,0,0.01))
                            p3 = c0 + perp * ( 0.075) + mathutils.Vector((0,0,0.01))
                            mark_verts.extend([p0,p1,p2,p3])
                            mvi = len(mark_verts) - 4
                            mark_faces.append([mvi, mvi+1, mvi+2, mvi+3])
                        t    += 1.5
                        dash  = not dash

            bme.free()

            if not road_verts:
                continue

            # Build road mesh
            rm = bpy.data.meshes.new(f"RoadMesh_{src_obj.name}")
            rm.from_pydata(
                [v.to_tuple() for v in road_verts],
                [],
                road_faces,
            )
            rm.update()
            rm.materials.append(mat_road)
            ro = bpy.data.objects.new(f"RoadMesh_{src_obj.name}", rm)
            ro["osm_layer"]   = "roads"
            ro["osm_highway"] = hw_tag
            scene.collection.objects.link(ro)
            roads_created += 1

            if mark_verts:
                mm = bpy.data.meshes.new(f"LaneMarkings_{src_obj.name}")
                mm.from_pydata(
                    [v.to_tuple() for v in mark_verts],
                    [],
                    mark_faces,
                )
                mm.update()
                mm.materials.append(mat_marking)
                mo = bpy.data.objects.new(f"LaneMarkings_{src_obj.name}", mm)
                scene.collection.objects.link(mo)
                markings_created += 1

        return {
            "road_meshes_created": roads_created,
            "marking_meshes_created": markings_created,
            "roads_processed": len(road_objs),
        }

    # ── add_lighting_setup ────────────────────────────────────────────────────

    def add_lighting_setup(self, time_of_day="golden_hour"):
        """Configure scene lighting for the requested time of day."""
        import math
        import random

        scene = bpy.context.scene

        # ── Remove previous city lighting objects ─────────────────────────────
        for obj in list(scene.objects):
            if obj.get("city_light"):
                bpy.data.objects.remove(obj, do_unlink=True)

        # ── World node tree ───────────────────────────────────────────────────
        world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
        scene.world = world
        world.use_nodes = True
        nt = world.node_tree
        nt.nodes.clear()

        out = nt.nodes.new("ShaderNodeOutputWorld"); out.location = (600,0)

        # Hemisphere fill light (always present, blue sky tone)
        bg_sky = nt.nodes.new("ShaderNodeBackground"); bg_sky.location = (400,100)
        bg_sky.inputs["Color"].default_value    = (0.35, 0.50, 0.80, 1.0)
        bg_sky.inputs["Strength"].default_value = 0.5

        mix_world = nt.nodes.new("ShaderNodeMixShader"); mix_world.location = (500, 0)
        mix_world.inputs["Fac"].default_value = 0.8

        # Sun / main light
        bg_sun = nt.nodes.new("ShaderNodeBackground"); bg_sun.location = (300, -100)

        nt.links.new(bg_sky.outputs["Background"], mix_world.inputs[1])
        nt.links.new(bg_sun.outputs["Background"], mix_world.inputs[2])
        nt.links.new(mix_world.outputs["Shader"],  out.inputs["Surface"])

        lights_added = 0

        tod = time_of_day.lower()

        if tod == "noon":
            elevation_deg = 70.0
            sun_color     = (1.00, 1.00, 0.98, 1.0)
            sun_strength  = 5.0
            bg_sky.inputs["Strength"].default_value = 0.4
        elif tod == "morning":
            elevation_deg = 20.0
            sun_color     = (0.85, 0.92, 1.00, 1.0)
            sun_strength  = 4.0
            bg_sky.inputs["Color"].default_value    = (0.40, 0.55, 0.80, 1.0)
            bg_sky.inputs["Strength"].default_value = 0.35
        elif tod == "night":
            elevation_deg = -10.0  # sun below horizon = no