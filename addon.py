# Code created by Siddharth Ahuja: www.github.com/ahujasid © 2025

import re
import bpy
import mathutils
import json
import threading
import socket
import time
import requests
import tempfile
import traceback
import os
import shutil
import zipfile
from bpy.props import IntProperty, BoolProperty
import io
from datetime import datetime
import hashlib, hmac, base64
import os.path as osp
from contextlib import redirect_stdout, suppress

bl_info = {
    "name": "Blender MCP",
    "author": "BlenderMCP",
    "version": (1, 2),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > BlenderMCP",
    "description": "Connect Blender to Claude via MCP",
    "category": "Interface",
}

RODIN_FREE_TRIAL_KEY = "k9TcfFoEhNd9cCPP2guHAHHHkctZHIRhZDywZ1euGUXwihbYLpOjQhofby80NJez"

# Add User-Agent as required by Poly Haven API
REQ_HEADERS = requests.utils.default_headers()
REQ_HEADERS.update({"User-Agent": "blender-mcp"})

class BlenderMCPServer:
    def __init__(self, host='localhost', port=9876):
        self.host = host
        self.port = port
        self.running = False
        self.socket = None
        self.server_thread = None

    def start(self):
        if self.running:
            print("Server is already running")
            return

        self.running = True

        try:
            # Create socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind((self.host, self.port))
            self.socket.listen(1)

            # Start server thread
            self.server_thread = threading.Thread(target=self._server_loop)
            self.server_thread.daemon = True
            self.server_thread.start()

            print(f"BlenderMCP server started on {self.host}:{self.port}")
        except Exception as e:
            print(f"Failed to start server: {str(e)}")
            self.stop()

    def stop(self):
        self.running = False

        # Close socket
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None

        # Wait for thread to finish
        if self.server_thread:
            try:
                if self.server_thread.is_alive():
                    self.server_thread.join(timeout=1.0)
            except:
                pass
            self.server_thread = None

        print("BlenderMCP server stopped")

    def _server_loop(self):
        """Main server loop in a separate thread"""
        print("Server thread started")
        self.socket.settimeout(1.0)  # Timeout to allow for stopping

        while self.running:
            try:
                # Accept new connection
                try:
                    client, address = self.socket.accept()
                    print(f"Connected to client: {address}")

                    # Handle client in a separate thread
                    client_thread = threading.Thread(
                        target=self._handle_client,
                        args=(client,)
                    )
                    client_thread.daemon = True
                    client_thread.start()
                except socket.timeout:
                    # Just check running condition
                    continue
                except Exception as e:
                    print(f"Error accepting connection: {str(e)}")
                    time.sleep(0.5)
            except Exception as e:
                print(f"Error in server loop: {str(e)}")
                if not self.running:
                    break
                time.sleep(0.5)

        print("Server thread stopped")

    def _handle_client(self, client):
        """Handle connected client"""
        print("Client handler started")
        client.settimeout(None)  # No timeout
        buffer = b''

        try:
            while self.running:
                # Receive data
                try:
                    data = client.recv(8192)
                    if not data:
                        print("Client disconnected")
                        break

                    buffer += data
                    try:
                        # Try to parse command
                        command = json.loads(buffer.decode('utf-8'))
                        buffer = b''

                        # Execute command in Blender's main thread
                        def execute_wrapper():
                            try:
                                response = self.execute_command(command)
                                response_json = json.dumps(response)
                                try:
                                    client.sendall(response_json.encode('utf-8'))
                                except:
                                    print("Failed to send response - client disconnected")
                            except Exception as e:
                                print(f"Error executing command: {str(e)}")
                                traceback.print_exc()
                                try:
                                    error_response = {
                                        "status": "error",
                                        "message": str(e)
                                    }
                                    client.sendall(json.dumps(error_response).encode('utf-8'))
                                except:
                                    pass
                            return None

                        # Schedule execution in main thread
                        bpy.app.timers.register(execute_wrapper, first_interval=0.0)
                    except json.JSONDecodeError:
                        # Incomplete data, wait for more
                        pass
                except Exception as e:
                    print(f"Error receiving data: {str(e)}")
                    break
        except Exception as e:
            print(f"Error in client handler: {str(e)}")
        finally:
            try:
                client.close()
            except:
                pass
            print("Client handler stopped")

    def execute_command(self, command):
        """Execute a command in the main Blender thread"""
        try:
            return self._execute_command_internal(command)

        except Exception as e:
            print(f"Error executing command: {str(e)}")
            traceback.print_exc()
            return {"status": "error", "message": str(e)}

    def _execute_command_internal(self, command):
        """Internal command execution with proper context"""
        cmd_type = command.get("type")
        params = command.get("params", {})

        # Add a handler for checking PolyHaven status
        if cmd_type == "get_polyhaven_status":
            return {"status": "success", "result": self.get_polyhaven_status()}

        # Base handlers that are always available
        handlers = {
            "get_scene_info": self.get_scene_info,
            "get_object_info": self.get_object_info,
            "get_viewport_screenshot": self.get_viewport_screenshot,
            "execute_code": self.execute_code,
            "get_telemetry_consent": self.get_telemetry_consent,
            "get_polyhaven_status": self.get_polyhaven_status,
            "get_hyper3d_status": self.get_hyper3d_status,
            "get_sketchfab_status": self.get_sketchfab_status,
            "get_hunyuan3d_status": self.get_hunyuan3d_status,
        }

        # Add Polyhaven handlers only if enabled
        if bpy.context.scene.blendermcp_use_polyhaven:
            polyhaven_handlers = {
                "get_polyhaven_categories": self.get_polyhaven_categories,
                "search_polyhaven_assets": self.search_polyhaven_assets,
                "download_polyhaven_asset": self.download_polyhaven_asset,
                "set_texture": self.set_texture,
            }
            handlers.update(polyhaven_handlers)

        # Add Hyper3d handlers only if enabled
        if bpy.context.scene.blendermcp_use_hyper3d:
            polyhaven_handlers = {
                "create_rodin_job": self.create_rodin_job,
                "poll_rodin_job_status": self.poll_rodin_job_status,
                "import_generated_asset": self.import_generated_asset,
            }
            handlers.update(polyhaven_handlers)

        # Add Sketchfab handlers only if enabled
        if bpy.context.scene.blendermcp_use_sketchfab:
            sketchfab_handlers = {
                "search_sketchfab_models": self.search_sketchfab_models,
                "get_sketchfab_model_preview": self.get_sketchfab_model_preview,
                "download_sketchfab_model": self.download_sketchfab_model,
            }
            handlers.update(sketchfab_handlers)
        
        # Add Hunyuan3d handlers only if enabled
        if bpy.context.scene.blendermcp_use_hunyuan3d:
            hunyuan_handlers = {
                "create_hunyuan_job": self.create_hunyuan_job,
                "poll_hunyuan_job_status": self.poll_hunyuan_job_status,
                "import_generated_asset_hunyuan": self.import_generated_asset_hunyuan
            }
            handlers.update(hunyuan_handlers)

        # City tools — always available
        city_handler_names = [
            "get_scene_graph", "validate_geometry", "take_snapshot",
            "get_scene_diff", "export_usd_tile", "import_osm_tile",
            "set_geo_origin", "import_pointcloud",
            "apply_procedural_materials",
            "add_street_detail", "add_vegetation", "add_ground_detail",
            "add_facade_textures", "add_ambient_occlusion",
            "add_road_geometry", "add_lighting_setup",
            "generate_facade_geometry",
            "generate_building_detail", "set_render_settings", "render_viewport",
        ]
        city_handlers = {
            name: getattr(self, name)
            for name in city_handler_names
            if hasattr(self, name)
        }
        handlers.update(city_handlers)

        handler = handlers.get(cmd_type)
        if handler:
            try:
                print(f"Executing handler for {cmd_type}")
                result = handler(**params)
                print(f"Handler execution complete")
                return {"status": "success", "result": result}
            except Exception as e:
                print(f"Error in handler: {str(e)}")
                traceback.print_exc()
                return {"status": "error", "message": str(e)}
        else:
            return {"status": "error", "message": f"Unknown command type: {cmd_type}"}



    def get_scene_info(self):
        """Get information about the current Blender scene"""
        try:
            print("Getting scene info...")
            # Simplify the scene info to reduce data size
            scene_info = {
                "name": bpy.context.scene.name,
                "object_count": len(bpy.context.scene.objects),
                "objects": [],
                "materials_count": len(bpy.data.materials),
            }

            # Collect minimal object information (limit to first 10 objects)
            for i, obj in enumerate(bpy.context.scene.objects):
                if i >= 10:  # Reduced from 20 to 10
                    break

                obj_info = {
                    "name": obj.name,
                    "type": obj.type,
                    # Only include basic location data
                    "location": [round(float(obj.location.x), 2),
                                round(float(obj.location.y), 2),
                                round(float(obj.location.z), 2)],
                }
                scene_info["objects"].append(obj_info)

            print(f"Scene info collected: {len(scene_info['objects'])} objects")
            return scene_info
        except Exception as e:
            print(f"Error in get_scene_info: {str(e)}")
            traceback.print_exc()
            return {"error": str(e)}

    @staticmethod
    def _get_aabb(obj):
        """ Returns the world-space axis-aligned bounding box (AABB) of an object. """
        if obj.type != 'MESH':
            raise TypeError("Object must be a mesh")

        # Get the bounding box corners in local space
        local_bbox_corners = [mathutils.Vector(corner) for corner in obj.bound_box]

        # Convert to world coordinates
        world_bbox_corners = [obj.matrix_world @ corner for corner in local_bbox_corners]

        # Compute axis-aligned min/max coordinates
        min_corner = mathutils.Vector(map(min, zip(*world_bbox_corners)))
        max_corner = mathutils.Vector(map(max, zip(*world_bbox_corners)))

        return [
            [*min_corner], [*max_corner]
        ]



    def get_object_info(self, name):
        """Get detailed information about a specific object"""
        obj = bpy.data.objects.get(name)
        if not obj:
            raise ValueError(f"Object not found: {name}")

        # Basic object info
        obj_info = {
            "name": obj.name,
            "type": obj.type,
            "location": [obj.location.x, obj.location.y, obj.location.z],
            "rotation": [obj.rotation_euler.x, obj.rotation_euler.y, obj.rotation_euler.z],
            "scale": [obj.scale.x, obj.scale.y, obj.scale.z],
            "visible": obj.visible_get(),
            "materials": [],
        }

        if obj.type == "MESH":
            bounding_box = self._get_aabb(obj)
            obj_info["world_bounding_box"] = bounding_box

        # Add material slots
        for slot in obj.material_slots:
            if slot.material:
                obj_info["materials"].append(slot.material.name)

        # Add mesh data if applicable
        if obj.type == 'MESH' and obj.data:
            mesh = obj.data
            obj_info["mesh"] = {
                "vertices": len(mesh.vertices),
                "edges": len(mesh.edges),
                "polygons": len(mesh.polygons),
            }

        return obj_info

    def get_viewport_screenshot(self, max_size=800, filepath=None, format="png"):
        """
        Capture a screenshot of the current 3D viewport and save it to the specified path.

        Parameters:
        - max_size: Maximum size in pixels for the largest dimension of the image
        - filepath: Path where to save the screenshot file
        - format: Image format (png, jpg, etc.)

        Returns success/error status
        """
        try:
            if not filepath:
                return {"error": "No filepath provided"}

            # Find the active 3D viewport
            area = None
            for a in bpy.context.screen.areas:
                if a.type == 'VIEW_3D':
                    area = a
                    break

            if not area:
                return {"error": "No 3D viewport found"}

            # Take screenshot with proper context override
            with bpy.context.temp_override(area=area):
                bpy.ops.screen.screenshot_area(filepath=filepath)

            # Load and resize if needed
            img = bpy.data.images.load(filepath)
            width, height = img.size

            if max(width, height) > max_size:
                scale = max_size / max(width, height)
                new_width = int(width * scale)
                new_height = int(height * scale)
                img.scale(new_width, new_height)

                # Set format and save
                img.file_format = format.upper()
                img.save()
                width, height = new_width, new_height

            # Cleanup Blender image data
            bpy.data.images.remove(img)

            return {
                "success": True,
                "width": width,
                "height": height,
                "filepath": filepath
            }

        except Exception as e:
            return {"error": str(e)}

    def execute_code(self, code):
        """Execute arbitrary Blender Python code"""
        # This is powerful but potentially dangerous - use with caution
        try:
            # Create a local namespace for execution
            namespace = {"bpy": bpy}

            # Capture stdout during execution, and return it as result
            capture_buffer = io.StringIO()
            with redirect_stdout(capture_buffer):
                exec(code, namespace)

            captured_output = capture_buffer.getvalue()
            return {"executed": True, "result": captured_output}
        except Exception as e:
            raise Exception(f"Code execution error: {str(e)}")



    def get_polyhaven_categories(self, asset_type):
        """Get categories for a specific asset type from Polyhaven"""
        try:
            if asset_type not in ["hdris", "textures", "models", "all"]:
                return {"error": f"Invalid asset type: {asset_type}. Must be one of: hdris, textures, models, all"}

            response = requests.get(f"https://api.polyhaven.com/categories/{asset_type}", headers=REQ_HEADERS)
            if response.status_code == 200:
                return {"categories": response.json()}
            else:
                return {"error": f"API request failed with status code {response.status_code}"}
        except Exception as e:
            return {"error": str(e)}

    def search_polyhaven_assets(self, asset_type=None, categories=None):
        """Search for assets from Polyhaven with optional filtering"""
        try:
            url = "https://api.polyhaven.com/assets"
            params = {}

            if asset_type and asset_type != "all":
                if asset_type not in ["hdris", "textures", "models"]:
                    return {"error": f"Invalid asset type: {asset_type}. Must be one of: hdris, textures, models, all"}
                params["type"] = asset_type

            if categories:
                params["categories"] = categories

            response = requests.get(url, params=params, headers=REQ_HEADERS)
            if response.status_code == 200:
                # Limit the response size to avoid overwhelming Blender
                assets = response.json()
                # Return only the first 20 assets to keep response size manageable
                limited_assets = {}
                for i, (key, value) in enumerate(assets.items()):
                    if i >= 20:  # Limit to 20 assets
                        break
                    limited_assets[key] = value

                return {"assets": limited_assets, "total_count": len(assets), "returned_count": len(limited_assets)}
            else:
                return {"error": f"API request failed with status code {response.status_code}"}
        except Exception as e:
            return {"error": str(e)}

    def download_polyhaven_asset(self, asset_id, asset_type, resolution="1k", file_format=None):
        try:
            # First get the files information
            files_response = requests.get(f"https://api.polyhaven.com/files/{asset_id}", headers=REQ_HEADERS)
            if files_response.status_code != 200:
                return {"error": f"Failed to get asset files: {files_response.status_code}"}

            files_data = files_response.json()

            # Handle different asset types
            if asset_type == "hdris":
                # For HDRIs, download the .hdr or .exr file
                if not file_format:
                    file_format = "hdr"  # Default format for HDRIs

                if "hdri" in files_data and resolution in files_data["hdri"] and file_format in files_data["hdri"][resolution]:
                    file_info = files_data["hdri"][resolution][file_format]
                    file_url = file_info["url"]

                    # For HDRIs, we need to save to a temporary file first
                    # since Blender can't properly load HDR data directly from memory
                    with tempfile.NamedTemporaryFile(suffix=f".{file_format}", delete=False) as tmp_file:
                        # Download the file
                        response = requests.get(file_url, headers=REQ_HEADERS)
                        if response.status_code != 200:
                            return {"error": f"Failed to download HDRI: {response.status_code}"}

                        tmp_file.write(response.content)
                        tmp_path = tmp_file.name

                    try:
                        # Create a new world if none exists
                        if not bpy.data.worlds:
                            bpy.data.worlds.new("World")

                        world = bpy.data.worlds[0]
                        world.use_nodes = True
                        node_tree = world.node_tree

                        # Clear existing nodes
                        for node in node_tree.nodes:
                            node_tree.nodes.remove(node)

                        # Create nodes
                        tex_coord = node_tree.nodes.new(type='ShaderNodeTexCoord')
                        tex_coord.location = (-800, 0)

                        mapping = node_tree.nodes.new(type='ShaderNodeMapping')
                        mapping.location = (-600, 0)

                        # Load the image from the temporary file
                        env_tex = node_tree.nodes.new(type='ShaderNodeTexEnvironment')
                        env_tex.location = (-400, 0)
                        env_tex.image = bpy.data.images.load(tmp_path)

                        # Use a color space that exists in all Blender versions
                        if file_format.lower() == 'exr':
                            # Try to use Linear color space for EXR files
                            try:
                                env_tex.image.colorspace_settings.name = 'Linear'
                            except:
                                # Fallback to Non-Color if Linear isn't available
                                env_tex.image.colorspace_settings.name = 'Non-Color'
                        else:  # hdr
                            # For HDR files, try these options in order
                            for color_space in ['Linear', 'Linear Rec.709', 'Non-Color']:
                                try:
                                    env_tex.image.colorspace_settings.name = color_space
                                    break  # Stop if we successfully set a color space
                                except:
                                    continue

                        background = node_tree.nodes.new(type='ShaderNodeBackground')
                        background.location = (-200, 0)

                        output = node_tree.nodes.new(type='ShaderNodeOutputWorld')
                        output.location = (0, 0)

                        # Connect nodes
                        node_tree.links.new(tex_coord.outputs['Generated'], mapping.inputs['Vector'])
                        node_tree.links.new(mapping.outputs['Vector'], env_tex.inputs['Vector'])
                        node_tree.links.new(env_tex.outputs['Color'], background.inputs['Color'])
                        node_tree.links.new(background.outputs['Background'], output.inputs['Surface'])

                        # Set as active world
                        bpy.context.scene.world = world

                        # Clean up temporary file
                        try:
                            tempfile._cleanup()  # This will clean up all temporary files
                        except:
                            pass

                        return {
                            "success": True,
                            "message": f"HDRI {asset_id} imported successfully",
                            "image_name": env_tex.image.name
                        }
                    except Exception as e:
                        return {"error": f"Failed to set up HDRI in Blender: {str(e)}"}
                else:
                    return {"error": f"Requested resolution or format not available for this HDRI"}

            elif asset_type == "textures":
                if not file_format:
                    file_format = "jpg"  # Default format for textures

                downloaded_maps = {}

                try:
                    for map_type in files_data:
                        if map_type not in ["blend", "gltf"]:  # Skip non-texture files
                            if resolution in files_data[map_type] and file_format in files_data[map_type][resolution]:
                                file_info = files_data[map_type][resolution][file_format]
                                file_url = file_info["url"]

                                # Use NamedTemporaryFile like we do for HDRIs
                                with tempfile.NamedTemporaryFile(suffix=f".{file_format}", delete=False) as tmp_file:
                                    # Download the file
                                    response = requests.get(file_url, headers=REQ_HEADERS)
                                    if response.status_code == 200:
                                        tmp_file.write(response.content)
                                        tmp_path = tmp_file.name

                                        # Load image from temporary file
                                        image = bpy.data.images.load(tmp_path)
                                        image.name = f"{asset_id}_{map_type}.{file_format}"

                                        # Pack the image into .blend file
                                        image.pack()

                                        # Set color space based on map type
                                        if map_type in ['color', 'diffuse', 'albedo']:
                                            try:
                                                image.colorspace_settings.name = 'sRGB'
                                            except:
                                                pass
                                        else:
                                            try:
                                                image.colorspace_settings.name = 'Non-Color'
                                            except:
                                                pass

                                        downloaded_maps[map_type] = image

                                        # Clean up temporary file
                                        try:
                                            os.unlink(tmp_path)
                                        except:
                                            pass

                    if not downloaded_maps:
                        return {"error": f"No texture maps found for the requested resolution and format"}

                    # Create a new material with the downloaded textures
                    mat = bpy.data.materials.new(name=asset_id)
                    mat.use_nodes = True
                    nodes = mat.node_tree.nodes
                    links = mat.node_tree.links

                    # Clear default nodes
                    for node in nodes:
                        nodes.remove(node)

                    # Create output node
                    output = nodes.new(type='ShaderNodeOutputMaterial')
                    output.location = (300, 0)

                    # Create principled BSDF node
                    principled = nodes.new(type='ShaderNodeBsdfPrincipled')
                    principled.location = (0, 0)
                    links.new(principled.outputs[0], output.inputs[0])

                    # Add texture nodes based on available maps
                    tex_coord = nodes.new(type='ShaderNodeTexCoord')
                    tex_coord.location = (-800, 0)

                    mapping = nodes.new(type='ShaderNodeMapping')
                    mapping.location = (-600, 0)
                    mapping.vector_type = 'TEXTURE'  # Changed from default 'POINT' to 'TEXTURE'
                    links.new(tex_coord.outputs['UV'], mapping.inputs['Vector'])

                    # Position offset for texture nodes
                    x_pos = -400
                    y_pos = 300

                    # Connect different texture maps
                    for map_type, image in downloaded_maps.items():
                        tex_node = nodes.new(type='ShaderNodeTexImage')
                        tex_node.location = (x_pos, y_pos)
                        tex_node.image = image

                        # Set color space based on map type
                        if map_type.lower() in ['color', 'diffuse', 'albedo']:
                            try:
                                tex_node.image.colorspace_settings.name = 'sRGB'
                            except:
                                pass  # Use default if sRGB not available
                        else:
                            try:
                                tex_node.image.colorspace_settings.name = 'Non-Color'
                            except:
                                pass  # Use default if Non-Color not available

                        links.new(mapping.outputs['Vector'], tex_node.inputs['Vector'])

                        # Connect to appropriate input on Principled BSDF
                        if map_type.lower() in ['color', 'diffuse', 'albedo']:
                            links.new(tex_node.outputs['Color'], principled.inputs['Base Color'])
                        elif map_type.lower() in ['roughness', 'rough']:
                            links.new(tex_node.outputs['Color'], principled.inputs['Roughness'])
                        elif map_type.lower() in ['metallic', 'metalness', 'metal']:
                            links.new(tex_node.outputs['Color'], principled.inputs['Metallic'])
                        elif map_type.lower() in ['normal', 'nor']:
                            # Add normal map node
                            normal_map = nodes.new(type='ShaderNodeNormalMap')
                            normal_map.location = (x_pos + 200, y_pos)
                            links.new(tex_node.outputs['Color'], normal_map.inputs['Color'])
                            links.new(normal_map.outputs['Normal'], principled.inputs['Normal'])
                        elif map_type in ['displacement', 'disp', 'height']:
                            # Add displacement node
                            disp_node = nodes.new(type='ShaderNodeDisplacement')
                            disp_node.location = (x_pos + 200, y_pos - 200)
                            links.new(tex_node.outputs['Color'], disp_node.inputs['Height'])
                            links.new(disp_node.outputs['Displacement'], output.inputs['Displacement'])

                        y_pos -= 250

                    return {
                        "success": True,
                        "message": f"Texture {asset_id} imported as material",
                        "material": mat.name,
                        "maps": list(downloaded_maps.keys())
                    }

                except Exception as e:
                    return {"error": f"Failed to process textures: {str(e)}"}

            elif asset_type == "models":
                # For models, prefer glTF format if available
                if not file_format:
                    file_format = "gltf"  # Default format for models

                if file_format in files_data and resolution in files_data[file_format]:
                    file_info = files_data[file_format][resolution][file_format]
                    file_url = file_info["url"]

                    # Create a temporary directory to store the model and its dependencies
                    temp_dir = tempfile.mkdtemp()
                    main_file_path = ""

                    try:
                        # Download the main model file
                        main_file_name = file_url.split("/")[-1]
                        main_file_path = os.path.join(temp_dir, main_file_name)

                        response = requests.get(file_url, headers=REQ_HEADERS)
                        if response.status_code != 200:
                            return {"error": f"Failed to download model: {response.status_code}"}

                        with open(main_file_path, "wb") as f:
                            f.write(response.content)

                        # Check for included files and download them
                        if "include" in file_info and file_info["include"]:
                            for include_path, include_info in file_info["include"].items():
                                # Get the URL for the included file - this is the fix
                                include_url = include_info["url"]

                                # Create the directory structure for the included file
                                include_file_path = os.path.join(temp_dir, include_path)
                                os.makedirs(os.path.dirname(include_file_path), exist_ok=True)

                                # Download the included file
                                include_response = requests.get(include_url, headers=REQ_HEADERS)
                                if include_response.status_code == 200:
                                    with open(include_file_path, "wb") as f:
                                        f.write(include_response.content)
                                else:
                                    print(f"Failed to download included file: {include_path}")

                        # Import the model into Blender
                        if file_format == "gltf" or file_format == "glb":
                            bpy.ops.import_scene.gltf(filepath=main_file_path)
                        elif file_format == "fbx":
                            bpy.ops.import_scene.fbx(filepath=main_file_path)
                        elif file_format == "obj":
                            bpy.ops.import_scene.obj(filepath=main_file_path)
                        elif file_format == "blend":
                            # For blend files, we need to append or link
                            with bpy.data.libraries.load(main_file_path, link=False) as (data_from, data_to):
                                data_to.objects = data_from.objects

                            # Link the objects to the scene
                            for obj in data_to.objects:
                                if obj is not None:
                                    bpy.context.collection.objects.link(obj)
                        else:
                            return {"error": f"Unsupported model format: {file_format}"}

                        # Get the names of imported objects
                        imported_objects = [obj.name for obj in bpy.context.selected_objects]

                        return {
                            "success": True,
                            "message": f"Model {asset_id} imported successfully",
                            "imported_objects": imported_objects
                        }
                    except Exception as e:
                        return {"error": f"Failed to import model: {str(e)}"}
                    finally:
                        # Clean up temporary directory
                        with suppress(Exception):
                            shutil.rmtree(temp_dir)
                else:
                    return {"error": f"Requested format or resolution not available for this model"}

            else:
                return {"error": f"Unsupported asset type: {asset_type}"}

        except Exception as e:
            return {"error": f"Failed to download asset: {str(e)}"}

    def set_texture(self, object_name, texture_id):
        """Apply a previously downloaded Polyhaven texture to an object by creating a new material"""
        try:
            # Get the object
            obj = bpy.data.objects.get(object_name)
            if not obj:
                return {"error": f"Object not found: {object_name}"}

            # Make sure object can accept materials
            if not hasattr(obj, 'data') or not hasattr(obj.data, 'materials'):
                return {"error": f"Object {object_name} cannot accept materials"}

            # Find all images related to this texture and ensure they're properly loaded
            texture_images = {}
            for img in bpy.data.images:
                if img.name.startswith(texture_id + "_"):
                    # Extract the map type from the image name
                    map_type = img.name.split('_')[-1].split('.')[0]

                    # Force a reload of the image
                    img.reload()

                    # Ensure proper color space
                    if map_type.lower() in ['color', 'diffuse', 'albedo']:
                        try:
                            img.colorspace_settings.name = 'sRGB'
                        except:
                            pass
                    else:
                        try:
                            img.colorspace_settings.name = 'Non-Color'
                        except:
                            pass

                    # Ensure the image is packed
                    if not img.packed_file:
                        img.pack()

                    texture_images[map_type] = img
                    print(f"Loaded texture map: {map_type} - {img.name}")

                    # Debug info
                    print(f"Image size: {img.size[0]}x{img.size[1]}")
                    print(f"Color space: {img.colorspace_settings.name}")
                    print(f"File format: {img.file_format}")
                    print(f"Is packed: {bool(img.packed_file)}")

            if not texture_images:
                return {"error": f"No texture images found for: {texture_id}. Please download the texture first."}

            # Create a new material
            new_mat_name = f"{texture_id}_material_{object_name}"

            # Remove any existing material with this name to avoid conflicts
            existing_mat = bpy.data.materials.get(new_mat_name)
            if existing_mat:
                bpy.data.materials.remove(existing_mat)

            new_mat = bpy.data.materials.new(name=new_mat_name)
            new_mat.use_nodes = True

            # Set up the material nodes
            nodes = new_mat.node_tree.nodes
            links = new_mat.node_tree.links

            # Clear default nodes
            nodes.clear()

            # Create output node
            output = nodes.new(type='ShaderNodeOutputMaterial')
            output.location = (600, 0)

            # Create principled BSDF node
            principled = nodes.new(type='ShaderNodeBsdfPrincipled')
            principled.location = (300, 0)
            links.new(principled.outputs[0], output.inputs[0])

            # Add texture nodes based on available maps
            tex_coord = nodes.new(type='ShaderNodeTexCoord')
            tex_coord.location = (-800, 0)

            mapping = nodes.new(type='ShaderNodeMapping')
            mapping.location = (-600, 0)
            mapping.vector_type = 'TEXTURE'  # Changed from default 'POINT' to 'TEXTURE'
            links.new(tex_coord.outputs['UV'], mapping.inputs['Vector'])

            # Position offset for texture nodes
            x_pos = -400
            y_pos = 300

            # Connect different texture maps
            for map_type, image in texture_images.items():
                tex_node = nodes.new(type='ShaderNodeTexImage')
                tex_node.location = (x_pos, y_pos)
                tex_node.image = image

                # Set color space based on map type
                if map_type.lower() in ['color', 'diffuse', 'albedo']:
                    try:
                        tex_node.image.colorspace_settings.name = 'sRGB'
                    except:
                        pass  # Use default if sRGB not available
                else:
                    try:
                        tex_node.image.colorspace_settings.name = 'Non-Color'
                    except:
                        pass  # Use default if Non-Color not available

                links.new(mapping.outputs['Vector'], tex_node.inputs['Vector'])

                # Connect to appropriate input on Principled BSDF
                if map_type.lower() in ['color', 'diffuse', 'albedo']:
                    links.new(tex_node.outputs['Color'], principled.inputs['Base Color'])
                elif map_type.lower() in ['roughness', 'rough']:
                    links.new(tex_node.outputs['Color'], principled.inputs['Roughness'])
                elif map_type.lower() in ['metallic', 'metalness', 'metal']:
                    links.new(tex_node.outputs['Color'], principled.inputs['Metallic'])
                elif map_type.lower() in ['normal', 'nor', 'dx', 'gl']:
                    # Add normal map node
                    normal_map = nodes.new(type='ShaderNodeNormalMap')
                    normal_map.location = (x_pos + 200, y_pos)
                    links.new(tex_node.outputs['Color'], normal_map.inputs['Color'])
                    links.new(normal_map.outputs['Normal'], principled.inputs['Normal'])
                elif map_type.lower() in ['displacement', 'disp', 'height']:
                    # Add displacement node
                    disp_node = nodes.new(type='ShaderNodeDisplacement')
                    disp_node.location = (x_pos + 200, y_pos - 200)
                    disp_node.inputs['Scale'].default_value = 0.1  # Reduce displacement strength
                    links.new(tex_node.outputs['Color'], disp_node.inputs['Height'])
                    links.new(disp_node.outputs['Displacement'], output.inputs['Displacement'])

                y_pos -= 250

            # Second pass: Connect nodes with proper handling for special cases
            texture_nodes = {}

            # First find all texture nodes and store them by map type
            for node in nodes:
                if node.type == 'TEX_IMAGE' and node.image:
                    for map_type, image in texture_images.items():
                        if node.image == image:
                            texture_nodes[map_type] = node
                            break

            # Now connect everything using the nodes instead of images
            # Handle base color (diffuse)
            for map_name in ['color', 'diffuse', 'albedo']:
                if map_name in texture_nodes:
                    links.new(texture_nodes[map_name].outputs['Color'], principled.inputs['Base Color'])
                    print(f"Connected {map_name} to Base Color")
                    break

            # Handle roughness
            for map_name in ['roughness', 'rough']:
                if map_name in texture_nodes:
                    links.new(texture_nodes[map_name].outputs['Color'], principled.inputs['Roughness'])
                    print(f"Connected {map_name} to Roughness")
                    break

            # Handle metallic
            for map_name in ['metallic', 'metalness', 'metal']:
                if map_name in texture_nodes:
                    links.new(texture_nodes[map_name].outputs['Color'], principled.inputs['Metallic'])
                    print(f"Connected {map_name} to Metallic")
                    break

            # Handle normal maps
            for map_name in ['gl', 'dx', 'nor']:
                if map_name in texture_nodes:
                    normal_map_node = nodes.new(type='ShaderNodeNormalMap')
                    normal_map_node.location = (100, 100)
                    links.new(texture_nodes[map_name].outputs['Color'], normal_map_node.inputs['Color'])
                    links.new(normal_map_node.outputs['Normal'], principled.inputs['Normal'])
                    print(f"Connected {map_name} to Normal")
                    break

            # Handle displacement
            for map_name in ['displacement', 'disp', 'height']:
                if map_name in texture_nodes:
                    disp_node = nodes.new(type='ShaderNodeDisplacement')
                    disp_node.location = (300, -200)
                    disp_node.inputs['Scale'].default_value = 0.1  # Reduce displacement strength
                    links.new(texture_nodes[map_name].outputs['Color'], disp_node.inputs['Height'])
                    links.new(disp_node.outputs['Displacement'], output.inputs['Displacement'])
                    print(f"Connected {map_name} to Displacement")
                    break

            # Handle ARM texture (Ambient Occlusion, Roughness, Metallic)
            if 'arm' in texture_nodes:
                separate_rgb = nodes.new(type='ShaderNodeSeparateRGB')
                separate_rgb.location = (-200, -100)
                links.new(texture_nodes['arm'].outputs['Color'], separate_rgb.inputs['Image'])

                # Connect Roughness (G) if no dedicated roughness map
                if not any(map_name in texture_nodes for map_name in ['roughness', 'rough']):
                    links.new(separate_rgb.outputs['G'], principled.inputs['Roughness'])
                    print("Connected ARM.G to Roughness")

                # Connect Metallic (B) if no dedicated metallic map
                if not any(map_name in texture_nodes for map_name in ['metallic', 'metalness', 'metal']):
                    links.new(separate_rgb.outputs['B'], principled.inputs['Metallic'])
                    print("Connected ARM.B to Metallic")

                # For AO (R channel), multiply with base color if we have one
                base_color_node = None
                for map_name in ['color', 'diffuse', 'albedo']:
                    if map_name in texture_nodes:
                        base_color_node = texture_nodes[map_name]
                        break

                if base_color_node:
                    mix_node = nodes.new(type='ShaderNodeMixRGB')
                    mix_node.location = (100, 200)
                    mix_node.blend_type = 'MULTIPLY'
                    mix_node.inputs['Fac'].default_value = 0.8  # 80% influence

                    # Disconnect direct connection to base color
                    for link in base_color_node.outputs['Color'].links:
                        if link.to_socket == principled.inputs['Base Color']:
                            links.remove(link)

                    # Connect through the mix node
                    links.new(base_color_node.outputs['Color'], mix_node.inputs[1])
                    links.new(separate_rgb.outputs['R'], mix_node.inputs[2])
                    links.new(mix_node.outputs['Color'], principled.inputs['Base Color'])
                    print("Connected ARM.R to AO mix with Base Color")

            # Handle AO (Ambient Occlusion) if separate
            if 'ao' in texture_nodes:
                base_color_node = None
                for map_name in ['color', 'diffuse', 'albedo']:
                    if map_name in texture_nodes:
                        base_color_node = texture_nodes[map_name]
                        break

                if base_color_node:
                    mix_node = nodes.new(type='ShaderNodeMixRGB')
                    mix_node.location = (100, 200)
                    mix_node.blend_type = 'MULTIPLY'
                    mix_node.inputs['Fac'].default_value = 0.8  # 80% influence

                    # Disconnect direct connection to base color
                    for link in base_color_node.outputs['Color'].links:
                        if link.to_socket == principled.inputs['Base Color']:
                            links.remove(link)

                    # Connect through the mix node
                    links.new(base_color_node.outputs['Color'], mix_node.inputs[1])
                    links.new(texture_nodes['ao'].outputs['Color'], mix_node.inputs[2])
                    links.new(mix_node.outputs['Color'], principled.inputs['Base Color'])
                    print("Connected AO to mix with Base Color")

            # CRITICAL: Make sure to clear all existing materials from the object
            while len(obj.data.materials) > 0:
                obj.data.materials.pop(index=0)

            # Assign the new material to the object
            obj.data.materials.append(new_mat)

            # CRITICAL: Make the object active and select it
            bpy.context.view_layer.objects.active = obj
            obj.select_set(True)

            # CRITICAL: Force Blender to update the material
            bpy.context.view_layer.update()

            # Get the list of texture maps
            texture_maps = list(texture_images.keys())

            # Get info about texture nodes for debugging
            material_info = {
                "name": new_mat.name,
                "has_nodes": new_mat.use_nodes,
                "node_count": len(new_mat.node_tree.nodes),
                "texture_nodes": []
            }

            for node in new_mat.node_tree.nodes:
                if node.type == 'TEX_IMAGE' and node.image:
                    connections = []
                    for output in node.outputs:
                        for link in output.links:
                            connections.append(f"{output.name} → {link.to_node.name}.{link.to_socket.name}")

                    material_info["texture_nodes"].append({
                        "name": node.name,
                        "image": node.image.name,
                        "colorspace": node.image.colorspace_settings.name,
                        "connections": connections
                    })

            return {
                "success": True,
                "message": f"Created new material and applied texture {texture_id} to {object_name}",
                "material": new_mat.name,
                "maps": texture_maps,
                "material_info": material_info
            }

        except Exception as e:
            print(f"Error in set_texture: {str(e)}")
            traceback.print_exc()
            return {"error": f"Failed to apply texture: {str(e)}"}

    def get_telemetry_consent(self):
        """Get the current telemetry consent status"""
        try:
            # Get addon preferences - use the module name
            addon_prefs = bpy.context.preferences.addons.get(__name__)
            if addon_prefs:
                consent = addon_prefs.preferences.telemetry_consent
            else:
                # Fallback to default if preferences not available
                consent = True
        except (AttributeError, KeyError):
            # Fallback to default if preferences not available
            consent = True
        return {"consent": consent}

    def get_polyhaven_status(self):
        """Get the current status of PolyHaven integration"""
        enabled = bpy.context.scene.blendermcp_use_polyhaven
        if enabled:
            return {"enabled": True, "message": "PolyHaven integration is enabled and ready to use."}
        else:
            return {
                "enabled": False,
                "message": """PolyHaven integration is currently disabled. To enable it:
                            1. In the 3D Viewport, find the BlenderMCP panel in the sidebar (press N if hidden)
                            2. Check the 'Use assets from Poly Haven' checkbox
                            3. Restart the connection to Claude"""
        }

    #region Hyper3D
    def get_hyper3d_status(self):
        """Get the current status of Hyper3D Rodin integration"""
        enabled = bpy.context.scene.blendermcp_use_hyper3d
        if enabled:
            if not bpy.context.scene.blendermcp_hyper3d_api_key:
                return {
                    "enabled": False,
                    "message": """Hyper3D Rodin integration is currently enabled, but API key is not given. To enable it:
                                1. In the 3D Viewport, find the BlenderMCP panel in the sidebar (press N if hidden)
                                2. Keep the 'Use Hyper3D Rodin 3D model generation' checkbox checked
                                3. Choose the right plaform and fill in the API Key
                                4. Restart the connection to Claude"""
                }
            mode = bpy.context.scene.blendermcp_hyper3d_mode
            message = f"Hyper3D Rodin integration is enabled and ready to use. Mode: {mode}. " + \
                f"Key type: {'private' if bpy.context.scene.blendermcp_hyper3d_api_key != RODIN_FREE_TRIAL_KEY else 'free_trial'}"
            return {
                "enabled": True,
                "message": message
            }
        else:
            return {
                "enabled": False,
                "message": """Hyper3D Rodin integration is currently disabled. To enable it:
                            1. In the 3D Viewport, find the BlenderMCP panel in the sidebar (press N if hidden)
                            2. Check the 'Use Hyper3D Rodin 3D model generation' checkbox
                            3. Restart the connection to Claude"""
            }

    def create_rodin_job(self, *args, **kwargs):
        match bpy.context.scene.blendermcp_hyper3d_mode:
            case "MAIN_SITE":
                return self.create_rodin_job_main_site(*args, **kwargs)
            case "FAL_AI":
                return self.create_rodin_job_fal_ai(*args, **kwargs)
            case _:
                return f"Error: Unknown Hyper3D Rodin mode!"

    def create_rodin_job_main_site(
            self,
            text_prompt: str=None,
            images: list[tuple[str, str]]=None,
            bbox_condition=None
        ):
        try:
            if images is None:
                images = []
            """Call Rodin API, get the job uuid and subscription key"""
            files = [
                *[("images", (f"{i:04d}{img_suffix}", img)) for i, (img_suffix, img) in enumerate(images)],
                ("tier", (None, "Sketch")),
                ("mesh_mode", (None, "Raw")),
            ]
            if text_prompt:
                files.append(("prompt", (None, text_prompt)))
            if bbox_condition:
                files.append(("bbox_condition", (None, json.dumps(bbox_condition))))
            response = requests.post(
                "https://hyperhuman.deemos.com/api/v2/rodin",
                headers={
                    "Authorization": f"Bearer {bpy.context.scene.blendermcp_hyper3d_api_key}",
                },
                files=files
            )
            data = response.json()
            return data
        except Exception as e:
            return {"error": str(e)}

    def create_rodin_job_fal_ai(
            self,
            text_prompt: str=None,
            images: list[tuple[str, str]]=None,
            bbox_condition=None
        ):
        try:
            req_data = {
                "tier": "Sketch",
            }
            if images:
                req_data["input_image_urls"] = images
            if text_prompt:
                req_data["prompt"] = text_prompt
            if bbox_condition:
                req_data["bbox_condition"] = bbox_condition
            response = requests.post(
                "https://queue.fal.run/fal-ai/hyper3d/rodin",
                headers={
                    "Authorization": f"Key {bpy.context.scene.blendermcp_hyper3d_api_key}",
                    "Content-Type": "application/json",
                },
                json=req_data
            )
            data = response.json()
            return data
        except Exception as e:
            return {"error": str(e)}

    def poll_rodin_job_status(self, *args, **kwargs):
        match bpy.context.scene.blendermcp_hyper3d_mode:
            case "MAIN_SITE":
                return self.poll_rodin_job_status_main_site(*args, **kwargs)
            case "FAL_AI":
                return self.poll_rodin_job_status_fal_ai(*args, **kwargs)
            case _:
                return f"Error: Unknown Hyper3D Rodin mode!"

    def poll_rodin_job_status_main_site(self, subscription_key: str):
        """Call the job status API to get the job status"""
        response = requests.post(
            "https://hyperhuman.deemos.com/api/v2/status",
            headers={
                "Authorization": f"Bearer {bpy.context.scene.blendermcp_hyper3d_api_key}",
            },
            json={
                "subscription_key": subscription_key,
            },
        )
        data = response.json()
        return {
            "status_list": [i["status"] for i in data["jobs"]]
        }

    def poll_rodin_job_status_fal_ai(self, request_id: str):
        """Call the job status API to get the job status"""
        response = requests.get(
            f"https://queue.fal.run/fal-ai/hyper3d/requests/{request_id}/status",
            headers={
                "Authorization": f"KEY {bpy.context.scene.blendermcp_hyper3d_api_key}",
            },
        )
        data = response.json()
        return data

    @staticmethod
    def _clean_imported_glb(filepath, mesh_name=None):
        # Get the set of existing objects before import
        existing_objects = set(bpy.data.objects)

        # Import the GLB file
        bpy.ops.import_scene.gltf(filepath=filepath)

        # Ensure the context is updated
        bpy.context.view_layer.update()

        # Get all imported objects
        imported_objects = list(set(bpy.data.objects) - existing_objects)
        # imported_objects = [obj for obj in bpy.context.view_layer.objects if obj.select_get()]

        if not imported_objects:
            print("Error: No objects were imported.")
            return

        # Identify the mesh object
        mesh_obj = None

        if len(imported_objects) == 1 and imported_objects[0].type == 'MESH':
            mesh_obj = imported_objects[0]
            print("Single mesh imported, no cleanup needed.")
        else:
            if len(imported_objects) == 2:
                empty_objs = [i for i in imported_objects if i.type == "EMPTY"]
                if len(empty_objs) != 1:
                    print("Error: Expected an empty node with one mesh child or a single mesh object.")
                    return
                parent_obj = empty_objs.pop()
                if len(parent_obj.children) == 1:
                    potential_mesh = parent_obj.children[0]
                    if potential_mesh.type == 'MESH':
                        print("GLB structure confirmed: Empty node with one mesh child.")

                        # Unparent the mesh from the empty node
                        potential_mesh.parent = None

                        # Remove the empty node
                        bpy.data.objects.remove(parent_obj)
                        print("Removed empty node, keeping only the mesh.")

                        mesh_obj = potential_mesh
                    else:
                        print("Error: Child is not a mesh object.")
                        return
                else:
                    print("Error: Expected an empty node with one mesh child or a single mesh object.")
                    return
            else:
                print("Error: Expected an empty node with one mesh child or a single mesh object.")
                return

        # Rename the mesh if needed
        try:
            if mesh_obj and mesh_obj.name is not None and mesh_name:
                mesh_obj.name = mesh_name
                if mesh_obj.data.name is not None:
                    mesh_obj.data.name = mesh_name
                print(f"Mesh renamed to: {mesh_name}")
        except Exception as e:
            print("Having issue with renaming, give up renaming.")

        return mesh_obj

    def import_generated_asset(self, *args, **kwargs):
        match bpy.context.scene.blendermcp_hyper3d_mode:
            case "MAIN_SITE":
                return self.import_generated_asset_main_site(*args, **kwargs)
            case "FAL_AI":
                return self.import_generated_asset_fal_ai(*args, **kwargs)
            case _:
                return f"Error: Unknown Hyper3D Rodin mode!"

    def import_generated_asset_main_site(self, task_uuid: str, name: str):
        """Fetch the generated asset, import into blender"""
        response = requests.post(
            "https://hyperhuman.deemos.com/api/v2/download",
            headers={
                "Authorization": f"Bearer {bpy.context.scene.blendermcp_hyper3d_api_key}",
            },
            json={
                'task_uuid': task_uuid
            }
        )
        data_ = response.json()
        temp_file = None
        for i in data_["list"]:
            if i["name"].endswith(".glb"):
                temp_file = tempfile.NamedTemporaryFile(
                    delete=False,
                    prefix=task_uuid,
                    suffix=".glb",
                )

                try:
                    # Download the content
                    response = requests.get(i["url"], stream=True)
                    response.raise_for_status()  # Raise an exception for HTTP errors

                    # Write the content to the temporary file
                    for chunk in response.iter_content(chunk_size=8192):
                        temp_file.write(chunk)

                    # Close the file
                    temp_file.close()

                except Exception as e:
                    # Clean up the file if there's an error
                    temp_file.close()
                    os.unlink(temp_file.name)
                    return {"succeed": False, "error": str(e)}

                break
        else:
            return {"succeed": False, "error": "Generation failed. Please first make sure that all jobs of the task are done and then try again later."}

        try:
            obj = self._clean_imported_glb(
                filepath=temp_file.name,
                mesh_name=name
            )
            result = {
                "name": obj.name,
                "type": obj.type,
                "location": [obj.location.x, obj.location.y, obj.location.z],
                "rotation": [obj.rotation_euler.x, obj.rotation_euler.y, obj.rotation_euler.z],
                "scale": [obj.scale.x, obj.scale.y, obj.scale.z],
            }

            if obj.type == "MESH":
                bounding_box = self._get_aabb(obj)
                result["world_bounding_box"] = bounding_box

            return {
                "succeed": True, **result
            }
        except Exception as e:
            return {"succeed": False, "error": str(e)}

    def import_generated_asset_fal_ai(self, request_id: str, name: str):
        """Fetch the generated asset, import into blender"""
        response = requests.get(
            f"https://queue.fal.run/fal-ai/hyper3d/requests/{request_id}",
            headers={
                "Authorization": f"Key {bpy.context.scene.blendermcp_hyper3d_api_key}",
            }
        )
        data_ = response.json()
        temp_file = None

        temp_file = tempfile.NamedTemporaryFile(
            delete=False,
            prefix=request_id,
            suffix=".glb",
        )

        try:
            # Download the content
            response = requests.get(data_["model_mesh"]["url"], stream=True)
            response.raise_for_status()  # Raise an exception for HTTP errors

            # Write the content to the temporary file
            for chunk in response.iter_content(chunk_size=8192):
                temp_file.write(chunk)

            # Close the file
            temp_file.close()

        except Exception as e:
            # Clean up the file if there's an error
            temp_file.close()
            os.unlink(temp_file.name)
            return {"succeed": False, "error": str(e)}

        try:
            obj = self._clean_imported_glb(
                filepath=temp_file.name,
                mesh_name=name
            )
            result = {
                "name": obj.name,
                "type": obj.type,
                "location": [obj.location.x, obj.location.y, obj.location.z],
                "rotation": [obj.rotation_euler.x, obj.rotation_euler.y, obj.rotation_euler.z],
                "scale": [obj.scale.x, obj.scale.y, obj.scale.z],
            }

            if obj.type == "MESH":
                bounding_box = self._get_aabb(obj)
                result["world_bounding_box"] = bounding_box

            return {
                "succeed": True, **result
            }
        except Exception as e:
            return {"succeed": False, "error": str(e)}
    #endregion
 
    #region Sketchfab API
    def get_sketchfab_status(self):
        """Get the current status of Sketchfab integration"""
        enabled = bpy.context.scene.blendermcp_use_sketchfab
        api_key = bpy.context.scene.blendermcp_sketchfab_api_key

        # Test the API key if present
        if api_key:
            try:
                headers = {
                    "Authorization": f"Token {api_key}"
                }

                response = requests.get(
                    "https://api.sketchfab.com/v3/me",
                    headers=headers,
                    timeout=30  # Add timeout of 30 seconds
                )

                if response.status_code == 200:
                    user_data = response.json()
                    username = user_data.get("username", "Unknown user")
                    return {
                        "enabled": True,
                        "message": f"Sketchfab integration is enabled and ready to use. Logged in as: {username}"
                    }
                else:
                    return {
                        "enabled": False,
                        "message": f"Sketchfab API key seems invalid. Status code: {response.status_code}"
                    }
            except requests.exceptions.Timeout:
                return {
                    "enabled": False,
                    "message": "Timeout connecting to Sketchfab API. Check your internet connection."
                }
            except Exception as e:
                return {
                    "enabled": False,
                    "message": f"Error testing Sketchfab API key: {str(e)}"
                }

        if enabled and api_key:
            return {"enabled": True, "message": "Sketchfab integration is enabled and ready to use."}
        elif enabled and not api_key:
            return {
                "enabled": False,
                "message": """Sketchfab integration is currently enabled, but API key is not given. To enable it:
                            1. In the 3D Viewport, find the BlenderMCP panel in the sidebar (press N if hidden)
                            2. Keep the 'Use Sketchfab' checkbox checked
                            3. Enter your Sketchfab API Key
                            4. Restart the connection to Claude"""
            }
        else:
            return {
                "enabled": False,
                "message": """Sketchfab integration is currently disabled. To enable it:
                            1. In the 3D Viewport, find the BlenderMCP panel in the sidebar (press N if hidden)
                            2. Check the 'Use assets from Sketchfab' checkbox
                            3. Enter your Sketchfab API Key
                            4. Restart the connection to Claude"""
            }

    def search_sketchfab_models(self, query, categories=None, count=20, downloadable=True):
        """Search for models on Sketchfab based on query and optional filters"""
        try:
            api_key = bpy.context.scene.blendermcp_sketchfab_api_key
            if not api_key:
                return {"error": "Sketchfab API key is not configured"}

            # Build search parameters with exact fields from Sketchfab API docs
            params = {
                "type": "models",
                "q": query,
                "count": count,
                "downloadable": downloadable,
                "archives_flavours": False
            }

            if categories:
                params["categories"] = categories

            # Make API request to Sketchfab search endpoint
            # The proper format according to Sketchfab API docs for API key auth
            headers = {
                "Authorization": f"Token {api_key}"
            }


            # Use the search endpoint as specified in the API documentation
            response = requests.get(
                "https://api.sketchfab.com/v3/search",
                headers=headers,
                params=params,
                timeout=30  # Add timeout of 30 seconds
            )

            if response.status_code == 401:
                return {"error": "Authentication failed (401). Check your API key."}

            if response.status_code != 200:
                return {"error": f"API request failed with status code {response.status_code}"}

            response_data = response.json()

            # Safety check on the response structure
            if response_data is None:
                return {"error": "Received empty response from Sketchfab API"}

            # Handle 'results' potentially missing from response
            results = response_data.get("results", [])
            if not isinstance(results, list):
                return {"error": f"Unexpected response format from Sketchfab API: {response_data}"}

            return response_data

        except requests.exceptions.Timeout:
            return {"error": "Request timed out. Check your internet connection."}
        except json.JSONDecodeError as e:
            return {"error": f"Invalid JSON response from Sketchfab API: {str(e)}"}
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"error": str(e)}

    def get_sketchfab_model_preview(self, uid):
        """Get thumbnail preview image of a Sketchfab model by its UID"""
        try:
            import base64
            
            api_key = bpy.context.scene.blendermcp_sketchfab_api_key
            if not api_key:
                return {"error": "Sketchfab API key is not configured"}

            headers = {"Authorization": f"Token {api_key}"}
            
            # Get model info which includes thumbnails
            response = requests.get(
                f"https://api.sketchfab.com/v3/models/{uid}",
                headers=headers,
                timeout=30
            )
            
            if response.status_code == 401:
                return {"error": "Authentication failed (401). Check your API key."}
            
            if response.status_code == 404:
                return {"error": f"Model not found: {uid}"}
            
            if response.status_code != 200:
                return {"error": f"Failed to get model info: {response.status_code}"}
            
            data = response.json()
            thumbnails = data.get("thumbnails", {}).get("images", [])
            
            if not thumbnails:
                return {"error": "No thumbnail available for this model"}
            
            # Find a suitable thumbnail (prefer medium size ~640px)
            selected_thumbnail = None
            for thumb in thumbnails:
                width = thumb.get("width", 0)
                if 400 <= width <= 800:
                    selected_thumbnail = thumb
                    break
            
            # Fallback to the first available thumbnail
            if not selected_thumbnail:
                selected_thumbnail = thumbnails[0]
            
            thumbnail_url = selected_thumbnail.get("url")
            if not thumbnail_url:
                return {"error": "Thumbnail URL not found"}
            
            # Download the thumbnail image
            img_response = requests.get(thumbnail_url, timeout=30)
            if img_response.status_code != 200:
                return {"error": f"Failed to download thumbnail: {img_response.status_code}"}
            
            # Encode image as base64
            image_data = base64.b64encode(img_response.content).decode('ascii')
            
            # Determine format from content type or URL
            content_type = img_response.headers.get("Content-Type", "")
            if "png" in content_type or thumbnail_url.endswith(".png"):
                img_format = "png"
            else:
                img_format = "jpeg"
            
            # Get additional model info for context
            model_name = data.get("name", "Unknown")
            author = data.get("user", {}).get("username", "Unknown")
            
            return {
                "success": True,
                "image_data": image_data,
                "format": img_format,
                "model_name": model_name,
                "author": author,
                "uid": uid,
                "thumbnail_width": selected_thumbnail.get("width"),
                "thumbnail_height": selected_thumbnail.get("height")
            }
            
        except requests.exceptions.Timeout:
            return {"error": "Request timed out. Check your internet connection."}
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"error": f"Failed to get model preview: {str(e)}"}

    def download_sketchfab_model(self, uid, normalize_size=False, target_size=1.0):
        """Download a model from Sketchfab by its UID
        
        Parameters:
        - uid: The unique identifier of the Sketchfab model
        - normalize_size: If True, scale the model so its largest dimension equals target_size
        - target_size: The target size in Blender units (meters) for the largest dimension
        """
        try:
            api_key = bpy.context.scene.blendermcp_sketchfab_api_key
            if not api_key:
                return {"error": "Sketchfab API key is not configured"}

            # Use proper authorization header for API key auth
            headers = {
                "Authorization": f"Token {api_key}"
            }

            # Request download URL using the exact endpoint from the documentation
            download_endpoint = f"https://api.sketchfab.com/v3/models/{uid}/download"

            response = requests.get(
                download_endpoint,
                headers=headers,
                timeout=30  # Add timeout of 30 seconds
            )

            if response.status_code == 401:
                return {"error": "Authentication failed (401). Check your API key."}

            if response.status_code != 200:
                return {"error": f"Download request failed with status code {response.status_code}"}

            data = response.json()

            # Safety check for None data
            if data is None:
                return {"error": "Received empty response from Sketchfab API for download request"}

            # Extract download URL with safety checks
            gltf_data = data.get("gltf")
            if not gltf_data:
                return {"error": "No gltf download URL available for this model. Response: " + str(data)}

            download_url = gltf_data.get("url")
            if not download_url:
                return {"error": "No download URL available for this model. Make sure the model is downloadable and you have access."}

            # Download the model (already has timeout)
            model_response = requests.get(download_url, timeout=60)  # 60 second timeout

            if model_response.status_code != 200:
                return {"error": f"Model download failed with status code {model_response.status_code}"}

            # Save to temporary file
            temp_dir = tempfile.mkdtemp()
            zip_file_path = os.path.join(temp_dir, f"{uid}.zip")

            with open(zip_file_path, "wb") as f:
                f.write(model_response.content)

            # Extract the zip file with enhanced security
            with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
                # More secure zip slip prevention
                for file_info in zip_ref.infolist():
                    # Get the path of the file
                    file_path = file_info.filename

                    # Convert directory separators to the current OS style
                    # This handles both / and \ in zip entries
                    target_path = os.path.join(temp_dir, os.path.normpath(file_path))

                    # Get absolute paths for comparison
                    abs_temp_dir = os.path.abspath(temp_dir)
                    abs_target_path = os.path.abspath(target_path)

                    # Ensure the normalized path doesn't escape the target directory
                    if not abs_target_path.startswith(abs_temp_dir):
                        with suppress(Exception):
                            shutil.rmtree(temp_dir)
                        return {"error": "Security issue: Zip contains files with path traversal attempt"}

                    # Additional explicit check for directory traversal
                    if ".." in file_path:
                        with suppress(Exception):
                            shutil.rmtree(temp_dir)
                        return {"error": "Security issue: Zip contains files with directory traversal sequence"}

                # If all files passed security checks, extract them
                zip_ref.extractall(temp_dir)

            # Find the main glTF file
            gltf_files = [f for f in os.listdir(temp_dir) if f.endswith('.gltf') or f.endswith('.glb')]

            if not gltf_files:
                with suppress(Exception):
                    shutil.rmtree(temp_dir)
                return {"error": "No glTF file found in the downloaded model"}

            main_file = os.path.join(temp_dir, gltf_files[0])

            # Import the model
            bpy.ops.import_scene.gltf(filepath=main_file)

            # Get the imported objects
            imported_objects = list(bpy.context.selected_objects)
            imported_object_names = [obj.name for obj in imported_objects]

            # Clean up temporary files
            with suppress(Exception):
                shutil.rmtree(temp_dir)

            # Find root objects (objects without parents in the imported set)
            root_objects = [obj for obj in imported_objects if obj.parent is None]

            # Helper function to recursively get all mesh children
            def get_all_mesh_children(obj):
                """Recursively collect all mesh objects in the hierarchy"""
                meshes = []
                if obj.type == 'MESH':
                    meshes.append(obj)
                for child in obj.children:
                    meshes.extend(get_all_mesh_children(child))
                return meshes

            # Collect ALL meshes from the entire hierarchy (starting from roots)
            all_meshes = []
            for obj in root_objects:
                all_meshes.extend(get_all_mesh_children(obj))
            
            if all_meshes:
                # Calculate combined world bounding box for all meshes
                all_min = mathutils.Vector((float('inf'), float('inf'), float('inf')))
                all_max = mathutils.Vector((float('-inf'), float('-inf'), float('-inf')))
                
                for mesh_obj in all_meshes:
                    # Get world-space bounding box corners
                    for corner in mesh_obj.bound_box:
                        world_corner = mesh_obj.matrix_world @ mathutils.Vector(corner)
                        all_min.x = min(all_min.x, world_corner.x)
                        all_min.y = min(all_min.y, world_corner.y)
                        all_min.z = min(all_min.z, world_corner.z)
                        all_max.x = max(all_max.x, world_corner.x)
                        all_max.y = max(all_max.y, world_corner.y)
                        all_max.z = max(all_max.z, world_corner.z)
                
                # Calculate dimensions
                dimensions = [
                    all_max.x - all_min.x,
                    all_max.y - all_min.y,
                    all_max.z - all_min.z
                ]
                max_dimension = max(dimensions)
                
                # Apply normalization if requested
                scale_applied = 1.0
                if normalize_size and max_dimension > 0:
                    scale_factor = target_size / max_dimension
                    scale_applied = scale_factor
                    
                    # ✅ Only apply scale to ROOT objects (not children!)
                    # Child objects inherit parent's scale through matrix_world
                    for root in root_objects:
                        root.scale = (
                            root.scale.x * scale_factor,
                            root.scale.y * scale_factor,
                            root.scale.z * scale_factor
                        )
                    
                    # Update the scene to recalculate matrix_world for all objects
                    bpy.context.view_layer.update()
                    
                    # Recalculate bounding box after scaling
                    all_min = mathutils.Vector((float('inf'), float('inf'), float('inf')))
                    all_max = mathutils.Vector((float('-inf'), float('-inf'), float('-inf')))
                    
                    for mesh_obj in all_meshes:
                        for corner in mesh_obj.bound_box:
                            world_corner = mesh_obj.matrix_world @ mathutils.Vector(corner)
                            all_min.x = min(all_min.x, world_corner.x)
                            all_min.y = min(all_min.y, world_corner.y)
                            all_min.z = min(all_min.z, world_corner.z)
                            all_max.x = max(all_max.x, world_corner.x)
                            all_max.y = max(all_max.y, world_corner.y)
                            all_max.z = max(all_max.z, world_corner.z)
                    
                    dimensions = [
                        all_max.x - all_min.x,
                        all_max.y - all_min.y,
                        all_max.z - all_min.z
                    ]
                
                world_bounding_box = [[all_min.x, all_min.y, all_min.z], [all_max.x, all_max.y, all_max.z]]
            else:
                world_bounding_box = None
                dimensions = None
                scale_applied = 1.0

            result = {
                "success": True,
                "message": "Model imported successfully",
                "imported_objects": imported_object_names
            }
            
            if world_bounding_box:
                result["world_bounding_box"] = world_bounding_box
            if dimensions:
                result["dimensions"] = [round(d, 4) for d in dimensions]
            if normalize_size:
                result["scale_applied"] = round(scale_applied, 6)
                result["normalized"] = True
            
            return result

        except requests.exceptions.Timeout:
            return {"error": "Request timed out. Check your internet connection and try again with a simpler model."}
        except json.JSONDecodeError as e:
            return {"error": f"Invalid JSON response from Sketchfab API: {str(e)}"}
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"error": f"Failed to download model: {str(e)}"}
    #endregion

    #region Hunyuan3D
    def get_hunyuan3d_status(self):
        """Get the current status of Hunyuan3D integration"""
        enabled = bpy.context.scene.blendermcp_use_hunyuan3d
        hunyuan3d_mode = bpy.context.scene.blendermcp_hunyuan3d_mode
        if enabled:
            match hunyuan3d_mode:
                case "OFFICIAL_API":
                    if not bpy.context.scene.blendermcp_hunyuan3d_secret_id or not bpy.context.scene.blendermcp_hunyuan3d_secret_key:
                        return {
                            "enabled": False, 
                            "mode": hunyuan3d_mode, 
                            "message": """Hunyuan3D integration is currently enabled, but SecretId or SecretKey is not given. To enable it:
                                1. In the 3D Viewport, find the BlenderMCP panel in the sidebar (press N if hidden)
                                2. Keep the 'Use Tencent Hunyuan 3D model generation' checkbox checked
                                3. Choose the right platform and fill in the SecretId and SecretKey
                                4. Restart the connection to Claude"""
                        }
                case "LOCAL_API":
                    if not bpy.context.scene.blendermcp_hunyuan3d_api_url:
                        return {
                            "enabled": False, 
                            "mode": hunyuan3d_mode, 
                            "message": """Hunyuan3D integration is currently enabled, but API URL  is not given. To enable it:
                                1. In the 3D Viewport, find the BlenderMCP panel in the sidebar (press N if hidden)
                                2. Keep the 'Use Tencent Hunyuan 3D model generation' checkbox checked
                                3. Choose the right platform and fill in the API URL
                                4. Restart the connection to Claude"""
                        }
                case _:
                    return {
                        "enabled": False, 
                        "message": "Hunyuan3D integration is enabled and mode is not supported."
                    }
            return {
                "enabled": True, 
                "mode": hunyuan3d_mode,
                "message": "Hunyuan3D integration is enabled and ready to use."
            }
        return {
            "enabled": False, 
            "message": """Hunyuan3D integration is currently disabled. To enable it:
                        1. In the 3D Viewport, find the BlenderMCP panel in the sidebar (press N if hidden)
                        2. Check the 'Use Tencent Hunyuan 3D model generation' checkbox
                        3. Restart the connection to Claude"""
        }
    
    @staticmethod
    def get_tencent_cloud_sign_headers(
        method: str,
        path: str,
        headParams: dict,
        data: dict,
        service: str,
        region: str,
        secret_id: str,
        secret_key: str,
        host: str = None
    ):
        """Generate the signature header required for Tencent Cloud API requests headers"""
        # Generate timestamp
        timestamp = int(time.time())
        date = datetime.utcfromtimestamp(timestamp).strftime("%Y-%m-%d")
        
        # If host is not provided, it is generated based on service and region.
        if not host:
            host = f"{service}.tencentcloudapi.com"
        
        endpoint = f"https://{host}"
        
        # Constructing the request body
        payload_str = json.dumps(data)
        
        # ************* Step 1: Concatenate the canonical request string *************
        canonical_uri = path
        canonical_querystring = ""
        ct = "application/json; charset=utf-8"
        canonical_headers = f"content-type:{ct}\nhost:{host}\nx-tc-action:{headParams.get('Action', '').lower()}\n"
        signed_headers = "content-type;host;x-tc-action"
        hashed_request_payload = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()
        
        canonical_request = (method + "\n" +
                            canonical_uri + "\n" +
                            canonical_querystring + "\n" +
                            canonical_headers + "\n" +
                            signed_headers + "\n" +
                            hashed_request_payload)

        # ************* Step 2: Construct the reception signature string *************
        credential_scope = f"{date}/{service}/tc3_request"
        hashed_canonical_request = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
        string_to_sign = ("TC3-HMAC-SHA256" + "\n" +
                        str(timestamp) + "\n" +
                        credential_scope + "\n" +
                        hashed_canonical_request)

        # ************* Step 3: Calculate the signature *************
        def sign(key, msg):
            return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

        secret_date = sign(("TC3" + secret_key).encode("utf-8"), date)
        secret_service = sign(secret_date, service)
        secret_signing = sign(secret_service, "tc3_request")
        signature = hmac.new(
            secret_signing, 
            string_to_sign.encode("utf-8"), 
            hashlib.sha256
        ).hexdigest()

        # ************* Step 4: Connect Authorization *************
        authorization = ("TC3-HMAC-SHA256" + " " +
                        "Credential=" + secret_id + "/" + credential_scope + ", " +
                        "SignedHeaders=" + signed_headers + ", " +
                        "Signature=" + signature)

        # Constructing request headers
        headers = {
            "Authorization": authorization,
            "Content-Type": "application/json; charset=utf-8",
            "Host": host,
            "X-TC-Action": headParams.get("Action", ""),
            "X-TC-Timestamp": str(timestamp),
            "X-TC-Version": headParams.get("Version", ""),
            "X-TC-Region": region
        }

        return headers, endpoint

    def create_hunyuan_job(self, *args, **kwargs):
        match bpy.context.scene.blendermcp_hunyuan3d_mode:
            case "OFFICIAL_API":
                return self.create_hunyuan_job_main_site(*args, **kwargs)
            case "LOCAL_API":
                return self.create_hunyuan_job_local_site(*args, **kwargs)
            case _:
                return f"Error: Unknown Hunyuan3D mode!"

    def create_hunyuan_job_main_site(
        self,
        text_prompt: str = None,
        image: str = None
    ):
        try:
            secret_id = bpy.context.scene.blendermcp_hunyuan3d_secret_id
            secret_key = bpy.context.scene.blendermcp_hunyuan3d_secret_key

            if not secret_id or not secret_key:
                return {"error": "SecretId or SecretKey is not given"}

            # Parameter verification
            if not text_prompt and not image:
                return {"error": "Prompt or Image is required"}
            if text_prompt and image:
                return {"error": "Prompt and Image cannot be provided simultaneously"}
            # Fixed parameter configuration
            service = "hunyuan"
            action = "SubmitHunyuanTo3DJob"
            version = "2023-09-01"
            region = "ap-guangzhou"

            headParams={
                "Action": action,
                "Version": version,
                "Region": region,
            }

            # Constructing request parameters
            data = {
                "Num": 1  # The current API limit is only 1
            }

            # Handling text prompts
            if text_prompt:
                if len(text_prompt) > 200:
                    return {"error": "Prompt exceeds 200 characters limit"}
                data["Prompt"] = text_prompt

            # Handling image
            if image:
                if re.match(r'^https?://', image, re.IGNORECASE) is not None:
                    data["ImageUrl"] = image
                else:
                    try:
                        # Convert to Base64 format
                        with open(image, "rb") as f:
                            image_base64 = base64.b64encode(f.read()).decode("ascii")
                        data["ImageBase64"] = image_base64
                    except Exception as e:
                        return {"error": f"Image encoding failed: {str(e)}"}
            
            # Get signed headers
            headers, endpoint = self.get_tencent_cloud_sign_headers("POST", "/", headParams, data, service, region, secret_id, secret_key)

            response = requests.post(
                endpoint,
                headers = headers,
                data = json.dumps(data)
            )

            if response.status_code == 200:
                return response.json()
            return {
                "error": f"API request failed with status {response.status_code}: {response}"
            }
        except Exception as e:
            return {"error": str(e)}

    def create_hunyuan_job_local_site(
        self,
        text_prompt: str = None,
        image: str = None):
        try:
            base_url = bpy.context.scene.blendermcp_hunyuan3d_api_url.rstrip('/')
            octree_resolution = bpy.context.scene.blendermcp_hunyuan3d_octree_resolution
            num_inference_steps = bpy.context.scene.blendermcp_hunyuan3d_num_inference_steps
            guidance_scale = bpy.context.scene.blendermcp_hunyuan3d_guidance_scale
            texture = bpy.context.scene.blendermcp_hunyuan3d_texture

            if not base_url:
                return {"error": "API URL is not given"}
            # Parameter verification
            if not text_prompt and not image:
                return {"error": "Prompt or Image is required"}

            # Constructing request parameters
            data = {
                "octree_resolution": octree_resolution,
                "num_inference_steps": num_inference_steps,
                "guidance_scale": guidance_scale,
                "texture": texture,
            }

            # Handling text prompts
            if text_prompt:
                data["text"] = text_prompt

            # Handling image
            if image:
                if re.match(r'^https?://', image, re.IGNORECASE) is not None:
                    try:
                        resImg = requests.get(image)
                        resImg.raise_for_status()
                        image_base64 = base64.b64encode(resImg.content).decode("ascii")
                        data["image"] = image_base64
                    except Exception as e:
                        return {"error": f"Failed to download or encode image: {str(e)}"} 
                else:
                    try:
                        # Convert to Base64 format
                        with open(image, "rb") as f:
                            image_base64 = base64.b64encode(f.read()).decode("ascii")
                        data["image"] = image_base64
                    except Exception as e:
                        return {"error": f"Image encoding failed: {str(e)}"}

            response = requests.post(
                f"{base_url}/generate",
                json = data,
            )

            if response.status_code != 200:
                return {
                    "error": f"Generation failed: {response.text}"
                }
        
            # Decode base64 and save to temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix=".glb") as temp_file:
                temp_file.write(response.content)
                temp_file_name = temp_file.name

            # Import the GLB file in the main thread
            def import_handler():
                bpy.ops.import_scene.gltf(filepath=temp_file_name)
                os.unlink(temp_file.name)
                return None
            
            bpy.app.timers.register(import_handler)

            return {
                "status": "DONE",
                "message": "Generation and Import glb succeeded"
            }
        except Exception as e:
            print(f"An error occurred: {e}")
            return {"error": str(e)}
        
    
    def poll_hunyuan_job_status(self, *args, **kwargs):
        return self.poll_hunyuan_job_status_ai(*args, **kwargs)
    
    def poll_hunyuan_job_status_ai(self, job_id: str):
        """Call the job status API to get the job status"""
        print(job_id)
        try:
            secret_id = bpy.context.scene.blendermcp_hunyuan3d_secret_id
            secret_key = bpy.context.scene.blendermcp_hunyuan3d_secret_key

            if not secret_id or not secret_key:
                return {"error": "SecretId or SecretKey is not given"}
            if not job_id:
                return {"error": "JobId is required"}
            
            service = "hunyuan"
            action = "QueryHunyuanTo3DJob"
            version = "2023-09-01"
            region = "ap-guangzhou"

            headParams={
                "Action": action,
                "Version": version,
                "Region": region,
            }

            clean_job_id = job_id.removeprefix("job_")
            data = {
                "JobId": clean_job_id
            }

            headers, endpoint = self.get_tencent_cloud_sign_headers("POST", "/", headParams, data, service, region, secret_id, secret_key)

            response = requests.post(
                endpoint,
                headers=headers,
                data=json.dumps(data)
            )

            if response.status_code == 200:
                return response.json()
            return {
                "error": f"API request failed with status {response.status_code}: {response}"
            }
        except Exception as e:
            return {"error": str(e)}

    def import_generated_asset_hunyuan(self, *args, **kwargs):
        return self.import_generated_asset_hunyuan_ai(*args, **kwargs)
            
    def import_generated_asset_hunyuan_ai(self, name: str , zip_file_url: str):
        if not zip_file_url:
            return {"error": "Zip file not found"}
        
        # Validate URL
        if not re.match(r'^https?://', zip_file_url, re.IGNORECASE):
            return {"error": "Invalid URL format. Must start with http:// or https://"}
        
        # Create a temporary directory
        temp_dir = tempfile.mkdtemp(prefix="tencent_obj_")
        zip_file_path = osp.join(temp_dir, "model.zip")
        obj_file_path = osp.join(temp_dir, "model.obj")
        mtl_file_path = osp.join(temp_dir, "model.mtl")

        try:
            # Download ZIP file
            zip_response = requests.get(zip_file_url, stream=True)
            zip_response.raise_for_status()
            with open(zip_file_path, "wb") as f:
                for chunk in zip_response.iter_content(chunk_size=8192):
                    f.write(chunk)

            # Unzip the ZIP
            with zipfile.ZipFile(zip_file_path, "r") as zip_ref:
                zip_ref.extractall(temp_dir)

            # Find the .obj file (there may be multiple, assuming the main file is model.obj)
            for file in os.listdir(temp_dir):
                if file.endswith(".obj"):
                    obj_file_path = osp.join(temp_dir, file)

            if not osp.exists(obj_file_path):
                return {"succeed": False, "error": "OBJ file not found after extraction"}

            # Import obj file
            if bpy.app.version>=(4, 0, 0):
                bpy.ops.wm.obj_import(filepath=obj_file_path)
            else:
                bpy.ops.import_scene.obj(filepath=obj_file_path)

            imported_objs = [obj for obj in bpy.context.selected_objects if obj.type == 'MESH']
            if not imported_objs:
                return {"succeed": False, "error": "No mesh objects imported"}

            obj = imported_objs[0]
            if name:
                obj.name = name

            result = {
                "name": obj.name,
                "type": obj.type,
                "location": [obj.location.x, obj.location.y, obj.location.z],
                "rotation": [obj.rotation_euler.x, obj.rotation_euler.y, obj.rotation_euler.z],
                "scale": [obj.scale.x, obj.scale.y, obj.scale.z],
            }

            if obj.type == "MESH":
                bounding_box = self._get_aabb(obj)
                result["world_bounding_box"] = bounding_box

            return {"succeed": True, **result}
        except Exception as e:
            return {"succeed": False, "error": str(e)}
        finally:
            #  Clean up temporary zip and obj, save texture and mtl
            try:
                if os.path.exists(zip_file_path):
                    os.remove(zip_file_path) 
                if os.path.exists(obj_file_path):
                    os.remove(obj_file_path)
            except Exception as e:
                print(f"Failed to clean up temporary directory {temp_dir}: {e}")
    # ── City Tools ──────────────────────────────────────────────────────────────

    def get_scene_graph(self):
        """Return a compact JSON scene graph for the entire active scene."""
        import math

        POLYCOUNT_BUDGET = 50_000

        def _round3(v):
            return [round(float(x), 4) for x in v]

        def _collection_tree(col):
            return {
                "name": col.name,
                "children": [_collection_tree(c) for c in col.children],
                "objects": [o.name for o in col.objects],
            }

        scene = bpy.context.scene
        objects = []
        total_verts = 0
        total_faces = 0
        total_materials_used = set()

        for obj in scene.objects:
            entry = {
                "name": obj.name,
                "type": obj.type,
                "location": _round3(obj.location),
                "rotation_euler": _round3(obj.rotation_euler),
                "scale": _round3(obj.scale),
                "visible": obj.visible_get(),
                "parent": obj.parent.name if obj.parent else None,
                "children": [c.name for c in obj.children],
                "materials": [s.material.name if s.material else None for s in obj.material_slots],
                "modifiers": [m.name for m in obj.modifiers],
            }
            if obj.type == "MESH" and obj.data:
                m = obj.data
                nv = len(m.vertices)
                nf = len(m.polygons)
                total_verts += nv
                total_faces += nf
                for slot in obj.material_slots:
                    if slot.material:
                        total_materials_used.add(slot.material.name)

                entry["mesh"] = {
                    "vertices": nv,
                    "edges": len(m.edges),
                    "faces": nf,
                }
                if nf > POLYCOUNT_BUDGET:
                    entry["mesh"]["budget_warning"] = (
                        f"faces ({nf}) exceeds budget of {POLYCOUNT_BUDGET}"
                    )

                # Quick health flags (no bmesh — cheap)
                health = []
                if not obj.material_slots or all(s.material is None for s in obj.material_slots):
                    health.append("no_material")
                if not m.uv_layers:
                    health.append("no_uv")
                # Inverted-normals heuristic: sample up to 200 faces, count inward-pointing
                centroid = mathutils.Vector((0.0, 0.0, 0.0))
                if m.vertices:
                    for v in m.vertices:
                        centroid += v.co
                    centroid /= len(m.vertices)
                sample = m.polygons[:200]
                inward = sum(
                    1 for f in sample
                    if (f.center - centroid).normalized().dot(
                        mathutils.Vector(f.normal).normalized()) < -0.4
                )
                if inward > len(sample) * 0.1:
                    health.append("likely_inverted_normals")

                if health:
                    entry["health_flags"] = health

                try:
                    entry["bbox"] = self._get_aabb(obj)
                except Exception:
                    pass

            objects.append(entry)

        # Scene-level memory estimate: ~32 bytes/vertex (pos + normal + uv + color)
        mem_mb = round(total_verts * 32 / 1_048_576, 2)

        collections = [_collection_tree(c) for c in scene.collection.children]
        return {
            "scene": scene.name,
            "frame_current": scene.frame_current,
            "object_count": len(objects),
            "objects": objects,
            "collections": collections,
            "totals": {
                "vertices": total_verts,
                "faces": total_faces,
                "unique_materials": len(total_materials_used),
                "estimated_memory_mb": mem_mb,
            },
        }

    def validate_geometry(self, object_name=None):
        """Run mesh analysis on one object or the whole scene.

        Each issue carries a 'severity' field: CRITICAL / WARNING / INFO.
        """
        import bmesh

        # ── helpers ──────────────────────────────────────────────────────────
        def _issue(severity, type_, **kw):
            return {"severity": severity, "type": type_, **kw}

        def _validate_obj(obj):
            report = {
                "object": obj.name,
                "issues": [],   # flat list, each entry has severity + type
                "clean": True,
            }
            if obj.type != "MESH" or not obj.data:
                report["issues"].append(_issue("INFO", "not_a_mesh"))
                return report

            mesh = obj.data

            # ── bmesh checks ─────────────────────────────────────────────────
            bm = bmesh.new()
            bm.from_mesh(mesh)
            bm.normal_update()

            # Non-manifold edges
            non_manifold = [e.index for e in bm.edges if not e.is_manifold]
            if non_manifold:
                report["issues"].append(_issue(
                    "CRITICAL", "non_manifold_edges",
                    count=len(non_manifold), indices=non_manifold[:50]))
                report["clean"] = False

            # Isolated vertices
            isolated = [v.index for v in bm.verts if not v.link_edges]
            if isolated:
                report["issues"].append(_issue(
                    "WARNING", "isolated_vertices",
                    count=len(isolated), indices=isolated[:50]))

            # Zero-area faces
            zero_area = [f.index for f in bm.faces if f.calc_area() < 1e-8]
            if zero_area:
                report["issues"].append(_issue(
                    "CRITICAL", "zero_area_faces",
                    count=len(zero_area), indices=zero_area[:50]))
                report["clean"] = False

            # Inverted normals heuristic
            centroid = bm.calc_center_median()
            inverted = [
                f.index for f in bm.faces
                if (f.calc_center_median() - centroid).length > 1e-6
                and f.normal.dot((f.calc_center_median() - centroid).normalized()) < -0.5
            ]
            if inverted:
                report["issues"].append(_issue(
                    "WARNING", "inverted_normals",
                    count=len(inverted), indices=inverted[:50]))

            # Duplicate / overlapping faces
            face_sets: dict = {}
            for f in bm.faces:
                key = frozenset(v.index for v in f.verts)
                face_sets.setdefault(key, []).append(f.index)
            duplicates = [idxs for idxs in face_sets.values() if len(idxs) > 1]
            if duplicates:
                flat = [i for grp in duplicates for i in grp]
                report["issues"].append(_issue(
                    "CRITICAL", "duplicate_faces",
                    count=len(duplicates), indices=flat[:50]))
                report["clean"] = False

            bm.free()

            # ── UV checks ────────────────────────────────────────────────────
            if not mesh.uv_layers:
                report["issues"].append(_issue("WARNING", "no_uv_map"))
            elif mesh.uv_layers.active:
                us = [d.uv for d in mesh.uv_layers.active.data]
                if us:
                    xs = [u[0] for u in us]; ys = [u[1] for u in us]
                    coverage = (max(xs) - min(xs)) * (max(ys) - min(ys))
                    if coverage < 0.05:
                        report["issues"].append(_issue(
                            "WARNING", "low_uv_coverage",
                            coverage=round(coverage, 4)))

            # ── Scene-bounds check ───────────────────────────────────────────
            loc = obj.location
            if any(abs(v) > 10_000 for v in loc):
                report["issues"].append(_issue(
                    "WARNING", "outside_scene_bounds",
                    location=[round(float(v), 2) for v in loc]))

            # ── NEW: scale not applied ────────────────────────────────────────
            s = obj.scale
            if abs(s.x - 1.0) > 1e-3 or abs(s.y - 1.0) > 1e-3 or abs(s.z - 1.0) > 1e-3:
                report["issues"].append(_issue(
                    "WARNING", "unapplied_scale",
                    scale=[round(float(v), 4) for v in s]))

            # ── NEW: origin far from geometry center ──────────────────────────
            if mesh.vertices:
                # Geometry centroid in object-local space
                lc = mathutils.Vector((0.0, 0.0, 0.0))
                for v in mesh.vertices:
                    lc += v.co
                lc /= len(mesh.vertices)
                dist = lc.length  # distance from object origin (local 0,0,0)
                if dist > 10.0:
                    report["issues"].append(_issue(
                        "INFO", "origin_far_from_geometry",
                        offset_m=round(dist, 2)))

            return report

        # ── NEW: overlapping objects (scene-level, only when doing whole scene) ──
        def _check_overlapping(objs):
            issues = []
            centroids = {}
            for obj in objs:
                if obj.type != "MESH":
                    continue
                c = (round(obj.location.x, 1),
                     round(obj.location.y, 1),
                     round(obj.location.z, 1))
                centroids.setdefault(c, []).append(obj.name)
            for c, names in centroids.items():
                if len(names) > 1:
                    issues.append({
                        "type": "overlapping_objects",
                        "severity": "WARNING",
                        "centroid": list(c),
                        "objects": names,
                    })
            return issues

        # ── dispatch ─────────────────────────────────────────────────────────
        if object_name:
            obj = bpy.data.objects.get(object_name)
            if not obj:
                return {"error": f"Object not found: {object_name}"}
            return _validate_obj(obj)

        scene_objs = list(bpy.context.scene.objects)
        results = [_validate_obj(o) for o in scene_objs if o.type == "MESH"]
        overlap_issues = _check_overlapping(scene_objs)
        all_clean = all(r["clean"] for r in results) and not overlap_issues
        return {
            "scene_clean": all_clean,
            "objects": results,
            "scene_issues": overlap_issues,
        }

    # In-memory snapshot store (keyed by snapshot_id string)
    _snapshots = {}

    def take_snapshot(self, snapshot_id):
        """Store current scene state keyed by snapshot_id."""
        from datetime import datetime as _dt
        import math

        def _obj_state(obj):
            state = {
                "type": obj.type,
                "location": [round(float(v), 4) for v in obj.location],
                "rotation_euler": [round(float(v), 4) for v in obj.rotation_euler],
                "scale": [round(float(v), 4) for v in obj.scale],
                "materials": [s.material.name if s.material else None for s in obj.material_slots],
            }
            if obj.type == "MESH" and obj.data:
                m = obj.data
                state["mesh"] = {
                    "vertices": len(m.vertices),
                    "faces": len(m.polygons),
                }
                try:
                    state["bbox"] = self._get_aabb(obj)
                except Exception:
                    pass
            return state

        snap = {
            "timestamp": _dt.utcnow().isoformat() + "Z",
            "objects": {obj.name: _obj_state(obj) for obj in bpy.context.scene.objects},
        }
        BlenderMCPServer._snapshots[snapshot_id] = snap
        return {
            "snapshot_id": snapshot_id,
            "object_count": len(snap["objects"]),
            "timestamp": snap["timestamp"],
        }

    def get_scene_diff(self, snapshot_id):
        """Compare current scene to a stored snapshot."""
        snap = BlenderMCPServer._snapshots.get(snapshot_id)
        if snap is None:
            return {"error": f"Snapshot '{snapshot_id}' not found"}

        old_objs = snap["objects"]
        cur_objs = {obj.name: obj for obj in bpy.context.scene.objects}

        added = [n for n in cur_objs if n not in old_objs]
        deleted = [n for n in old_objs if n not in cur_objs]
        modified = []

        for name, obj in cur_objs.items():
            if name not in old_objs:
                continue
            prev = old_objs[name]
            cur_loc = [round(float(v), 4) for v in obj.location]
            if cur_loc != prev.get("location"):
                modified.append({"name": name, "field": "location",
                                  "before": prev.get("location"), "after": cur_loc})
                continue
            if obj.type == "MESH" and obj.data:
                cur_faces = len(obj.data.polygons)
                prev_faces = prev.get("mesh", {}).get("faces")
                if prev_faces is not None and cur_faces != prev_faces:
                    modified.append({
                        "name": name,
                        "field": "face_count",
                        "before": prev_faces,
                        "after": cur_faces,
                    })
                    try:
                        modified[-1]["bbox_after"] = self._get_aabb(obj)
                        modified[-1]["bbox_before"] = prev.get("bbox")
                    except Exception:
                        pass

        return {
            "snapshot_id": snapshot_id,
            "snapshot_timestamp": snap["timestamp"],
            "added": added,
            "deleted": deleted,
            "modified": modified,
        }

    def export_usd_tile(self, output_path, center, radius_m):
        """Export a spatial USD tile for objects within radius_m of center [x, y]."""
        import mathutils as mu
        cx, cy = float(center[0]), float(center[1])
        r = float(radius_m)

        # Collect objects within radius
        scene = bpy.context.scene
        selected_names = []
        for obj in scene.objects:
            ox, oy = obj.location.x, obj.location.y
            if ((ox - cx) ** 2 + (oy - cy) ** 2) <= r * r:
                selected_names.append(obj.name)

        if not selected_names:
            return {"error": "No objects within radius", "object_count": 0}

        # Deselect all, select target objects
        bpy.ops.object.select_all(action='DESELECT')
        for name in selected_names:
            obj = bpy.data.objects.get(name)
            if obj:
                obj.select_set(True)

        # Export USD
        try:
            bpy.ops.wm.usd_export(
                filepath=output_path,
                selected_objects_only=True,
                export_materials=True,
                export_uvmaps=True,
                export_normals=True,
            )
        except Exception as e:
            return {"error": f"USD export failed: {str(e)}"}

        file_size_mb = 0.0
        import os as _os
        if _os.path.exists(output_path):
            file_size_mb = round(_os.path.getsize(output_path) / (1024 * 1024), 3)

        return {
            "path": output_path,
            "file_size_mb": file_size_mb,
            "object_count": len(selected_names),
        }

    def set_geo_origin(self, lat, lon):
        """Store the geo-origin in scene custom properties."""
        scene = bpy.context.scene
        scene["geo_origin_lat"] = float(lat)
        scene["geo_origin_lon"] = float(lon)
        return {"lat": float(lat), "lon": float(lon), "stored": True}

    @staticmethod
    def _latlon_to_xy(lat, lon, origin_lat, origin_lon):
        """Equirectangular projection: 1 Blender unit = 1 metre."""
        import math
        R = 6_371_000.0  # Earth radius in metres
        x = math.radians(lon - origin_lon) * R * math.cos(math.radians(origin_lat))
        y = math.radians(lat - origin_lat) * R
        return x, y

    def import_osm_tile(self, bbox, layer_types):
        """Fetch OSM data from Overpass and build Blender geometry."""
        import math

        scene = bpy.context.scene
        origin_lat = scene.get("geo_origin_lat")
        origin_lon = scene.get("geo_origin_lon")
        if origin_lat is None or origin_lon is None:
            return {"error": "Geo origin not set — call set_geo_origin() first"}

        min_lat = float(bbox["min_lat"])
        max_lat = float(bbox["max_lat"])
        min_lon = float(bbox["min_lon"])
        max_lon = float(bbox["max_lon"])

        # Build Overpass query
        wanted = set(layer_types)
        filters = []
        if "buildings" in wanted:
            filters.append('way["building"]')
        if "roads" in wanted:
            filters.append('way["highway"]')
        if "water" in wanted:
            filters.append('way["natural"="water"]')
            filters.append('relation["natural"="water"]')
        if "parks" in wanted:
            filters.append('way["leisure"="park"]')
            filters.append('way["landuse"="grass"]')
        if "railways" in wanted:
            filters.append('way["railway"]')

        bbox_str = f"{min_lat},{min_lon},{max_lat},{max_lon}"
        union_parts = "\n".join(f"  {f}({bbox_str});" for f in filters)
        query = f"""
[out:json][timeout:60];
(
{union_parts}
);
out body;
>;
out skel qt;
"""
        try:
            resp = requests.post(
                "https://overpass-api.de/api/interpreter",
                data={"data": query},
                timeout=90,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            return {"error": f"Overpass API request failed: {str(e)}"}

        # Index nodes by id
        nodes = {}
        for el in data.get("elements", []):
            if el["type"] == "node":
                nx, ny = self._latlon_to_xy(el["lat"], el["lon"], origin_lat, origin_lon)
                nodes[el["id"]] = (nx, ny)

        # Ensure collections exist
        def _ensure_collection(name):
            if name not in bpy.data.collections:
                col = bpy.data.collections.new(name)
                bpy.context.scene.collection.children.link(col)
            return bpy.data.collections[name]

        counts = {lt: 0 for lt in layer_types}
        total = 0

        for el in data.get("elements", []):
            if el["type"] != "way":
                continue
            tags = el.get("tags", {})
            nd_refs = el.get("nodes", [])
            coords = [nodes[n] for n in nd_refs if n in nodes]
            if len(coords) < 2:
                continue

            el_id = el["id"]

            # Determine layer
            if "building" in tags and "buildings" in wanted:
                layer = "buildings"
            elif "highway" in tags and "roads" in wanted:
                layer = "roads"
            elif "natural" in tags and tags["natural"] == "water" and "water" in wanted:
                layer = "water"
            elif ("leisure" in tags or "landuse" in tags) and "parks" in wanted:
                layer = "parks"
            elif "railway" in tags and "railways" in wanted:
                layer = "railways"
            else:
                continue

            col = _ensure_collection(layer)

            # --- Create mesh ---
            verts = [(x, y, 0.0) for x, y in coords]
            mesh = bpy.data.meshes.new(f"osm_{el_id}")
            obj = bpy.data.objects.new(f"osm_{el_id}", mesh)

            # Store OSM tags as custom properties
            obj["osm_id"] = el_id
            obj["osm_layer"] = layer
            for k, v in tags.items():
                obj[f"osm_{k}"] = v

            col.objects.link(obj)

            if layer == "buildings":
                # Extrude footprint
                height_m = 10.0
                if "height" in tags:
                    try:
                        height_m = float(str(tags["height"]).replace("m", "").strip())
                    except ValueError:
                        pass
                elif "building:levels" in tags:
                    try:
                        height_m = float(tags["building:levels"]) * 3.0
                    except ValueError:
                        pass

                n = len(verts)
                top_verts = [(x, y, height_m) for x, y in coords]
                all_verts = verts + top_verts
                bottom_face = list(range(n))
                top_face = list(range(n, 2 * n))[::-1]
                side_faces = []
                for i in range(n - 1):
                    side_faces.append([i, i + 1, n + i + 1, n + i])
                faces = [bottom_face, top_face] + side_faces
                mesh.from_pydata(all_verts, [], faces)

                # Clean up: remove zero-area faces, recalc normals, add UV
                import bmesh as _bm
                bme = _bm.new()
                bme.from_mesh(mesh)
                # Remove zero-area faces
                zero_faces = [f for f in bme.faces if f.calc_area() < 1e-6]
                _bm.ops.delete(bme, geom=zero_faces, context='FACES')
                # Recalculate normals
                _bm.ops.recalc_face_normals(bme, faces=bme.faces[:])
                # Smart UV project
                bme.to_mesh(mesh)
                bme.free()
                mesh.update()
                # UV unwrap via operator (object already linked to collection above)
                bpy.context.view_layer.objects.active = obj
                obj.select_set(True)
                try:
                    bpy.ops.object.mode_set(mode='EDIT')
                    bpy.ops.mesh.select_all(action='SELECT')
                    bpy.ops.uv.smart_project(angle_limit=66.0, island_margin=0.02)
                    bpy.ops.object.mode_set(mode='OBJECT')
                except Exception:
                    try:
                        bpy.ops.object.mode_set(mode='OBJECT')
                    except Exception:
                        pass
                obj.select_set(False)
            else:
                # Polyline as edges
                edges = [(i, i + 1) for i in range(len(verts) - 1)]
                mesh.from_pydata(verts, edges, [])
                mesh.update()

            counts[layer] = counts.get(layer, 0) + 1
            total += 1

        return {"objects_created": total, "layers": counts}

    def import_pointcloud(self, file_path, voxel_size=0.5):
        """Import a .las/.laz point cloud, voxel-downsample, and create a mesh."""
        import os as _os

        if not _os.path.exists(file_path):
            return {"error": f"File not found: {file_path}"}

        ext = _os.path.splitext(file_path)[1].lower()
        if ext not in (".las", ".laz"):
            return {"error": f"Unsupported format: {ext}. Use .las or .laz"}

        # --- Load points ---
        try:
            import laspy
            las = laspy.read(file_path)
            pts = las.xyz  # numpy array (N, 3)
        except ImportError:
            return {"error": "laspy is not installed. Install it with: pip install laspy"}
        except Exception as e:
            return {"error": f"Failed to read point cloud: {str(e)}"}

        points_loaded = len(pts)

        # --- Voxel downsample ---
        try:
            import open3d as o3d
            pcd = o3d.geometry.PointCloud()
            pcd.points = o3d.utility.Vector3dVector(pts)
            pcd = pcd.voxel_down_sample(voxel_size=float(voxel_size))
            pts = pcd.points  # open3d Vector3dVector
            pts_list = [list(p) for p in pts]
        except ImportError:
            # Fallback: simple numpy grid voxelisation
            import numpy as np
            arr = pts
            vox = (arr / float(voxel_size)).astype(int)
            _, unique_idx = np.unique(vox, axis=0, return_index=True)
            arr = arr[unique_idx]
            pts_list = arr.tolist()
        except Exception as e:
            return {"error": f"Voxel downsampling failed: {str(e)}"}

        points_after = len(pts_list)

        # --- Create Blender mesh ---
        try:
            mesh = bpy.data.meshes.new("PointCloud")
            obj = bpy.data.objects.new("PointCloud", mesh)
            bpy.context.scene.collection.objects.link(obj)
            mesh.from_pydata(pts_list, [], [])
            mesh.update()
            mesh_created = True
        except Exception as e:
            return {"error": f"Failed to create mesh: {str(e)}",
                    "points_loaded": points_loaded,
                    "points_after_voxel": points_after,
                    "mesh_created": False}

        return {
            "points_loaded": points_loaded,
            "points_after_voxel": points_after,
            "mesh_created": mesh_created,
        }

    def apply_procedural_materials(self, ruleset="default"):
        """Assign node-tree materials based on collection name / OSM tags."""
        import random

        def _new_mat(name, unique=False):
            """Return existing material by name, or create a new one.
            If unique=True always create a fresh material with that name."""
            if not unique and name in bpy.data.materials:
                return bpy.data.materials[name]
            mat = bpy.data.materials.new(name)
            mat.use_nodes = True
            return mat

        def _clear_nodes(mat):
            mat.node_tree.nodes.clear()

        def _principled(mat, base_color, roughness=0.8, metallic=0.0,
                         transmission=0.0, alpha=1.0):
            nt = mat.node_tree
            out = nt.nodes.new("ShaderNodeOutputMaterial")
            bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
            bsdf.inputs["Base Color"].default_value = (*base_color, 1.0)
            bsdf.inputs["Roughness"].default_value = roughness
            bsdf.inputs["Metallic"].default_value = metallic
            if "Transmission Weight" in bsdf.inputs:
                bsdf.inputs["Transmission Weight"].default_value = transmission
            elif "Transmission" in bsdf.inputs:
                bsdf.inputs["Transmission"].default_value = transmission
            bsdf.inputs["Alpha"].default_value = alpha
            nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
            out.location = (600, 0)
            bsdf.location = (300, 0)
            return bsdf

        def _mat_brick(obj):
            """Brick material: wave-texture brick color + noise mortar + bump depth.
            Each building gets a unique color via Object Info Random node."""
            mat_name = f"mat_brick_{obj.name}"
            mat = _new_mat(mat_name, unique=True)
            _clear_nodes(mat)
            nt = mat.node_tree

            out  = nt.nodes.new("ShaderNodeOutputMaterial");  out.location  = (900, 0)
            bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled");  bsdf.location = (600, 0)
            bsdf.inputs["Roughness"].default_value = 0.9

            # Object Info for per-building unique seed
            obj_info = nt.nodes.new("ShaderNodeObjectInfo"); obj_info.location = (-700, 200)

            # Wave texture drives brick color variation
            wave = nt.nodes.new("ShaderNodeTexWave");  wave.location = (-500, 200)
            wave.wave_type = 'BANDS'
            wave.inputs["Scale"].default_value      = 50.0
            wave.inputs["Distortion"].default_value = 2.0
            wave.inputs["Detail"].default_value     = 4.0

            # Mix brick colors (light brick ↔ dark brick)
            mix_brick = nt.nodes.new("ShaderNodeMixRGB"); mix_brick.location = (-200, 200)
            mix_brick.blend_type = 'MIX'
            mix_brick.inputs["Color1"].default_value = (0.65, 0.30, 0.20, 1.0)
            mix_brick.inputs["Color2"].default_value = (0.55, 0.25, 0.15, 1.0)

            # Noise texture for mortar lines / micro variation
            noise = nt.nodes.new("ShaderNodeTexNoise"); noise.location = (-500, -100)
            noise.inputs["Scale"].default_value  = 80.0
            noise.inputs["Detail"].default_value = 8.0

            # Mix in noise-based mortar (lighter grey between bricks)
            mix_mortar = nt.nodes.new("ShaderNodeMixRGB"); mix_mortar.location = (100, 100)
            mix_mortar.blend_type = 'MIX'
            mix_mortar.inputs["Color2"].default_value = (0.72, 0.70, 0.68, 1.0)  # mortar grey

            # Bump node for surface depth
            bump = nt.nodes.new("ShaderNodeBump"); bump.location = (300, -200)
            bump.inputs["Strength"].default_value = 0.4
            bump.inputs["Distance"].default_value = 0.02

            # Add random per-object hue shift using Object Info Random
            hue_sat = nt.nodes.new("ShaderNodeHueSaturation"); hue_sat.location = (100, -50)
            hue_sat.inputs["Saturation"].default_value = 1.0
            hue_sat.inputs["Value"].default_value      = 1.0
            # Map 0..1 random to 0.95..1.05 hue range
            map_range = nt.nodes.new("ShaderNodeMapRange"); map_range.location = (-200, -200)
            map_range.inputs["From Min"].default_value = 0.0
            map_range.inputs["From Max"].default_value = 1.0
            map_range.inputs["To Min"].default_value   = 0.95
            map_range.inputs["To Max"].default_value   = 1.05

            # Wire up
            nt.links.new(obj_info.outputs["Random"],   wave.inputs["Phase Offset"])
            nt.links.new(wave.outputs["Color"],        mix_brick.inputs["Fac"])
            nt.links.new(noise.outputs["Fac"],         mix_mortar.inputs["Fac"])
            nt.links.new(mix_brick.outputs["Color"],   mix_mortar.inputs["Color1"])
            nt.links.new(obj_info.outputs["Random"],   map_range.inputs["Value"])
            nt.links.new(map_range.outputs["Result"],  hue_sat.inputs["Hue"])
            nt.links.new(mix_mortar.outputs["Color"],  hue_sat.inputs["Color"])
            nt.links.new(hue_sat.outputs["Color"],     bsdf.inputs["Base Color"])
            nt.links.new(noise.outputs["Fac"],         bump.inputs["Height"])
            nt.links.new(bump.outputs["Normal"],       bsdf.inputs["Normal"])
            nt.links.new(bsdf.outputs["BSDF"],         out.inputs["Surface"])
            return mat

        def _mat_concrete(obj):
            """Concrete: Musgrave imperfections + AO-like roughness + per-building color seed."""
            mat_name = f"mat_concrete_{obj.name}"
            mat = _new_mat(mat_name, unique=True)
            _clear_nodes(mat)
            nt = mat.node_tree

            out  = nt.nodes.new("ShaderNodeOutputMaterial"); out.location  = (800, 0)
            bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled"); bsdf.location = (500, 0)

            # Object Info for per-building color seed
            obj_info = nt.nodes.new("ShaderNodeObjectInfo"); obj_info.location = (-700, 200)

            # Noise for surface imperfections (ShaderNodeTexMusgrave removed in Blender 4.x)
            musgrave = nt.nodes.new("ShaderNodeTexNoise"); musgrave.location = (-500, 200)
            musgrave.inputs["Scale"].default_value     = 15.0
            musgrave.inputs["Detail"].default_value    = 8.0

            # Map roughness range: 0.7 to 0.95
            map_rough = nt.nodes.new("ShaderNodeMapRange"); map_rough.location = (-200, 200)
            map_rough.inputs["From Min"].default_value = 0.0
            map_rough.inputs["From Max"].default_value = 1.0
            map_rough.inputs["To Min"].default_value   = 0.70
            map_rough.inputs["To Max"].default_value   = 0.95

            # Subtle color variation per building
            obj_map = nt.nodes.new("ShaderNodeMapRange"); obj_map.location = (-500, -100)
            obj_map.inputs["From Min"].default_value = 0.0
            obj_map.inputs["From Max"].default_value = 1.0
            obj_map.inputs["To Min"].default_value   = 0.58
            obj_map.inputs["To Max"].default_value   = 0.72

            mix_color = nt.nodes.new("ShaderNodeMixRGB"); mix_color.location = (-200, -100)
            mix_color.blend_type = 'MIX'
            mix_color.inputs["Fac"].default_value    = 0.5
            mix_color.inputs["Color1"].default_value = (0.62, 0.60, 0.57, 1.0)
            mix_color.inputs["Color2"].default_value = (0.70, 0.68, 0.65, 1.0)

            # Wire up
            nt.links.new(musgrave.outputs["Fac"],      map_rough.inputs["Value"])
            nt.links.new(map_rough.outputs["Result"],  bsdf.inputs["Roughness"])
            nt.links.new(obj_info.outputs["Random"],   obj_map.inputs["Value"])
            nt.links.new(obj_info.outputs["Random"],   mix_color.inputs["Fac"])
            nt.links.new(mix_color.outputs["Color"],   bsdf.inputs["Base Color"])
            nt.links.new(bsdf.outputs["BSDF"],         out.inputs["Surface"])
            return mat

        def _mat_glass(obj):
            """Glass: thin-film IOR=1.45, reflection tint, fresnel-driven env mix."""
            mat_name = f"mat_glass_{obj.name}"
            mat = _new_mat(mat_name, unique=True)
            _clear_nodes(mat)
            nt = mat.node_tree

            out  = nt.nodes.new("ShaderNodeOutputMaterial"); out.location  = (900, 0)
            bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled"); bsdf.location = (600, 0)
            bsdf.inputs["Roughness"].default_value  = 0.05
            bsdf.inputs["Metallic"].default_value   = 0.0
            bsdf.inputs["IOR"].default_value        = 1.45
            if "Transmission Weight" in bsdf.inputs:
                bsdf.inputs["Transmission Weight"].default_value = 0.85
            elif "Transmission" in bsdf.inputs:
                bsdf.inputs["Transmission"].default_value = 0.85

            # Object Info for per-building random tint
            obj_info = nt.nodes.new("ShaderNodeObjectInfo"); obj_info.location = (-700, 200)

            # Reflection tint base (slightly blue-green)
            tint_mix = nt.nodes.new("ShaderNodeMixRGB"); tint_mix.location = (-300, 200)
            tint_mix.blend_type = 'MIX'
            tint_mix.inputs["Color1"].default_value = (0.70, 0.85, 1.00, 1.0)
            tint_mix.inputs["Color2"].default_value = (0.65, 0.90, 0.85, 1.0)

            # Fresnel for edge reflectivity
            fresnel = nt.nodes.new("ShaderNodeFresnel"); fresnel.location = (-500, -100)
            fresnel.inputs["IOR"].default_value = 1.45

            # Mix glossy (reflective) with glass (transmissive) via fresnel
            glossy = nt.nodes.new("ShaderNodeBsdfGlossy"); glossy.location = (200, -200)
            glossy.inputs["Roughness"].default_value = 0.03
            glossy.inputs["Color"].default_value     = (0.70, 0.85, 1.0, 1.0)

            mix_shader = nt.nodes.new("ShaderNodeMixShader"); mix_shader.location = (500, -150)

            # Wire up
            nt.links.new(obj_info.outputs["Random"],  tint_mix.inputs["Fac"])
            nt.links.new(tint_mix.outputs["Color"],   bsdf.inputs["Base Color"])
            nt.links.new(fresnel.outputs["Fac"],      mix_shader.inputs["Fac"])
            nt.links.new(bsdf.outputs["BSDF"],        mix_shader.inputs[1])
            nt.links.new(glossy.outputs["BSDF"],      mix_shader.inputs[2])
            nt.links.new(mix_shader.outputs["Shader"], out.inputs["Surface"])
            mat.blend_method = "BLEND"
            return mat

        def _mat_building(obj):
            btype = str(obj.get("osm_building", "yes")).lower()
            if btype in ("glass", "commercial", "office", "retail"):
                return _mat_glass(obj)
            elif btype in ("house", "residential", "apartments"):
                return _mat_brick(obj)
            else:
                return _mat_concrete(obj)

        def _mat_road():
            mat = _new_mat("mat_road_asphalt")
            if mat.node_tree and len(mat.node_tree.nodes) > 0:
                return mat  # already built, share it
            mat.use_nodes = True
            _clear_nodes(mat)
            nt = mat.node_tree
            bsdf = _principled(mat, (0.08, 0.08, 0.08), roughness=0.95)
            # Wave texture for subtle lane-marking suggestion
            wave = nt.nodes.new("ShaderNodeTexWave")
            wave.inputs["Scale"].default_value = 0.5
            wave.inputs["Distortion"].default_value = 0.1
            wave.location = (-400, 100)
            mix = nt.nodes.new("ShaderNodeMixRGB")
            mix.inputs["Color1"].default_value = (0.08, 0.08, 0.08, 1)
            mix.inputs["Color2"].default_value = (0.9, 0.9, 0.8, 1)
            mix.inputs["Fac"].default_value = 0.0
            mix.location = (-150, 100)
            nt.links.new(wave.outputs["Color"], mix.inputs["Fac"])
            nt.links.new(mix.outputs["Color"], bsdf.inputs["Base Color"])
            return mat

        def _mat_water():
            mat = _new_mat("mat_water")
            if mat.node_tree and len(mat.node_tree.nodes) > 0:
                return mat
            mat.use_nodes = True
            _clear_nodes(mat)
            bsdf = _principled(mat, (0.05, 0.25, 0.55), roughness=0.05,
                                transmission=0.9, alpha=0.6)
            mat.blend_method = "BLEND"
            return mat

        def _mat_park():
            mat = _new_mat("mat_park_grass")
            if mat.node_tree and len(mat.node_tree.nodes) > 0:
                return mat
            mat.use_nodes = True
            _clear_nodes(mat)
            nt = mat.node_tree
            bsdf = _principled(mat, (0.1, 0.4, 0.08), roughness=0.95)
            musgrave = nt.nodes.new("ShaderNodeTexNoise")
            musgrave.inputs["Scale"].default_value = 20.0
            musgrave.location = (-400, -150)
            nt.links.new(musgrave.outputs["Fac"], bsdf.inputs["Roughness"])
            return mat

        applied = 0

        for obj in bpy.context.scene.objects:
            if obj.type != "MESH":
                continue

            layer = obj.get("osm_layer", "")

            if layer == "buildings":
                mat = _mat_building(obj)
            elif layer in ("roads", "railways"):
                mat = _mat_road()
            elif layer == "water":
                mat = _mat_water()
            elif layer == "parks":
                mat = _mat_park()
            else:
                continue

            if not obj.material_slots:
                obj.data.materials.append(mat)
            else:
                obj.material_slots[0].material = mat
            applied += 1

        return {"ruleset": ruleset, "materials_applied": applied}

    # ── add_street_detail ────────────────────────────────────────────────────

    def add_street_detail(self):
        """Add sidewalks, road markings, and curbs to road objects."""
        import bmesh as _bm
        import math

        scene = bpy.context.scene
        objects_created = 0

        # ---- materials --------------------------------------------------------
        def _get_or_create_mat(name, base_color, roughness=0.85, emission=None):
            if name in bpy.data.materials:
                return bpy.data.materials[name]
            mat = bpy.data.materials.new(name)
            mat.use_nodes = True
            nt = mat.node_tree
            nt.nodes.clear()
            out  = nt.nodes.new("ShaderNodeOutputMaterial"); out.location  = (400, 0)
            if emission is not None:
                em = nt.nodes.new("ShaderNodeEmission"); em.location = (200, 0)
                em.inputs["Color"].default_value   = (*base_color, 1.0)
                em.inputs["Strength"].default_value = emission
                nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
            else:
                bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled"); bsdf.location = (200, 0)
                bsdf.inputs["Base Color"].default_value = (*base_color, 1.0)
                bsdf.inputs["Roughness"].default_value  = roughness
                nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
            return mat

        mat_sidewalk = _get_or_create_mat("mat_sidewalk",    (0.65, 0.63, 0.60), roughness=0.80)
        mat_marking  = _get_or_create_mat("mat_road_marking",(0.95, 0.95, 0.90), emission=0.3)
        mat_curb     = _get_or_create_mat("mat_curb",        (0.50, 0.48, 0.45), roughness=0.75)

        # Collect road mesh objects
        road_objs = [o for o in scene.objects
                     if o.type == 'MESH' and o.get("osm_layer") == "roads"]

        # Ensure street_detail collection
        _SD_COL = "street_detail"
        if _SD_COL not in bpy.data.collections:
            _c = bpy.data.collections.new(_SD_COL)
            scene.collection.children.link(_c)
        detail_col = bpy.data.collections[_SD_COL]

        def _link(obj):
            detail_col.objects.link(obj)

        for road_obj in road_objs:
            try:
                mesh = road_obj.data
                mw   = road_obj.matrix_world

                # Build ordered world-space polyline from edge adjacency
                adj = {}
                for e in mesh.edges:
                    a, b = e.vertices[0], e.vertices[1]
                    adj.setdefault(a, []).append(b)
                    adj.setdefault(b, []).append(a)
                start = next((vi for vi, nb in adj.items() if len(nb) == 1),
                             next(iter(adj), None))
                if start is None:
                    continue
                chain = [start]; prev = None
                while True:
                    cur = chain[-1]
                    nxt = [n for n in adj.get(cur, []) if n != prev]
                    if not nxt:
                        break
                    nxt = nxt[0]
                    if nxt == chain[0] and len(chain) > 2:
                        break
                    chain.append(nxt); prev = cur
                if len(chain) < 2:
                    continue

                pts = [mathutils.Vector((mw @ mesh.vertices[vi].co).to_tuple()[:2] + (0.0,))
                       for vi in chain]
                base = road_obj.name

                # Sidewalk
                sw_bme = _bm.new()
                for i in range(len(pts) - 1):
                    v0, v1 = pts[i], pts[i+1]
                    seg = v1 - v0
                    if seg.length < 0.5: continue
                    seg.normalize()
                    perp = mathutils.Vector((-seg.y, seg.x, 0.0))
                    h = mathutils.Vector((0, 0, 0.15))
                    p = [v0+perp*0.3+h, v1+perp*0.3+h, v1+perp*2.3+h, v0+perp*2.3+h]
                    sw_bme.faces.new([sw_bme.verts.new(x) for x in p])
                if sw_bme.faces:
                    _bm.ops.recalc_face_normals(sw_bme, faces=sw_bme.faces[:])
                    sw_m = bpy.data.meshes.new(f"Sidewalk_{base}")
                    sw_bme.to_mesh(sw_m); sw_m.update(); sw_m.materials.append(mat_sidewalk)
                    sw_o = bpy.data.objects.new(f"Sidewalk_{base}", sw_m)
                    sw_o["street_detail"] = "sidewalk"
                    _link(sw_o); objects_created += 1
                sw_bme.free()

                # Road markings
                mk_bme = _bm.new()
                for i in range(len(pts) - 1):
                    v0, v1 = pts[i], pts[i+1]
                    seg = v1 - v0
                    if seg.length < 1.0: continue
                    seg.normalize()
                    perp = mathutils.Vector((-seg.y, seg.x, 0.0))
                    z = mathutils.Vector((0, 0, 0.01))
                    p = [v0-perp*0.15+z, v1-perp*0.15+z, v1+perp*0.15+z, v0+perp*0.15+z]
                    mk_bme.faces.new([mk_bme.verts.new(x) for x in p])
                if mk_bme.faces:
                    _bm.ops.recalc_face_normals(mk_bme, faces=mk_bme.faces[:])
                    mk_m = bpy.data.meshes.new(f"Markings_{base}")
                    mk_bme.to_mesh(mk_m); mk_m.update(); mk_m.materials.append(mat_marking)
                    mk_o = bpy.data.objects.new(f"Markings_{base}", mk_m)
                    mk_o["street_detail"] = "road_marking"
                    _link(mk_o); objects_created += 1
                mk_bme.free()

                # Curb
                cb_bme = _bm.new()
                for i in range(len(pts) - 1):
                    v0, v1 = pts[i], pts[i+1]
                    seg = v1 - v0
                    if seg.length < 0.3: continue
                    seg.normalize()
                    perp = mathutils.Vector((-seg.y, seg.x, 0.0))
                    h = mathutils.Vector((0, 0, 0.1))
                    p = [v0+perp*0.1+h, v1+perp*0.1+h, v1+perp*0.3+h, v0+perp*0.3+h]
                    cb_bme.faces.new([cb_bme.verts.new(x) for x in p])
                if cb_bme.faces:
                    _bm.ops.recalc_face_normals(cb_bme, faces=cb_bme.faces[:])
                    cb_m = bpy.data.meshes.new(f"Curb_{base}")
                    cb_bme.to_mesh(cb_m); cb_m.update(); cb_m.materials.append(mat_curb)
                    cb_o = bpy.data.objects.new(f"Curb_{base}", cb_m)
                    cb_o["street_detail"] = "curb"
                    _link(cb_o); objects_created += 1
                cb_bme.free()

            except Exception:
                pass

        return {"objects_created": objects_created, "roads_processed": len(road_objs)}

    # ── add_vegetation ────────────────────────────────────────────────────────

    def add_vegetation(self, density=0.5):
        """Place trees along road edges as simple LOD meshes."""
        import bmesh as _bm
        import random
        import math

        scene = bpy.context.scene
        rng = random.Random(42)
        trees_created = 0

        # ---- materials -------------------------------------------------------
        def _get_or_create_mat_nodes(name, setup_fn):
            if name in bpy.data.materials:
                return bpy.data.materials[name]
            mat = bpy.data.materials.new(name)
            mat.use_nodes = True
            mat.node_tree.nodes.clear()
            setup_fn(mat)
            return mat

        def _setup_trunk(mat):
            nt = mat.node_tree
            out  = nt.nodes.new("ShaderNodeOutputMaterial"); out.location  = (400, 0)
            bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled"); bsdf.location = (200, 0)
            bsdf.inputs["Base Color"].default_value = (0.18, 0.10, 0.06, 1.0)
            bsdf.inputs["Roughness"].default_value  = 0.9
            nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

        def _setup_canopy(mat):
            nt = mat.node_tree
            out  = nt.nodes.new("ShaderNodeOutputMaterial"); out.location = (700, 0)
            bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled"); bsdf.location = (400, 0)
            bsdf.inputs["Roughness"].default_value     = 0.85
            if "Subsurface Weight" in bsdf.inputs:
                bsdf.inputs["Subsurface Weight"].default_value = 0.3
            elif "Subsurface" in bsdf.inputs:
                bsdf.inputs["Subsurface"].default_value = 0.3
            bsdf.inputs["Subsurface Color"].default_value = (0.15, 0.50, 0.08, 1.0)

            noise = nt.nodes.new("ShaderNodeTexNoise"); noise.location = (-300, 0)
            noise.inputs["Scale"].default_value  = 6.0
            noise.inputs["Detail"].default_value = 4.0

            mix = nt.nodes.new("ShaderNodeMixRGB"); mix.location = (100, 0)
            mix.blend_type = 'MIX'
            mix.inputs["Color1"].default_value = (0.10, 0.40, 0.05, 1.0)
            mix.inputs["Color2"].default_value = (0.20, 0.55, 0.10, 1.0)

            nt.links.new(noise.outputs["Fac"],   mix.inputs["Fac"])
            nt.links.new(mix.outputs["Color"],   bsdf.inputs["Base Color"])
            nt.links.new(bsdf.outputs["BSDF"],   out.inputs["Surface"])

        mat_trunk  = _get_or_create_mat_nodes("mat_tree_trunk",  _setup_trunk)
        mat_canopy = _get_or_create_mat_nodes("mat_tree_canopy", _setup_canopy)

        # Collect road objects
        road_objs = [o for o in scene.objects
                     if o.type == 'MESH' and o.get("osm_layer") == "roads"]

        # Apply density filter
        selected_roads = [r for r in road_objs if rng.random() < density]

        for road_obj in selected_roads:
            mesh = road_obj.data
            bme = _bm.new()
            bme.from_mesh(mesh)
            bme.transform(road_obj.matrix_world)
            bme.edges.ensure_lookup_table()
            bme.verts.ensure_lookup_table()

            # Sample edge midpoints as candidate tree positions
            edge_points = []
            for edge in bme.edges:
                v0 = edge.verts[0].co.copy()
                v1 = edge.verts[1].co.copy()
                seg_len = (v1 - v0).length
                # Space trees every 8-12 m
                spacing = rng.uniform(8.0, 12.0)
                t = 0.0
                while t < seg_len:
                    frac = t / seg_len if seg_len > 0 else 0
                    pos  = v0.lerp(v1, frac)
                    edge_dir = (v1 - v0)
                    if edge_dir.length > 0.01:
                        edge_dir.normalize()
                    perp = mathutils.Vector((-edge_dir.y, edge_dir.x, 0.0))
                    # Offset tree ±1 m from road edge
                    side_offset = 2.5 + rng.uniform(-1.0, 1.0)
                    pos += perp * side_offset
                    pos.z = 0.0
                    edge_points.append(pos)
                    t += spacing
            bme.free()

            # Create one tree at each candidate position
            for pos in edge_points:
                # Trunk
                trunk_h   = 4.0
                trunk_r   = 0.3
                bme_t = _bm.new()
                _bm.ops.create_cone(bme_t, cap_ends=True, cap_tris=False,
                                    segments=8, radius1=trunk_r, radius2=trunk_r * 0.6,
                                    depth=trunk_h)
                t_mesh = bpy.data.meshes.new(f"Tree_trunk_{trees_created}")
                bme_t.to_mesh(t_mesh); bme_t.free(); t_mesh.update()
                t_obj = bpy.data.objects.new(f"Tree_trunk_{trees_created}", t_mesh)
                t_obj.location = pos + mathutils.Vector((0, 0, trunk_h / 2))
                scene.collection.objects.link(t_obj)
                t_mesh.materials.append(mat_trunk)
                t_obj["vegetation"] = "trunk"

                # Canopy (icosphere)
                canopy_scale = rng.uniform(3.0, 6.0)
                bme_c = _bm.new()
                _bm.ops.create_icosphere(bme_c, subdivisions=2, radius=canopy_scale * 0.5)
                c_mesh = bpy.data.meshes.new(f"Tree_canopy_{trees_created}")
                bme_c.to_mesh(c_mesh); bme_c.free(); c_mesh.update()
                c_obj = bpy.data.objects.new(f"Tree_canopy_{trees_created}", c_mesh)
                c_obj.location = pos + mathutils.Vector((0, 0, trunk_h + canopy_scale * 0.4))
                # Random scale variation
                s = rng.uniform(0.85, 1.15)
                c_obj.scale = (s, s, rng.uniform(0.9, 1.1))
                scene.collection.objects.link(c_obj)
                c_mesh.materials.append(mat_canopy)
                c_obj["vegetation"] = "canopy"

                trees_created += 1

        return {
            "trees_created": trees_created,
            "roads_sampled": len(selected_roads),
            "total_roads": len(road_objs),
        }

    # ── add_ground_detail ─────────────────────────────────────────────────────

    def add_ground_detail(self):
        """Replace flat ground with layered zone materials and special plaza handling."""
        import bmesh as _bm
        import math

        scene = bpy.context.scene
        objects_created = 0

        # ---- helper to build or retrieve a material -------------------------
        def _mat(name, base_color, roughness=0.85, normal_strength=0.0):
            if name in bpy.data.materials:
                return bpy.data.materials[name]
            mat = bpy.data.materials.new(name)
            mat.use_nodes = True
            nt = mat.node_tree
            nt.nodes.clear()
            out  = nt.nodes.new("ShaderNodeOutputMaterial"); out.location  = (600, 0)
            bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled"); bsdf.location = (300, 0)
            bsdf.inputs["Base Color"].default_value = (*base_color, 1.0)
            bsdf.inputs["Roughness"].default_value  = roughness
            if normal_strength > 0.0:
                noise = nt.nodes.new("ShaderNodeTexNoise"); noise.location = (-300, -150)
                noise.inputs["Scale"].default_value = 40.0
                bump  = nt.nodes.new("ShaderNodeBump");    bump.location  = (0, -150)
                bump.inputs["Strength"].default_value = normal_strength
                nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
                nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
            nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
            return mat

        mat_asphalt   = _mat("mat_ground_asphalt",   (0.07, 0.07, 0.07), roughness=0.95, normal_strength=0.15)
        mat_pavement  = _mat("mat_ground_pavement",  (0.62, 0.60, 0.57), roughness=0.80)
        mat_grass     = _mat("mat_ground_grass",     (0.10, 0.38, 0.07), roughness=0.95)
        mat_plaza_std = _mat("mat_ground_plaza_std", (0.72, 0.70, 0.66), roughness=0.55)

        # ---- Special stone-tile material for Plaça Catalunya ----------------
        def _mat_plaza_catalonia():
            name = "mat_plaza_catalonia"
            if name in bpy.data.materials:
                return bpy.data.materials[name]
            mat = bpy.data.materials.new(name)
            mat.use_nodes = True
            nt = mat.node_tree
            nt.nodes.clear()

            out  = nt.nodes.new("ShaderNodeOutputMaterial"); out.location  = (800, 0)
            bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled"); bsdf.location = (500, 0)
            bsdf.inputs["Roughness"].default_value = 0.45

            # Radial UV mapping via Geometry → Separate XYZ → atan2
            geo   = nt.nodes.new("ShaderNodeNewGeometry");  geo.location  = (-700, 0)
            sep   = nt.nodes.new("ShaderNodeSeparateXYZ");  sep.location  = (-500, 0)
            atan2 = nt.nodes.new("ShaderNodeMath");         atan2.location = (-300, 0)
            atan2.operation = 'ARCTAN2'

            combine = nt.nodes.new("ShaderNodeCombineXYZ"); combine.location = (-100, 0)
            combine.inputs["Z"].default_value = 0.0

            wave = nt.nodes.new("ShaderNodeTexWave"); wave.location = (100, 0)
            wave.wave_type = 'RINGS'
            wave.inputs["Scale"].default_value      = 2.5
            wave.inputs["Distortion"].default_value = 0.3

            mix = nt.nodes.new("ShaderNodeMixRGB"); mix.location = (300, 0)
            mix.inputs["Color1"].default_value = (0.78, 0.76, 0.72, 1.0)
            mix.inputs["Color2"].default_value = (0.65, 0.63, 0.59, 1.0)

            nt.links.new(geo.outputs["Position"],      sep.inputs["Vector"])
            nt.links.new(sep.outputs["X"],             atan2.inputs[0])
            nt.links.new(sep.outputs["Y"],             atan2.inputs[1])
            nt.links.new(atan2.outputs["Value"],       combine.inputs["X"])
            nt.links.new(combine.outputs["Vector"],    wave.inputs["Vector"])
            nt.links.new(wave.outputs["Color"],        mix.inputs["Fac"])
            nt.links.new(mix.outputs["Color"],         bsdf.inputs["Base Color"])
            nt.links.new(bsdf.outputs["BSDF"],         out.inputs["Surface"])
            return mat

        # Process all objects and assign ground zone materials
        for obj in scene.objects:
            if obj.type != "MESH":
                continue

            osm_layer   = obj.get("osm_layer", "")
            osm_leisure = str(obj.get("osm_leisure", "")).lower()
            osm_name    = str(obj.get("osm_name", "")).lower()
            osm_surface = str(obj.get("osm_surface", "")).lower()
            osm_landuse = str(obj.get("osm_landuse", "")).lower()
            osm_highway = str(obj.get("osm_highway", "")).lower()

            mat = None

            if osm_layer == "roads" or osm_highway in ("footway", "path", "pedestrian"):
                if osm_highway in ("footway", "path"):
                    mat = mat_pavement
                else:
                    mat = mat_asphalt
            elif osm_layer == "parks" or osm_landuse == "grass" or osm_leisure == "park":
                mat = mat_grass
            elif osm_leisure in ("plaza", "square") or osm_landuse in ("plaza", "square"):
                # Check for Plaça Catalunya
                if "catalunya" in osm_name or "cataluña" in osm_name:
                    mat = _mat_plaza_catalonia()
                else:
                    mat = mat_plaza_std
            elif osm_layer == "" and obj.name.lower() in ("groundplane", "ground_plane"):
                # The fallback ground plane from render_viewport
                mat = mat_asphalt

            # Also detect Catalunya by name fallback
            if mat is None and ("catalunya" in osm_name or "cataluña" in osm_name):
                mat = _mat_plaza_catalonia()

            if mat is not None:
                if not obj.material_slots:
                    obj.data.materials.append(mat)
                else:
                    obj.material_slots[0].material = mat
                objects_created += 1

        # Ensure the GroundPlane (created by render_viewport) gets asphalt
        gp = scene.objects.get("GroundPlane")
        if gp and gp.type == "MESH":
            if not gp.material_slots:
                gp.data.materials.append(mat_asphalt)
            else:
                gp.material_slots[0].material = mat_asphalt

        return {"objects_updated": objects_created}

    # ── add_facade_textures ───────────────────────────────────────────────────

    def add_facade_textures(self):
        """UV-project building footprints, add window frames, floor bands, age-based style."""
        import bmesh as _bm
        import math

        scene = bpy.context.scene
        processed = 0
        skipped = []

        # ── material factories keyed by era ──────────────────────────────────
        def _era_from_obj(obj):
            raw = str(obj.get("osm_start_date", obj.get("osm_construction_date", "")))
            # strip non-numeric prefix/suffix; take first 4-digit run
            import re as _re
            m = _re.search(r'\d{4}', raw)
            if m:
                try:
                    return int(m.group())
                except ValueError:
                    pass
            return None  # unknown

        def _get_or_build_mat(name, build_fn):
            if name in bpy.data.materials:
                return bpy.data.materials[name]
            mat = bpy.data.materials.new(name)
            mat.use_nodes = True
            mat.node_tree.nodes.clear()
            build_fn(mat)
            return mat

        def _build_stone(mat):
            nt = mat.node_tree
            out  = nt.nodes.new("ShaderNodeOutputMaterial"); out.location  = (600,0)
            bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled"); bsdf.location = (300,0)
            bsdf.inputs["Base Color"].default_value = (0.78, 0.74, 0.66, 1.0)
            bsdf.inputs["Roughness"].default_value  = 0.80
            # Voronoi for carved-stone look
            vor = nt.nodes.new("ShaderNodeTexVoronoi"); vor.location = (-200,0)
            vor.inputs["Scale"].default_value = 12.0
            bump = nt.nodes.new("ShaderNodeBump"); bump.location = (0,-200)
            bump.inputs["Strength"].default_value = 0.3
            nt.links.new(vor.outputs["Distance"], bump.inputs["Height"])
            nt.links.new(bump.outputs["Normal"],  bsdf.inputs["Normal"])
            nt.links.new(bsdf.outputs["BSDF"],    out.inputs["Surface"])

        def _build_brutalist(mat):
            nt = mat.node_tree
            out  = nt.nodes.new("ShaderNodeOutputMaterial"); out.location  = (600,0)
            bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled"); bsdf.location = (300,0)
            bsdf.inputs["Base Color"].default_value = (0.48, 0.47, 0.45, 1.0)
            bsdf.inputs["Roughness"].default_value  = 0.92
            # ShaderNodeTexMusgrave removed in Blender 4.x; use Noise instead
            noise = nt.nodes.new("ShaderNodeTexNoise"); noise.location = (-300, 0)
            noise.inputs["Scale"].default_value  = 30.0
            noise.inputs["Detail"].default_value = 6.0
            mr  = nt.nodes.new("ShaderNodeMapRange"); mr.location = (-100,0)
            mr.inputs["To Min"].default_value = 0.80
            mr.inputs["To Max"].default_value = 0.98
            nt.links.new(noise.outputs["Fac"],     mr.inputs["Value"])
            nt.links.new(mr.outputs["Result"],     bsdf.inputs["Roughness"])
            nt.links.new(bsdf.outputs["BSDF"],     out.inputs["Surface"])

        def _build_modern(mat):
            nt = mat.node_tree
            out  = nt.nodes.new("ShaderNodeOutputMaterial"); out.location  = (600,0)
            bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled"); bsdf.location = (300,0)
            bsdf.inputs["Base Color"].default_value = (0.65, 0.78, 0.88, 1.0)
            bsdf.inputs["Roughness"].default_value  = 0.05
            bsdf.inputs["Metallic"].default_value   = 0.10
            if "Transmission Weight" in bsdf.inputs:
                bsdf.inputs["Transmission Weight"].default_value = 0.6
            elif "Transmission" in bsdf.inputs:
                bsdf.inputs["Transmission"].default_value = 0.6
            fresnel = nt.nodes.new("ShaderNodeFresnel"); fresnel.location = (-200, -150)
            fresnel.inputs["IOR"].default_value = 1.52
            nt.links.new(fresnel.outputs["Fac"], bsdf.inputs["Roughness"])
            nt.links.new(bsdf.outputs["BSDF"],   out.inputs["Surface"])

        def _build_frame_mat(mat):
            nt = mat.node_tree
            out  = nt.nodes.new("ShaderNodeOutputMaterial"); out.location  = (400,0)
            bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled"); bsdf.location = (200,0)
            bsdf.inputs["Base Color"].default_value = (0.10, 0.10, 0.11, 1.0)
            bsdf.inputs["Roughness"].default_value  = 0.30
            bsdf.inputs["Metallic"].default_value   = 0.80
            nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

        def _build_band_mat(mat):
            nt = mat.node_tree
            out  = nt.nodes.new("ShaderNodeOutputMaterial"); out.location  = (400,0)
            bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled"); bsdf.location = (200,0)
            bsdf.inputs["Base Color"].default_value = (0.55, 0.53, 0.50, 1.0)
            bsdf.inputs["Roughness"].default_value  = 0.70
            nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

        mat_frame = _get_or_build_mat("mat_window_frame",   _build_frame_mat)
        mat_band  = _get_or_build_mat("mat_floor_band",     _build_band_mat)

        buildings = [o for o in scene.objects
                     if o.type == "MESH" and o.get("osm_layer") == "buildings"]

        for obj in buildings:
            try:
                mesh = obj.data
                era  = _era_from_obj(obj)

                # ── Pick era material ─────────────────────────────────────────
                if era is not None and era < 1940:
                    mat_name = f"mat_facade_stone_{obj.name}"
                    era_build = _build_stone
                elif era is not None and era <= 1980:
                    mat_name = f"mat_facade_brutalist_{obj.name}"
                    era_build = _build_brutalist
                else:
                    mat_name = f"mat_facade_modern_{obj.name}"
                    era_build = _build_modern

                mat_facade = _get_or_build_mat(mat_name, era_build)

                # Ensure two material slots: 0=facade, 1=window-frame, 2=band
                while len(mesh.materials) < 3:
                    mesh.materials.append(None)
                mesh.materials[0] = mat_facade
                mesh.materials[1] = mat_frame
                mesh.materials[2] = mat_band

                # ── UV: project footprint coords onto facade faces ────────────
                # Use world-space XY of each face center as UV, normalised by
                # building bbox so UVs are 0-1 within the footprint.
                if not mesh.uv_layers:
                    mesh.uv_layers.new(name="UVMap")
                uv_layer = mesh.uv_layers.active
                _bb_raw = self._get_aabb(obj)
                # _get_aabb returns [min_list, max_list]; normalise to dict
                if isinstance(_bb_raw, list):
                    bb = {"min": _bb_raw[0], "max": _bb_raw[1]}
                else:
                    bb = _bb_raw
                bb_min_x = bb["min"][0]; bb_max_x = bb["max"][0]
                bb_min_y = bb["min"][1]; bb_max_y = bb["max"][1]
                bb_min_z = bb["min"][2]; bb_max_z = bb["max"][2]
                span_x = max(bb_max_x - bb_min_x, 0.01)
                span_z = max(bb_max_z - bb_min_z, 0.01)

                for poly in mesh.polygons:
                    world_center = obj.matrix_world @ poly.center
                    for li in poly.loop_indices:
                        wco = obj.matrix_world @ mesh.vertices[mesh.loops[li].vertex_index].co
                        # Facade faces (side): U=horiz world-pos, V=height
                        if abs(poly.normal.z) < 0.3:
                            u = (wco.x - bb_min_x) / span_x
                            v = (wco.z - bb_min_z) / span_z
                        else:
                            # Top/bottom: U=X, V=Y
                            bb_sy = max(bb_max_y - bb_min_y, 0.01)
                            u = (wco.x - bb_min_x) / span_x
                            v = (wco.y - bb["min"][1]) / bb_sy
                        uv_layer.data[li].uv = (u, v)

                # ── Window frames and floor bands via bmesh ───────────────────
                bme = _bm.new()
                bme.from_mesh(mesh)
                bme.verts.ensure_lookup_table()
                bme.edges.ensure_lookup_table()
                bme.faces.ensure_lookup_table()

                # Assign material indices
                # Side faces that look like window insets (small, roughly square) → frame mat
                zmax = max((v.co.z for v in bme.verts), default=0)
                floor_h = 3.0

                for f in bme.faces:
                    if abs(f.normal.z) < 0.3:  # side face
                        area = f.calc_area()
                        cz   = f.calc_center_median().z
                        # Window insets: small area side faces
                        if 0.05 < area < 3.0:
                            f.material_index = 1  # window frame
                        # Floor-band faces: near floor cut heights
                        elif area > 0.0:
                            floor_idx = round(cz / floor_h)
                            band_z    = floor_idx * floor_h
                            if abs(cz - band_z) < 0.12 and area < 1.5:
                                f.material_index = 2  # floor band
                            else:
                                f.material_index = 0  # facade
                    else:
                        f.material_index = 0  # top/bottom → facade

                # Extrude floor-band faces outward by 0.1 m
                band_faces = [f for f in bme.faces if f.material_index == 2]
                if band_faces:
                    ext = _bm.ops.extrude_face_region(bme, geom=band_faces)
                    ext_verts = [e for e in ext["geom"] if isinstance(e, _bm.types.BMVert)]
                    # Translate in the face normal direction
                    for v in ext_verts:
                        # Average normals of linked faces
                        avg_n = mathutils.Vector((0, 0, 0))
                        for lf in v.link_faces:
                            if abs(lf.normal.z) < 0.3:
                                avg_n += lf.normal
                        if avg_n.length > 0.01:
                            avg_n.normalize()
                            v.co += avg_n * 0.1

                _bm.ops.recalc_face_normals(bme, faces=bme.faces[:])
                bme.to_mesh(mesh)
                bme.free()
                mesh.update()
                processed += 1

            except Exception as exc:
                skipped.append({"object": obj.name, "error": str(exc)})

        return {
            "processed": processed,
            "skipped_count": len(skipped),
            "skipped": skipped[:10],
        }

    # ── add_ambient_occlusion ─────────────────────────────────────────────────

    def add_ambient_occlusion(self):
        """Bake AO into vertex colours and wire a VertexColor × BaseColor multiply into all materials."""
        import math

        scene  = bpy.context.scene
        render = scene.render
        ao_attr = "Col"  # vertex colour attribute name

        # We need Cycles for baking
        prev_engine = render.engine
        render.engine = "CYCLES"
        scene.cycles.samples = 32

        mesh_objs = [o for o in scene.objects if o.type == "MESH"]
        baked_count = 0
        skipped = []

        for obj in mesh_objs:
            try:
                mesh = obj.data

                # Add / reuse vertex colour attribute
                if ao_attr not in mesh.color_attributes:
                    mesh.color_attributes.new(name=ao_attr, type='FLOAT_COLOR', domain='CORNER')

                # Select only this object for baking
                bpy.ops.object.select_all(action='DESELECT')
                bpy.context.view_layer.objects.active = obj
                obj.select_set(True)

                # Bake AO
                bpy.ops.object.bake(
                    type='AO',
                    use_selected_to_active=False,
                    target='VERTEX_COLORS',
                    save_mode='INTERNAL',
                )
                baked_count += 1
            except Exception as exc:
                skipped.append({"object": obj.name, "error": str(exc)})

        # Restore engine
        render.engine = prev_engine

        # ── Wire vertex colour × base colour into all materials ───────────────
        wired = 0
        AO_FACTOR = 0.7

        for mat in bpy.data.materials:
            if not mat.use_nodes:
                continue
            nt = mat.node_tree

            # Find Principled BSDF (if any)
            pbsdf = next(
                (n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"),
                None,
            )
            if pbsdf is None:
                continue

            # Check if AO node already wired
            already = any(
                n.type == "ATTRIBUTE" and n.attribute_name == ao_attr
                for n in nt.nodes
            )
            if already:
                continue

            # Get the current Base Color input link
            base_in = pbsdf.inputs["Base Color"]

            # Add nodes
            ao_node  = nt.nodes.new("ShaderNodeAttribute");   ao_node.attribute_name = ao_attr
            ao_node.location = (pbsdf.location.x - 450, pbsdf.location.y - 200)

            mul_node = nt.nodes.new("ShaderNodeMixRGB")
            mul_node.blend_type = 'MULTIPLY'
            mul_node.inputs["Fac"].default_value = AO_FACTOR
            mul_node.location = (pbsdf.location.x - 220, pbsdf.location.y - 100)

            # Preserve existing base colour link or default value
            if base_in.links:
                prev_link = base_in.links[0]
                nt.links.new(prev_link.from_socket,    mul_node.inputs["Color1"])
                nt.links.remove(prev_link)
            else:
                mul_node.inputs["Color1"].default_value = base_in.default_value

            nt.links.new(ao_node.outputs["Color"],     mul_node.inputs["Color2"])
            nt.links.new(mul_node.outputs["Color"],    base_in)
            wired += 1

        return {
            "baked_count": baked_count,
            "materials_wired": wired,
            "skipped_count": len(skipped),
            "skipped": skipped[:10],
        }

    # ── add_road_geometry ─────────────────────────────────────────────────────

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
            elevation_deg = -10.0  # sun below horizon = no direct light
            sun_color     = (0.05, 0.05, 0.15, 1.0)
            sun_strength  = 0.0
            bg_sky.inputs["Color"].default_value    = (0.02, 0.03, 0.10, 1.0)
            bg_sky.inputs["Strength"].default_value = 0.05
        else:  # golden_hour (default)
            elevation_deg = 8.0
            sun_color     = (1.00, 0.85, 0.60, 1.0)
            sun_strength  = 3.0
            bg_sky.inputs["Color"].default_value    = (0.50, 0.55, 0.80, 1.0)
            bg_sky.inputs["Strength"].default_value = 0.45

        bg_sun.inputs["Color"].default_value    = sun_color
        bg_sun.inputs["Strength"].default_value = sun_strength

        # ── Sun lamp ─────────────────────────────────────────────────────────
        if sun_strength > 0.01:
            origin_lon = scene.get("geo_origin_lon", 0.0)
            sun_data = bpy.data.lights.new("CityLightSun", type='SUN')
            sun_data.energy = sun_strength
            sun_data.color  = sun_color[:3]
            sun_data.angle  = math.radians(0.53)
            sun_obj = bpy.data.objects.new("CityLightSun", sun_data)
            sun_obj["city_light"] = True
            scene.collection.objects.link(sun_obj)
            sun_obj.rotation_euler = (
                math.radians(90.0 - elevation_deg),
                0.0,
                math.radians(origin_lon % 360),
            )
            lights_added += 1

        # ── Night-mode extras ─────────────────────────────────────────────────
        if tod == "night":
            rng = random.Random(7)

            road_objs = [o for o in scene.objects
                         if o.type == "MESH" and o.get("osm_layer") in ("roads",)]

            # Street lamps every 20 m along road edges
            lamp_positions = []
            for road_obj in road_objs:
                mesh = road_obj.data
                for edge in mesh.edges:
                    v0 = road_obj.matrix_world @ mesh.vertices[edge.vertices[0]].co
                    v1 = road_obj.matrix_world @ mesh.vertices[edge.vertices[1]].co
                    seg_len = (v1 - v0).length
                    t = 0.0
                    while t < seg_len:
                        frac = t / seg_len if seg_len > 0 else 0
                        pos  = v0.lerp(v1, frac)
                        pos.z = 5.5  # lamp height
                        lamp_positions.append(pos.copy())
                        t += 20.0

            for pos in lamp_positions:
                ld = bpy.data.lights.new("StreetLamp", type='POINT')
                ld.energy       = 100.0
                ld.color        = (1.0, 0.88, 0.60)  # 2700 K warm
                ld.shadow_soft_size = 0.3
                lo = bpy.data.objects.new("StreetLamp", ld)
                lo["city_light"] = True
                lo.location = pos
                scene.collection.objects.link(lo)
                lights_added += 1

            # Lit windows: emission on 30% of window-frame material faces
            # We add a per-material emit variant rather than modifying geometry
            window_mats = [m for m in bpy.data.materials
                           if "window_frame" in m.name.lower() or "glass" in m.name.lower()]
            lit_mats = 0
            for mat in window_mats:
                if not mat.use_nodes:
                    continue
                # Add a night-emission variant if not already present
                night_name = f"{mat.name}_night"
                if night_name in bpy.data.materials:
                    continue
                night_mat = bpy.data.materials.new(night_name)
                night_mat.use_nodes = True
                nnt = night_mat.node_tree; nnt.nodes.clear()
                nout = nnt.nodes.new("ShaderNodeOutputMaterial"); nout.location = (400,0)
                nem  = nnt.nodes.new("ShaderNodeEmission");       nem.location  = (200,0)
                # Warm interior light colour
                nem.inputs["Color"].default_value    = (1.0, 0.90, 0.70, 1.0)
                nem.inputs["Strength"].default_value = 2.0
                nnt.links.new(nem.outputs["Emission"], nout.inputs["Surface"])
                lit_mats += 1

        return {
            "time_of_day": tod,
            "lights_added": lights_added,
        }

    # ── generate_facade_geometry ─────────────────────────────────────────────

    def generate_facade_geometry(self, object_name=None):
        """
        Full procedural facade geometry system — real 3D relief vertices.

        For each building (filtered by footprint area and wall-face count):
          1. Identify vertical wall panels grouped by floor level.
          2. Cut real window openings, add sill ledges and frame reveals.
          3. Add balconies on south-facing residential facades every 2nd floor.
          4. Add era-specific architectural ornament (pilasters/cornice/
             brise-soleil/curtain-wall grid/setback/rooftop box).
          5. Add rooftop parapet + programme-specific rooftop elements.
          6. Assign named material slots to every geometry element.
        """
        import bmesh as _bm
        import math
        import random
        import re as _re

        scene  = bpy.context.scene
        rng    = random.Random(12345)

        # ── performance gates ─────────────────────────────────────────────────
        AREA_SKIP      = 1000.0   # m²  — keep as LOD0
        MIN_WALL_FACES = 4

        # ── floor / window geometry constants ────────────────────────────────
        FLOOR_H        = 3.0      # m per floor
        WIN_W_RES      = 0.9      # residential window width
        WIN_H_RES      = 1.4      # residential window height
        WIN_SPACING    = 2.5      # centre-to-centre spacing
        WIN_REVEAL     = 0.12     # inward extrusion for wall thickness reveal
        SILL_OUT       = 0.06     # sill protrusion outward
        SILL_H         = 0.10     # sill height
        BAL_DEPTH      = 0.90     # balcony slab depth
        BAL_THICK      = 0.15     # balcony slab thickness
        RAIL_H         = 1.00     # railing height
        RAIL_SPACING   = 0.15     # vertical bar spacing
        RAIL_R         = 0.02     # bar radius

        # ── shared material registry ──────────────────────────────────────────
        _mat_cache: dict = {}

        def _mat(name: str, build_fn):
            if name in _mat_cache:
                return _mat_cache[name]
            if name in bpy.data.materials:
                m = bpy.data.materials[name]
            else:
                m = bpy.data.materials.new(name)
                m.use_nodes = True
                m.node_tree.nodes.clear()
                build_fn(m)
            _mat_cache[name] = m
            return m

        def _pbsdf(mat, base_color, roughness=0.8, metallic=0.0,
                   transmission=0.0, alpha=1.0):
            nt = mat.node_tree
            out  = nt.nodes.new("ShaderNodeOutputMaterial"); out.location  = (400, 0)
            bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled"); bsdf.location = (100, 0)
            bsdf.inputs["Base Color"].default_value = (*base_color, 1.0)
            bsdf.inputs["Roughness"].default_value  = roughness
            bsdf.inputs["Metallic"].default_value   = metallic
            for key in ("Transmission Weight", "Transmission"):
                if key in bsdf.inputs:
                    bsdf.inputs[key].default_value = transmission
                    break
            bsdf.inputs["Alpha"].default_value = alpha
            nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
            return bsdf

        def _mat_wall_stone(m):
            bsdf = _pbsdf(m, (0.76, 0.72, 0.64), roughness=0.80)
            nt = m.node_tree
            vor = nt.nodes.new("ShaderNodeTexVoronoi"); vor.location = (-300, 0)
            vor.inputs["Scale"].default_value = 10.0
            bump = nt.nodes.new("ShaderNodeBump"); bump.location = (-100, -200)
            bump.inputs["Strength"].default_value = 0.25
            nt.links.new(vor.outputs["Distance"], bump.inputs["Height"])
            nt.links.new(bump.outputs["Normal"],  bsdf.inputs["Normal"])

        def _mat_wall_brick(m):
            bsdf = _pbsdf(m, (0.60, 0.28, 0.18), roughness=0.90)
            nt = m.node_tree
            noise = nt.nodes.new("ShaderNodeTexNoise"); noise.location = (-300, 0)
            noise.inputs["Scale"].default_value = 60.0
            bump  = nt.nodes.new("ShaderNodeBump");   bump.location  = (-100, -200)
            bump.inputs["Strength"].default_value = 0.20
            nt.links.new(noise.outputs["Fac"],   bump.inputs["Height"])
            nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

        def _mat_wall_concrete(m):
            bsdf = _pbsdf(m, (0.50, 0.48, 0.46), roughness=0.92)
            nt = m.node_tree
            mus = nt.nodes.new("ShaderNodeTexNoise"); mus.location = (-300, 0)
            mus.inputs["Scale"].default_value = 25.0
            mus.inputs["Detail"].default_value = 6.0
            mr  = nt.nodes.new("ShaderNodeMapRange");   mr.location  = (-100, 0)
            mr.inputs["To Min"].default_value = 0.82
            mr.inputs["To Max"].default_value = 0.96
            nt.links.new(mus.outputs["Fac"],       mr.inputs["Value"])
            nt.links.new(mr.outputs["Result"],     bsdf.inputs["Roughness"])

        def _mat_wall_glass_curtain(m):
            bsdf = _pbsdf(m, (0.60, 0.75, 0.88), roughness=0.04,
                          metallic=0.05, transmission=0.75)

        def _mat_window_glass(m):
            bsdf = _pbsdf(m, (0.55, 0.70, 0.85), roughness=0.02, transmission=0.90)
            m.blend_method = "BLEND"

        def _mat_window_frame_alu(m):
            _pbsdf(m, (0.12, 0.12, 0.13), roughness=0.20, metallic=0.90)

        def _mat_balcony_concrete(m):
            _pbsdf(m, (0.58, 0.56, 0.54), roughness=0.85)

        def _mat_balcony_railing(m):
            _pbsdf(m, (0.18, 0.18, 0.20), roughness=0.15, metallic=0.95)

        def _mat_cornice_stone(m):
            _pbsdf(m, (0.82, 0.78, 0.70), roughness=0.75)

        def _mat_roof_gravel(m):
            bsdf = _pbsdf(m, (0.42, 0.40, 0.37), roughness=0.97)
            nt = m.node_tree
            mus = nt.nodes.new("ShaderNodeTexNoise"); mus.location = (-300, 0)
            mus.inputs["Scale"].default_value = 40.0
            mus.inputs["Detail"].default_value = 4.0
            nt.links.new(mus.outputs["Fac"], bsdf.inputs["Roughness"])

        def _mat_brise_soleil(m):
            _pbsdf(m, (0.30, 0.30, 0.32), roughness=0.30, metallic=0.70)

        # Pre-build the shared materials once
        MAT_WALL_STONE   = _mat("facade_wall_stone",         _mat_wall_stone)
        MAT_WALL_BRICK   = _mat("facade_wall_brick",         _mat_wall_brick)
        MAT_WALL_CONC    = _mat("facade_wall_concrete",      _mat_wall_concrete)
        MAT_WALL_CURTAIN = _mat("facade_wall_glass_curtain", _mat_wall_glass_curtain)
        MAT_WIN_GLASS    = _mat("facade_window_glass",       _mat_window_glass)
        MAT_WIN_FRAME    = _mat("facade_window_frame_aluminium", _mat_window_frame_alu)
        MAT_BAL_CONC     = _mat("facade_balcony_concrete",   _mat_balcony_concrete)
        MAT_BAL_RAIL     = _mat("facade_balcony_railing",    _mat_balcony_railing)
        MAT_CORNICE      = _mat("facade_cornice_stone",      _mat_cornice_stone)
        MAT_ROOF_GRAVEL  = _mat("facade_roof_gravel",        _mat_roof_gravel)
        MAT_BRISE        = _mat("facade_brise_soleil",       _mat_brise_soleil)

        # ── helpers: child mesh creation ──────────────────────────────────────

        def _child_obj(name, verts, faces, mat, parent_obj):
            """Create a mesh child object from raw vert/face lists."""
            m = bpy.data.meshes.new(name)
            m.from_pydata([v.to_tuple() if hasattr(v, 'to_tuple') else tuple(v)
                           for v in verts], [], faces)
            m.update()
            m.materials.append(mat)
            o = bpy.data.objects.new(name, m)
            o["facade_child"] = True
            scene.collection.objects.link(o)
            o.parent = parent_obj
            o.matrix_parent_inverse = parent_obj.matrix_world.inverted()
            return o

        def _cylinder_verts(center, radius, height, segments=8):
            """Return (verts, faces) for a vertical cylinder in world space."""
            verts = []
            faces = []
            for i in range(segments):
                a = 2 * math.pi * i / segments
                verts.append(mathutils.Vector((center.x + math.cos(a)*radius,
                                               center.y + math.sin(a)*radius,
                                               center.z)))
                verts.append(mathutils.Vector((center.x + math.cos(a)*radius,
                                               center.y + math.sin(a)*radius,
                                               center.z + height)))
            for i in range(segments):
                n  = (i + 1) % segments
                b0 = i * 2;  b1 = b0 + 1
                b2 = n * 2;  b3 = b2 + 1
                faces.append([b0, b2, b3, b1])
            # bottom / top caps
            faces.append(list(range(0, segments*2, 2)))
            faces.append(list(range(1, segments*2, 2))[::-1])
            return verts, faces

        def _box_verts(origin, sx, sy, sz):
            """Return (verts, faces) for an axis-aligned box."""
            x, y, z = origin.x, origin.y, origin.z
            v = [
                mathutils.Vector((x,    y,    z   )),
                mathutils.Vector((x+sx, y,    z   )),
                mathutils.Vector((x+sx, y+sy, z   )),
                mathutils.Vector((x,    y+sy, z   )),
                mathutils.Vector((x,    y,    z+sz)),
                mathutils.Vector((x+sx, y,    z+sz)),
                mathutils.Vector((x+sx, y+sy, z+sz)),
                mathutils.Vector((x,    y+sy, z+sz)),
            ]
            f = [
                [0,1,2,3],[4,7,6,5],
                [0,4,5,1],[1,5,6,2],
                [2,6,7,3],[3,7,4,0],
            ]
            return v, f

        # ── era detection ─────────────────────────────────────────────────────

        def _era(obj):
            raw = str(obj.get("osm_start_date",
                      obj.get("osm_construction_date", "")))
            hit = _re.search(r'\d{4}', raw)
            if hit:
                try:
                    return int(hit.group())
                except ValueError:
                    pass
            return None   # unknown → default to contemporary

        # ── footprint area (local-space shoelace) ─────────────────────────────

        def _footprint_area(mesh):
            bot = [v.co for v in mesh.vertices if abs(v.co.z) < 0.2]
            if len(bot) < 3:
                return 0.0
            xs = [v.x for v in bot]; ys = [v.y for v in bot]
            n  = len(xs)
            return abs(sum(xs[i]*ys[(i+1)%n] - xs[(i+1)%n]*ys[i]
                           for i in range(n)) / 2.0)

        # ── building use type ─────────────────────────────────────────────────

        def _use(obj):
            btype = str(obj.get("osm_building", "yes")).lower()
            levels = obj.get("osm_building:levels", obj.get("osm_levels", None))
            if btype in ("commercial","retail","shop"):  return "commercial"
            if btype in ("office","government"):         return "office"
            if btype in ("house","residential","apartments","flat"): return "residential"
            if btype in ("industrial","warehouse","garage"): return "industrial"
            return "residential"   # default

        # ═══════════════════════════════════════════════════════════════════════
        # PER-BUILDING PROCESSING
        # ═══════════════════════════════════════════════════════════════════════

        if object_name:
            targets = [bpy.data.objects.get(object_name)]
            if targets[0] is None:
                return {"error": f"Object '{object_name}' not found"}
        else:
            targets = [o for o in scene.objects
                       if o.type == "MESH" and o.get("osm_layer") == "buildings"]

        reports = []
        total_windows   = 0
        total_balconies = 0

        for obj in targets:
            if obj is None or obj.type != "MESH":
                continue

            rep = {
                "object":            obj.name,
                "faces_before":      0,
                "faces_after":       0,
                "style":             "unknown",
                "windows_created":   0,
                "balconies_created": 0,
                "errors":            [],
            }

            try:
                mesh = obj.data
                rep["faces_before"] = len(mesh.polygons)

                # ── performance gates ─────────────────────────────────────────
                area = _footprint_area(mesh)
                if area > AREA_SKIP:
                    rep["errors"].append(f"skipped: footprint {area:.0f}m² > {AREA_SKIP}m²")
                    reports.append(rep)
                    continue

                year = _era(obj)
                use  = _use(obj)

                if year is not None and year < 1940:
                    style = "pre1940"
                elif year is not None and year <= 1980:
                    style = "brutalist"
                else:
                    style = "contemporary"
                rep["style"] = style

                # Pick wall material for this era
                if style == "pre1940":
                    wall_mat = MAT_WALL_STONE
                elif style == "brutalist":
                    wall_mat = MAT_WALL_CONC
                else:
                    if use == "office":
                        wall_mat = MAT_WALL_CURTAIN
                    else:
                        wall_mat = MAT_WALL_BRICK

                # Ensure enough material slots on the building mesh
                while len(mesh.materials) < 7:
                    mesh.materials.append(None)
                mesh.materials[0] = wall_mat
                mesh.materials[1] = MAT_WIN_GLASS
                mesh.materials[2] = MAT_WIN_FRAME
                mesh.materials[3] = MAT_BAL_CONC
                mesh.materials[4] = MAT_CORNICE
                mesh.materials[5] = MAT_ROOF_GRAVEL
                mesh.materials[6] = MAT_BRISE

                # Building world-space bounding box
                bb     = self._get_aabb(obj)   # [[min],[max]]
                bb_min = mathutils.Vector(bb[0])
                bb_max = mathutils.Vector(bb[1])
                height = bb_max.z - bb_min.z
                n_floors = max(1, int(round(height / FLOOR_H)))

                # ── STEP 1: identify vertical wall faces ──────────────────────
                #
                # We work in world space throughout so offsets are in metres.
                # bmesh is loaded from the mesh, transformed to world space.
                bme = _bm.new()
                bme.from_mesh(mesh)
                bme.transform(obj.matrix_world)
                bme.verts.ensure_lookup_table()
                bme.edges.ensure_lookup_table()
                bme.faces.ensure_lookup_table()

                # Group vertical faces by floor index
                # floor_idx = int((face_center.z - bb_min.z) / FLOOR_H)
                wall_faces_by_floor: dict = {}
                for f in bme.faces:
                    if abs(f.normal.z) >= 0.15:
                        continue   # skip horizontal faces
                    cz    = f.calc_center_median().z
                    fidx  = max(0, int((cz - bb_min.z) / FLOOR_H))
                    wall_faces_by_floor.setdefault(fidx, []).append(f)

                # Quick gate: need at least MIN_WALL_FACES vertical faces
                total_wall = sum(len(v) for v in wall_faces_by_floor.values())
                if total_wall < MIN_WALL_FACES:
                    rep["errors"].append(
                        f"skipped: only {total_wall} wall faces found")
                    bme.free()
                    reports.append(rep)
                    continue

                # ── STEP 2: window openings ───────────────────────────────────
                #
                # For each sufficiently wide wall panel we:
                #   a) Inset the panel's inner rect to create frame border
                #   b) Extrude the inner (window) face inward to make a reveal
                #   c) Assign window-glass mat index to the inset face
                #   d) Add a separate sill mesh as a child object
                #
                # We avoid actual hole-cutting because it requires manifold
                # geometry and triggers unstable bmesh boolean ops.  Instead we
                # inset+extrude which gives the same visual depth and is robust
                # on OSM building meshes that are often non-manifold.

                windows_this = 0

                for floor_idx, faces in wall_faces_by_floor.items():
                    floor_z     = bb_min.z + floor_idx * FLOOR_H
                    floor_top_z = floor_z + FLOOR_H

                    for wf in faces:
                        # Skip faces that are too small for a window
                        area_face = wf.calc_area()
                        if area_face < 1.5:
                            continue

                        # Estimate panel width from the face's bounding extent
                        # in the dominant horizontal direction
                        cx  = wf.calc_center_median()
                        nrm = wf.normal.normalized()
                        # Tangent: rotate normal 90° around Z
                        tang = mathutils.Vector((-nrm.y, nrm.x, 0.0)).normalized()
                        proj = [tang.dot(v.co) for v in wf.verts]
                        panel_w = max(proj) - min(proj) if proj else 0.0
                        panel_h = max(v.co.z for v in wf.verts) - \
                                  min(v.co.z for v in wf.verts)

                        if panel_w < 1.5:
                            continue

                        # Determine window count and dimensions
                        if use == "commercial" and floor_idx == 0:
                            # Shopfront: one wide window 80% panel width
                            wins = [(panel_w * 0.80, panel_h * 0.75)]
                        elif use == "office":
                            # Ribbon window: 70% width, 0.8m tall
                            wins = [(panel_w * 0.70, 0.80)]
                        else:
                            # Residential: evenly spaced 0.9m wide windows
                            n_wins = max(1, int(panel_w / WIN_SPACING))
                            wins = [(WIN_W_RES, WIN_H_RES)] * n_wins

                        # For each window: inset a sub-face from the wall face
                        for (ww, wh) in wins:
                            # Inset thickness = half of (panel_w - ww) / n_wins
                            horiz_margin = max(0.05, (panel_w - ww) / (2 * len(wins)))
                            vert_margin  = max(0.05, (panel_h - wh) / 2.0)
                            thickness    = min(horiz_margin, vert_margin, 0.4)

                            try:
                                res = _bm.ops.inset_individual(
                                    bme,
                                    faces=[wf],
                                    thickness=thickness,
                                    depth=0.0,
                                )
                                inner_faces = res.get("faces", [])
                                if inner_faces:
                                    inner = inner_faces[0]
                                    inner.material_index = 1  # window glass

                                    # Reveal: extrude inner face inward
                                    ext = _bm.ops.extrude_face_region(
                                        bme, geom=[inner])
                                    ext_verts = [e for e in ext["geom"]
                                                 if isinstance(e, _bm.types.BMVert)]
                                    _bm.ops.translate(
                                        bme,
                                        vec=-nrm * WIN_REVEAL,
                                        verts=ext_verts,
                                    )
                                    # Assign frame mat to the border ring faces
                                    for bf in bme.faces:
                                        if bf.material_index == 0 and \
                                           bf != wf and abs(bf.normal.z) < 0.3:
                                            # Heuristic: very small side faces
                                            # created by the inset
                                            if bf.calc_area() < 0.5:
                                                bf.material_index = 2

                                    windows_this += 1

                                    # Sill: child mesh ledge below window
                                    sill_center = mathutils.Vector((
                                        cx.x - nrm.x * 0.001,
                                        cx.y - nrm.y * 0.001,
                                        cx.z - wh / 2.0 - SILL_H,
                                    ))
                                    sill_w   = ww + 0.10
                                    sill_pos = sill_center + tang * (-sill_w / 2.0)
                                    sv = [
                                        sill_pos,
                                        sill_pos + tang * sill_w,
                                        sill_pos + tang * sill_w + nrm * (-SILL_OUT),
                                        sill_pos                  + nrm * (-SILL_OUT),
                                        sill_pos                  + mathutils.Vector((0,0,SILL_H)),
                                        sill_pos + tang * sill_w  + mathutils.Vector((0,0,SILL_H)),
                                        sill_pos + tang * sill_w  + nrm*(-SILL_OUT) + mathutils.Vector((0,0,SILL_H)),
                                        sill_pos                  + nrm*(-SILL_OUT) + mathutils.Vector((0,0,SILL_H)),
                                    ]
                                    sf = [[0,1,2,3],[4,7,6,5],
                                          [0,4,5,1],[1,5,6,2],
                                          [2,6,7,3],[3,7,4,0]]
                                    _child_obj(
                                        f"Sill_{obj.name}_{windows_this}",
                                        sv, sf, MAT_WIN_FRAME, obj)
                            except Exception as we:
                                rep["errors"].append(f"window err f{floor_idx}: {we}")

                rep["windows_created"] = windows_this
                total_windows += windows_this

                # ── STEP 3: balconies (residential, south-facing, every 2nd floor) ──

                balconies_this = 0

                if use in ("residential", "apartments", "house"):
                    for floor_idx, faces in wall_faces_by_floor.items():
                        if floor_idx == 0:
                            continue        # no ground-floor balconies
                        if floor_idx % 2 != 0:
                            continue        # only even floors

                        for wf in faces:
                            nrm = wf.normal.normalized()
                            # South-facing: normal.y < -0.3 in Blender (Y is north)
                            if nrm.y > -0.3:
                                continue

                            panel_w  = wf.calc_area() ** 0.5   # rough width
                            cx       = wf.calc_center_median()
                            tang     = mathutils.Vector((-nrm.y, nrm.x, 0.0)).normalized()
                            proj     = [tang.dot(v.co) for v in wf.verts]
                            actual_w = (max(proj) - min(proj)) if proj else panel_w
                            bal_w    = max(1.2, min(actual_w - 0.2, 3.5))
                            bal_z    = cx.z - FLOOR_H / 2.0 + 0.1

                            # Slab: box extruded outward from face
                            slab_origin = mathutils.Vector((
                                cx.x - tang.x * bal_w / 2.0,
                                cx.y - tang.y * bal_w / 2.0,
                                bal_z,
                            ))
                            # Slab mesh: sweep outward along -normal
                            sv = [
                                slab_origin,
                                slab_origin + tang * bal_w,
                                slab_origin + tang * bal_w - nrm * BAL_DEPTH,
                                slab_origin               - nrm * BAL_DEPTH,
                                slab_origin               + mathutils.Vector((0,0,BAL_THICK)),
                                slab_origin + tang*bal_w  + mathutils.Vector((0,0,BAL_THICK)),
                                slab_origin + tang*bal_w - nrm*BAL_DEPTH + mathutils.Vector((0,0,BAL_THICK)),
                                slab_origin             - nrm*BAL_DEPTH  + mathutils.Vector((0,0,BAL_THICK)),
                            ]
                            sf = [[0,1,2,3],[4,7,6,5],
                                  [0,4,5,1],[1,5,6,2],
                                  [2,6,7,3],[3,7,4,0]]
                            _child_obj(
                                f"Bal_slab_{obj.name}_{balconies_this}",
                                sv, sf, MAT_BAL_CONC, obj)

                            # Railings: vertical bars every RAIL_SPACING
                            rng_local = rng
                            n_bars = max(2, int(bal_w / RAIL_SPACING))
                            bar_verts_all = []
                            bar_faces_all = []
                            vi_base = 0
                            for bi in range(n_bars + 1):
                                t_frac = bi / max(n_bars, 1)
                                bar_x  = slab_origin.x + tang.x * t_frac * bal_w
                                bar_y  = slab_origin.y + tang.y * t_frac * bal_w
                                bar_z  = bal_z + BAL_THICK
                                # Offset slightly outward from wall
                                bar_c  = mathutils.Vector((bar_x, bar_y, bar_z))
                                bar_c -= nrm * (BAL_DEPTH * 0.95)
                                bv, bf = _cylinder_verts(bar_c, RAIL_R, RAIL_H, 6)
                                bf_off = [[idx + vi_base for idx in face] for face in bf]
                                bar_verts_all.extend(bv)
                                bar_faces_all.extend(bf_off)
                                vi_base += len(bv)
                            if bar_verts_all:
                                _child_obj(
                                    f"Bal_railing_{obj.name}_{balconies_this}",
                                    bar_verts_all, bar_faces_all,
                                    MAT_BAL_RAIL, obj)

                            # Top rail: thin horizontal box connecting bar tops
                            rail_top_z = bal_z + BAL_THICK + RAIL_H - 0.04
                            tr_origin  = slab_origin.copy()
                            tr_origin.z = rail_top_z
                            tr_origin  -= nrm * (BAL_DEPTH * 0.95)
                            trv = [
                                tr_origin,
                                tr_origin + tang * bal_w,
                                tr_origin + tang * bal_w + mathutils.Vector((0,0,0.04)),
                                tr_origin               + mathutils.Vector((0,0,0.04)),
                            ]
                            # Extrude 0.04m in normal direction for thickness
                            trv += [v - nrm * 0.04 for v in trv]
                            trf = [[0,1,2,3],[4,7,6,5],
                                   [0,4,5,1],[1,5,6,2],
                                   [2,6,7,3],[3,7,4,0]]
                            _child_obj(
                                f"Bal_toprail_{obj.name}_{balconies_this}",
                                trv, trf, MAT_BAL_RAIL, obj)

                            balconies_this += 1

                rep["balconies_created"] = balconies_this
                total_balconies += balconies_this

                # ── STEP 4: architectural details by era ──────────────────────

                if style == "pre1940":
                    # Pilasters: vertical strips 0.15m proud, 0.3m wide, every 3-4m
                    for floor_idx, faces in wall_faces_by_floor.items():
                        for wf in faces:
                            nrm  = wf.normal.normalized()
                            tang = mathutils.Vector((-nrm.y, nrm.x, 0.0)).normalized()
                            proj = [tang.dot(v.co) for v in wf.verts]
                            if not proj:
                                continue
                            pw   = max(proj) - min(proj)
                            if pw < 3.0:
                                continue
                            cz   = wf.calc_center_median().z
                            cx   = wf.calc_center_median()
                            spacing = rng.uniform(3.0, 4.0)
                            n_pil = max(1, int(pw / spacing))
                            for pi in range(n_pil):
                                t = (pi + 0.5) / n_pil
                                px = cx.x + tang.x * (min(proj) + t * pw - sum(proj)/len(proj))
                                py = cx.y + tang.y * (min(proj) + t * pw - sum(proj)/len(proj))
                                # Pilaster as thin box
                                pil_origin = mathutils.Vector((
                                    px - tang.x * 0.15,
                                    py - tang.y * 0.15,
                                    cz - FLOOR_H / 2.0,
                                ))
                                pv, pf = _box_verts(
                                    pil_origin - nrm * 0.15,
                                    tang.x * 0.30 if abs(tang.x) > 0.01 else 0.30,
                                    tang.y * 0.30 if abs(tang.y) > 0.01 else 0.30,
                                    FLOOR_H,
                                )
                                _child_obj(
                                    f"Pilaster_{obj.name}_{floor_idx}_{pi}",
                                    pv, pf, MAT_WALL_STONE, obj)

                    # Cornice: stepped top ledge at roof level
                    top_faces = [f for f in bme.faces if f.normal.z > 0.85]
                    if top_faces:
                        for step in range(3):
                            step_h   = 0.10
                            step_out = 0.12 * (step + 1)
                            try:
                                ext = _bm.ops.extrude_face_region(
                                    bme, geom=top_faces)
                                ext_v = [e for e in ext["geom"]
                                         if isinstance(e, _bm.types.BMVert)]
                                _bm.ops.translate(bme,
                                    vec=mathutils.Vector((0, 0, step_h)),
                                    verts=ext_v)
                                bme.faces.ensure_lookup_table()
                                # outset new ring
                                new_side = [f for f in bme.faces
                                            if abs(f.normal.z) < 0.3
                                            and f.calc_center_median().z > (
                                                bb_max.z + step * step_h - 0.2)]
                                if new_side:
                                    _bm.ops.extrude_face_region(bme, geom=new_side)
                                    bme.faces.ensure_lookup_table()
                                top_faces = [f for f in bme.faces
                                             if f.normal.z > 0.85
                                             and f.calc_center_median().z > (
                                                 bb_max.z + step * step_h - 0.05)]
                                for cf in bme.faces:
                                    if cf.calc_center_median().z > bb_max.z - 0.5:
                                        cf.material_index = 4  # cornice mat
                            except Exception as ce:
                                rep["errors"].append(f"cornice step {step}: {ce}")
                                break

                elif style == "brutalist":
                    # Brise-soleil fins: horizontal shelves above windows
                    for floor_idx, faces in wall_faces_by_floor.items():
                        if floor_idx == 0:
                            continue
                        for wf in faces:
                            if wf.calc_area() < 2.0:
                                continue
                            nrm   = wf.normal.normalized()
                            tang  = mathutils.Vector((-nrm.y, nrm.x, 0.0)).normalized()
                            proj  = [tang.dot(v.co) for v in wf.verts]
                            if not proj:
                                continue
                            pw    = max(proj) - min(proj)
                            cz    = wf.calc_center_median().z
                            cx_pt = wf.calc_center_median()
                            # Fin: 0.3m deep, 0.08m thick, at top of window area
                            fin_z  = cz + WIN_H_RES / 2.0 + 0.05
                            left   = cx_pt + tang * (-pw / 2.0)
                            right  = cx_pt + tang * ( pw / 2.0)
                            fv = [
                                left,  right,
                                right - nrm * 0.30, left - nrm * 0.30,
                                left  + mathutils.Vector((0, 0, 0.08)),
                                right + mathutils.Vector((0, 0, 0.08)),
                                right - nrm * 0.30 + mathutils.Vector((0, 0, 0.08)),
                                left  - nrm * 0.30 + mathutils.Vector((0, 0, 0.08)),
                            ]
                            fv2 = [v.copy() for v in fv]
                            for v in fv2:
                                v.z = fin_z + (v.z - left.z)
                            ff = [[0,1,2,3],[4,7,6,5],
                                  [0,4,5,1],[1,5,6,2],
                                  [2,6,7,3],[3,7,4,0]]
                            _child_obj(
                                f"Fin_{obj.name}_{floor_idx}",
                                fv2, ff, MAT_BRISE, obj)

                    # Flat roof parapet: 0.4m tall wall ring around roofline
                    try:
                        top_z = bb_max.z
                        par_faces = [f for f in bme.faces if f.normal.z > 0.85
                                     and abs(f.calc_center_median().z - top_z) < 0.5]
                        if par_faces:
                            ext = _bm.ops.extrude_face_region(bme, geom=par_faces)
                            ext_v = [e for e in ext["geom"]
                                     if isinstance(e, _bm.types.BMVert)]
                            _bm.ops.translate(bme,
                                vec=mathutils.Vector((0, 0, 0.4)),
                                verts=ext_v)
                            for f in bme.faces:
                                if f.normal.z > 0.85 and \
                                   f.calc_center_median().z > top_z + 0.1:
                                    f.material_index = 5  # roof gravel
                    except Exception as pe:
                        rep["errors"].append(f"parapet: {pe}")

                else:  # contemporary
                    # Setback: top 20% stepped back 0.5m
                    setback_z = bb_min.z + height * 0.80
                    try:
                        top_verts = [v for v in bme.verts if v.co.z > setback_z]
                        if len(top_verts) >= 4:
                            # Push top verts inward toward centroid
                            cx_xy = mathutils.Vector((
                                (bb_min.x + bb_max.x) / 2.0,
                                (bb_min.y + bb_max.y) / 2.0,
                                0.0,
                            ))
                            for v in top_verts:
                                to_centre = (cx_xy - mathutils.Vector(
                                    (v.co.x, v.co.y, 0.0))).normalized()
                                v.co.x += to_centre.x * 0.5
                                v.co.y += to_centre.y * 0.5
                    except Exception as se:
                        rep["errors"].append(f"setback: {se}")

                    # Rooftop mechanical box: 40% footprint, 2m tall
                    fp_w  = (bb_max.x - bb_min.x) * 0.40
                    fp_d  = (bb_max.y - bb_min.y) * 0.40
                    box_x = (bb_min.x + bb_max.x) / 2.0 - fp_w / 2.0
                    box_y = (bb_min.y + bb_max.y) / 2.0 - fp_d / 2.0
                    bxv, bxf = _box_verts(
                        mathutils.Vector((box_x, box_y, bb_max.z)),
                        fp_w, fp_d, 2.0,
                    )
                    _child_obj(
                        f"RoofBox_{obj.name}", bxv, bxf,
                        MAT_WALL_CONC, obj)

                # ── STEP 5: roof details ──────────────────────────────────────

                # Parapet ring (all styles — a low wall around the perimeter)
                try:
                    top_z    = bb_max.z
                    roof_fcs = [f for f in bme.faces if f.normal.z > 0.85
                                and abs(f.calc_center_median().z - top_z) < 0.5]
                    if roof_fcs and style != "brutalist":  # brutalist does own parapet
                        ext = _bm.ops.extrude_face_region(bme, geom=roof_fcs)
                        ext_v = [e for e in ext["geom"]
                                 if isinstance(e, _bm.types.BMVert)]
                        _bm.ops.translate(bme,
                            vec=mathutils.Vector((0, 0, 0.30)),
                            verts=ext_v)
                        for f in bme.faces:
                            if f.normal.z > 0.85 and \
                               f.calc_center_median().z > top_z + 0.1:
                                f.material_index = 5  # roof gravel
                except Exception as rpe:
                    rep["errors"].append(f"roof parapet: {rpe}")

                # Programme-specific rooftop elements
                if use == "residential":
                    # Water tank cylinder at roof corner
                    s = rng.uniform(0.8, 1.2)
                    tank_c = mathutils.Vector((
                        bb_min.x + (bb_max.x - bb_min.x) * 0.15,
                        bb_min.y + (bb_max.y - bb_min.y) * 0.15,
                        bb_max.z + 0.30,
                    ))
                    tv, tf = _cylinder_verts(tank_c, 0.6 * s, 1.2 * s, 12)
                    _child_obj(f"WaterTank_{obj.name}", tv, tf,
                               MAT_WALL_CONC, obj)
                    # TV antenna: thin pole
                    ant_c = mathutils.Vector((
                        bb_max.x - 0.3, bb_max.y - 0.3, bb_max.z + 0.30,
                    ))
                    av, af = _cylinder_verts(ant_c, 0.02, 2.5 * rng.uniform(0.8, 1.2), 4)
                    _child_obj(f"Antenna_{obj.name}", av, af,
                               MAT_BAL_RAIL, obj)

                elif use == "commercial":
                    # AC units: small boxes scattered on roof
                    for ai in range(rng.randint(2, 5)):
                        ax = bb_min.x + rng.uniform(0.5, bb_max.x - bb_min.x - 0.5)
                        ay = bb_min.y + rng.uniform(0.5, bb_max.y - bb_min.y - 0.5)
                        az = bb_max.z + 0.30
                        s  = rng.uniform(0.8, 1.2)
                        acv, acf = _box_verts(
                            mathutils.Vector((ax, ay, az)),
                            1.0*s, 0.6*s, 0.5*s,
                        )
                        _child_obj(f"ACUnit_{obj.name}_{ai}",
                                   acv, acf, MAT_BRISE, obj)

                    # Skylight: flat glass panel
                    sky_x = (bb_min.x + bb_max.x) / 2.0 - 0.75
                    sky_y = (bb_min.y + bb_max.y) / 2.0 - 0.5
                    sky_z = bb_max.z + 0.31
                    skv = [
                        mathutils.Vector((sky_x,      sky_y,      sky_z)),
                        mathutils.Vector((sky_x+1.5,  sky_y,      sky_z)),
                        mathutils.Vector((sky_x+1.5,  sky_y+1.0,  sky_z)),
                        mathutils.Vector((sky_x,      sky_y+1.0,  sky_z)),
                    ]
                    _child_obj(f"Skylight_{obj.name}", skv, [[0,1,2,3]],
                               MAT_WIN_GLASS, obj)

                # ── STEP 6: finalise bmesh → mesh ─────────────────────────────

                _bm.ops.recalc_face_normals(bme, faces=bme.faces[:])
                # Remove zero-area faces
                zero = [f for f in bme.faces if f.calc_area() < 1e-8]
                if zero:
                    _bm.ops.delete(bme, geom=zero, context='FACES')

                # Convert back from world to object-local space
                bme.transform(obj.matrix_world.inverted())
                bme.to_mesh(mesh)
                bme.free()
                mesh.update()

                rep["faces_after"] = len(mesh.polygons)

            except Exception as exc:
                import traceback as _tb
                rep["errors"].append(str(exc))
                rep["errors"].append(_tb.format_exc()[-300:])

            reports.append(rep)

        return {
            "buildings_processed": len(reports),
            "total_windows":       sum(r["windows_created"]   for r in reports),
            "total_balconies":     sum(r["balconies_created"] for r in reports),
            "reports":             reports[:20],  # cap to avoid huge responses
        }

    # ── generate_building_detail ─────────────────────────────────────────────

    def generate_building_detail(self, object_name=None, lod=None):
        """
        Apply LOD-based building detail to one object or all buildings.

        lod=0: simple box (fast, no change to existing geometry)
        lod=1: floor-level loop cuts + window insets
        lod=2: floor cuts + windows + cornice + residential balconies

        If lod is None, it is auto-selected by footprint area:
          area > 500 m²  → lod 0
          100–500 m²     → lod 1
          < 100 m²       → lod 2
        """
        import bmesh as _bm
        import math

        scene = bpy.context.scene

        if object_name:
            targets = [bpy.data.objects.get(object_name)]
            if targets[0] is None:
                return {"error": f"Object '{object_name}' not found"}
        else:
            targets = [o for o in scene.objects
                       if o.type == 'MESH' and o.get("osm_layer") == "buildings"]

        processed = 0
        skipped = []

        for obj in targets:
            try:
                # Determine footprint area from bottom face (z≈0 verts)
                mesh = obj.data
                bot_verts = [v.co for v in mesh.vertices if abs(v.co.z) < 0.1]
                if len(bot_verts) >= 3:
                    # Shoelace formula for polygon area
                    xs = [v.x for v in bot_verts]
                    ys = [v.y for v in bot_verts]
                    n = len(xs)
                    area = abs(sum(xs[i] * ys[(i+1) % n] - xs[(i+1) % n] * ys[i]
                                   for i in range(n)) / 2.0)
                else:
                    area = 0.0

                # Determine LOD
                if lod is not None:
                    effective_lod = int(lod)
                elif area > 500:
                    effective_lod = 0
                elif area > 100:
                    effective_lod = 1
                else:
                    effective_lod = 2

                obj["lod"] = effective_lod

                if effective_lod == 0:
                    # Still clean up normals, zero-area faces, and add UVs
                    bme = _bm.new()
                    bme.from_mesh(mesh)
                    zero = [f for f in bme.faces if f.calc_area() < 1e-6]
                    if zero:
                        _bm.ops.delete(bme, geom=zero, context='FACES')
                    _bm.ops.recalc_face_normals(bme, faces=bme.faces[:])
                    bme.to_mesh(mesh)
                    bme.free()
                    mesh.update()
                    bpy.context.view_layer.objects.active = obj
                    obj.select_set(True)
                    try:
                        bpy.ops.object.mode_set(mode='EDIT')
                        bpy.ops.mesh.select_all(action='SELECT')
                        bpy.ops.uv.smart_project(angle_limit=66.0, island_margin=0.02)
                        bpy.ops.object.mode_set(mode='OBJECT')
                    except Exception:
                        try:
                            bpy.ops.object.mode_set(mode='OBJECT')
                        except Exception:
                            pass
                    obj.select_set(False)
                    processed += 1
                    continue

                # Get building height from existing geometry
                zmax = max((v.co.z for v in mesh.vertices), default=10.0)
                height_m = max(zmax, 3.0)
                floor_h = 3.0
                n_floors = max(1, int(height_m / floor_h))

                bme = _bm.new()
                bme.from_mesh(mesh)
                bme.verts.ensure_lookup_table()
                bme.edges.ensure_lookup_table()
                bme.faces.ensure_lookup_table()

                # Remove any remaining zero-area faces first
                zero = [f for f in bme.faces if f.calc_area() < 1e-6]
                if zero:
                    _bm.ops.delete(bme, geom=zero, context='FACES')
                    bme.faces.ensure_lookup_table()

                # --- Floor loop cuts on vertical (side) faces ---
                side_faces = [f for f in bme.faces
                              if abs(f.normal.z) < 0.3 and f.calc_area() > 0.1]

                for floor_idx in range(1, n_floors):
                    cut_z = floor_idx * floor_h
                    if cut_z >= height_m - 0.1:
                        break
                    # Bisect each side face at this z height
                    geom_in = list(bme.verts) + list(bme.edges) + list(bme.faces)
                    plane_co = mathutils.Vector((0, 0, cut_z))
                    plane_no = mathutils.Vector((0, 0, 1))
                    _bm.ops.bisect_plane(bme, geom=geom_in,
                                         plane_co=plane_co, plane_no=plane_no,
                                         clear_inner=False, clear_outer=False)
                    bme.verts.ensure_lookup_table()
                    bme.edges.ensure_lookup_table()
                    bme.faces.ensure_lookup_table()

                # --- Window insets (lod >= 1) ---
                building_use = str(obj.get("osm_building:use", obj.get("osm_building", "yes"))).lower()
                add_windows = building_use not in ("industrial", "warehouse", "garage")
                large_windows = building_use in ("commercial", "retail", "office")

                if add_windows:
                    bme.faces.ensure_lookup_table()
                    side_panels = [f for f in bme.faces
                                   if abs(f.normal.z) < 0.3
                                   and f.calc_area() > 0.5]
                    if side_panels:
                        thickness = 0.8 if large_windows else 0.5
                        depth = 0.15
                        inset_result = _bm.ops.inset_individual(
                            bme, faces=side_panels,
                            thickness=thickness, depth=depth)

                # --- Cornice / ledge at rooftop (lod >= 2) ---
                if effective_lod >= 2:
                    bme.faces.ensure_lookup_table()
                    top_faces = [f for f in bme.faces
                                 if f.normal.z > 0.9
                                 and abs(f.calc_center_median().z - height_m) < 0.5]
                    if top_faces:
                        # Extrude top faces outward slightly
                        ext = _bm.ops.extrude_face_region(bme, geom=top_faces)
                        ext_verts = [e for e in ext["geom"] if isinstance(e, _bm.types.BMVert)]
                        _bm.ops.translate(bme, vec=(0, 0, 0.3), verts=ext_verts)
                        # Outset the cornice ring
                        bme.faces.ensure_lookup_table()
                        cornice_faces = [f for f in bme.faces
                                         if abs(f.normal.z) < 0.3
                                         and f.calc_center_median().z > height_m - 0.1]
                        if cornice_faces:
                            _bm.ops.inset_region(bme, faces=cornice_faces,
                                                thickness=-0.3, depth=0.0)

                    # --- Balconies on residential buildings (lod 2 only) ---
                    if building_use in ("residential", "apartments", "house", "yes"):
                        bme.faces.ensure_lookup_table()
                        balcony_candidates = [f for f in bme.faces
                                              if abs(f.normal.z) < 0.3
                                              and f.calc_area() > 1.5
                                              and 2.5 < f.calc_center_median().z < height_m - 1.0]
                        # Inset to create balcony slab on every other floor panel
                        step = max(1, len(balcony_candidates) // max(n_floors, 1))
                        balcony_faces = balcony_candidates[::step * 2]
                        if balcony_faces:
                            _bm.ops.inset_individual(bme, faces=balcony_faces,
                                                thickness=0.4, depth=-0.6)

                # Final cleanup
                _bm.ops.recalc_face_normals(bme, faces=bme.faces[:])
                zero2 = [f for f in bme.faces if f.calc_area() < 1e-8]
                if zero2:
                    _bm.ops.delete(bme, geom=zero2, context='FACES')
                bme.to_mesh(mesh)
                bme.free()
                mesh.update()

                # Re-unwrap UV
                bpy.context.view_layer.objects.active = obj
                obj.select_set(True)
                try:
                    bpy.ops.object.mode_set(mode='EDIT')
                    bpy.ops.mesh.select_all(action='SELECT')
                    bpy.ops.uv.smart_project(angle_limit=66.0, island_margin=0.02)
                    bpy.ops.object.mode_set(mode='OBJECT')
                except Exception:
                    try:
                        bpy.ops.object.mode_set(mode='OBJECT')
                    except Exception:
                        pass
                obj.select_set(False)

                processed += 1

            except Exception as exc:
                skipped.append({"object": obj.name if obj else "?", "error": str(exc)})

        return {
            "processed": processed,
            "skipped_count": len(skipped),
            "skipped": skipped[:10],
        }

    # ── set_render_settings ───────────────────────────────────────────────────

    def set_render_settings(self):
        """Configure Cycles render settings and sky/sun lighting."""
        import math

        scene = bpy.context.scene
        render = scene.render
        cycles = scene.cycles

        # Engine + samples
        render.engine = 'CYCLES'
        cycles.samples = 256
        cycles.use_denoising = True
        render.resolution_x = 1920
        render.resolution_y = 1080
        scene.view_settings.view_transform = 'Filmic'
        scene.view_settings.look = 'High Contrast'
        scene.view_settings.exposure = 0.5

        # World sky texture
        world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
        scene.world = world
        world.use_nodes = True
        nt = world.node_tree
        nt.nodes.clear()

        out = nt.nodes.new("ShaderNodeOutputWorld")
        out.location = (400, 0)
        bg = nt.nodes.new("ShaderNodeBackground")
        bg.location = (200, 0)
        sky = nt.nodes.new("ShaderNodeTexSky")
        sky.location = (0, 0)
        sky.sky_type = 'HOSEK_WILKIE'
        sky.sun_elevation = math.radians(25)

        # Sun rotation follows geo_origin longitude
        origin_lon = scene.get("geo_origin_lon", 0.0)
        sky.sun_rotation = math.radians(origin_lon % 360)

        nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
        nt.links.new(bg.outputs["Background"], out.inputs["Surface"])

        # Sun lamp
        sun_name = "CitySceneSun"
        if sun_name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[sun_name], do_unlink=True)
        sun_data = bpy.data.lights.new(name=sun_name, type='SUN')
        sun_data.energy = 5.0
        sun_data.angle = math.radians(0.5)
        sun_obj = bpy.data.objects.new(sun_name, sun_data)
        scene.collection.objects.link(sun_obj)
        sun_obj.rotation_euler = (
            math.radians(65),
            0.0,
            math.radians(origin_lon % 360),
        )

        return {
            "engine": "CYCLES",
            "samples": 256,
            "denoising": True,
            "sky_type": "NISHITA",
            "sun_elevation_deg": 25,
            "sun_rotation_deg": round(origin_lon % 360, 2),
            "exposure": 0.5,
            "color_management": "Filmic / High Contrast",
        }

    # ── render_viewport ───────────────────────────────────────────────────────

    def render_viewport(self, output_path, camera_preset="isometric"):
        """Render the scene to a PNG file using a preset camera."""
        import math
        import os
        import time as _time

        scene = bpy.context.scene

        # Compute scene bounding box
        all_objs = [o for o in scene.objects if o.type == 'MESH']
        if not all_objs:
            return {"error": "No mesh objects in scene"}

        xs, ys, zs = [], [], []
        for o in all_objs:
            for v in o.data.vertices:
                wco = o.matrix_world @ v.co
                xs.append(wco.x); ys.append(wco.y); zs.append(wco.z)

        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        max_z = max(zs)
        cx = (min_x + max_x) / 2
        cy = (min_y + max_y) / 2
        span_x = max_x - min_x
        span_y = max_y - min_y

        # Remove any previous render camera
        cam_name = "RenderCam"
        if cam_name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[cam_name], do_unlink=True)
        if cam_name in bpy.data.cameras:
            bpy.data.cameras.remove(bpy.data.cameras[cam_name])

        cam_data = bpy.data.cameras.new(cam_name)
        cam_obj = bpy.data.objects.new(cam_name, cam_data)
        scene.collection.objects.link(cam_obj)

        if camera_preset == "street_level":
            cam_data.type = 'PERSP'
            cam_data.lens = 50.0
            # Find a road axis: use first road object with ≥2 verts
            roads_col = bpy.data.collections.get("roads")
            road_dir = mathutils.Vector((1, 0, 0))
            if roads_col and roads_col.objects:
                road_obj = roads_col.objects[0]
                if road_obj.data.vertices and len(road_obj.data.vertices) >= 2:
                    v0 = road_obj.matrix_world @ road_obj.data.vertices[0].co
                    v1 = road_obj.matrix_world @ road_obj.data.vertices[1].co
                    d = v1 - v0
                    if d.length > 0.01:
                        road_dir = d.normalized()
            cam_obj.location = mathutils.Vector((cx, cy, 1.8))
            cam_obj.rotation_euler = (
                math.radians(90), 0, math.atan2(road_dir.x, road_dir.y)
            )

        elif camera_preset == "aerial":
            cam_data.type = 'ORTHO'
            cam_data.ortho_scale = max(span_x, span_y) * 1.1
            alt = max(max_z + 500, 500)
            cam_obj.location = mathutils.Vector((cx, cy, alt))
            cam_obj.rotation_euler = (0, 0, 0)

        else:  # isometric (default)
            cam_data.type = 'PERSP'
            cam_data.lens = 85.0
            diag = math.sqrt(span_x ** 2 + span_y ** 2)
            # Place camera at a reliable angle that always frames all buildings
            cam_obj.location = mathutils.Vector((
                cx + diag * 0.6,
                cy - diag * 0.6,
                diag * 0.7,
            ))

        # Track-to constraint pointing at scene centre for all presets
        # (street_level uses explicit euler instead)
        if camera_preset != "street_level":
            tgt_name = "SceneCentreTarget"
            if tgt_name in bpy.data.objects:
                bpy.data.objects.remove(bpy.data.objects[tgt_name], do_unlink=True)
            tgt = bpy.data.objects.new(tgt_name, None)
            # Point at a slightly elevated centre so buildings fill lower half of frame
            tgt.location = mathutils.Vector((cx, cy, max_z * 0.3))
            scene.collection.objects.link(tgt)
            tc = cam_obj.constraints.new('TRACK_TO')
            tc.track_axis = 'TRACK_NEGATIVE_Z'
            tc.up_axis    = 'UP_Y'
            tc.target     = tgt
            bpy.context.view_layer.update()

        # Ground plane (grey, 2× bbox size) — create/replace
        gname = "GroundPlane"
        if gname in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[gname], do_unlink=True)
        if gname in bpy.data.meshes:
            bpy.data.meshes.remove(bpy.data.meshes[gname])
        hx = span_x; hy = span_y
        gm = bpy.data.meshes.new(gname)
        gm.from_pydata([
            (cx - hx, cy - hy, -0.05), (cx + hx, cy - hy, -0.05),
            (cx + hx, cy + hy, -0.05), (cx - hx, cy + hy, -0.05),
        ], [], [[0, 1, 2, 3]])
        gm.update()
        go = bpy.data.objects.new(gname, gm)
        scene.collection.objects.link(go)
        gmat = bpy.data.materials.get("mat_ground") or bpy.data.materials.new("mat_ground")
        gmat.use_nodes = True
        gmat.node_tree.nodes.clear()
        gout  = gmat.node_tree.nodes.new("ShaderNodeOutputMaterial")
        gbsdf = gmat.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
        gbsdf.inputs["Base Color"].default_value = (0.35, 0.35, 0.33, 1.0)
        gbsdf.inputs["Roughness"].default_value  = 0.95
        gmat.node_tree.links.new(gbsdf.outputs["BSDF"], gout.inputs["Surface"])
        gm.materials.append(gmat)

        scene.camera = cam_obj

        # Output settings
        render = scene.render
        render.filepath = output_path
        render.image_settings.file_format = 'PNG'
        render.image_settings.color_mode = 'RGBA'

        t0 = _time.time()
        bpy.ops.render.render(write_still=True)
        render_time = round(_time.time() - t0, 2)

        file_size_mb = 0.0
        if os.path.exists(output_path):
            file_size_mb = round(os.path.getsize(output_path) / 1_048_576, 3)

        return {
            "output_path": output_path,
            "camera_preset": camera_preset,
            "render_time_s": render_time,
            "file_size_mb": file_size_mb,
        }

    #endregion

# Blender Addon Preferences
class BLENDERMCP_AddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__
    
    telemetry_consent: BoolProperty(
        name="Allow Telemetry",
        description="Allow collection of prompts, code snippets, and screenshots to help improve Blender MCP",
        default=True
    )

    def draw(self, context):
        layout = self.layout
        
        # Telemetry section
        layout.label(text="Telemetry & Privacy:", icon='PREFERENCES')
        
        box = layout.box()
        row = box.row()
        row.prop(self, "telemetry_consent", text="Allow Telemetry")
        
        # Info text
        box.separator()
        if self.telemetry_consent:
            box.label(text="With consent: We collect anonymized prompts, code, and screenshots.", icon='INFO')
        else:
            box.label(text="Without consent: We only collect minimal anonymous usage data", icon='INFO')
            box.label(text="(tool names, success/failure, duration - no prompts or code).", icon='BLANK1')
        box.separator()
        box.label(text="All data is fully anonymized. You can change this anytime.", icon='CHECKMARK')
        
        # Terms and Conditions link
        box.separator()
        row = box.row()
        row.operator("blendermcp.open_terms", text="View Terms and Conditions", icon='TEXT')

# Blender UI Panel
class BLENDERMCP_PT_Panel(bpy.types.Panel):
    bl_label = "Blender MCP"
    bl_idname = "BLENDERMCP_PT_Panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'BlenderMCP'

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        layout.prop(scene, "blendermcp_port")
        layout.prop(scene, "blendermcp_use_polyhaven", text="Use assets from Poly Haven")

        layout.prop(scene, "blendermcp_use_hyper3d", text="Use Hyper3D Rodin 3D model generation")
        if scene.blendermcp_use_hyper3d:
            layout.prop(scene, "blendermcp_hyper3d_mode", text="Rodin Mode")
            layout.prop(scene, "blendermcp_hyper3d_api_key", text="API Key")
            layout.operator("blendermcp.set_hyper3d_free_trial_api_key", text="Set Free Trial API Key")

        layout.prop(scene, "blendermcp_use_sketchfab", text="Use assets from Sketchfab")
        if scene.blendermcp_use_sketchfab:
            layout.prop(scene, "blendermcp_sketchfab_api_key", text="API Key")

        layout.prop(scene, "blendermcp_use_hunyuan3d", text="Use Tencent Hunyuan 3D model generation")
        if scene.blendermcp_use_hunyuan3d:
            layout.prop(scene, "blendermcp_hunyuan3d_mode", text="Hunyuan3D Mode")
            if scene.blendermcp_hunyuan3d_mode == 'OFFICIAL_API':
                layout.prop(scene, "blendermcp_hunyuan3d_secret_id", text="SecretId")
                layout.prop(scene, "blendermcp_hunyuan3d_secret_key", text="SecretKey")
            if scene.blendermcp_hunyuan3d_mode == 'LOCAL_API':
                layout.prop(scene, "blendermcp_hunyuan3d_api_url", text="API URL")
                layout.prop(scene, "blendermcp_hunyuan3d_octree_resolution", text="Octree Resolution")
                layout.prop(scene, "blendermcp_hunyuan3d_num_inference_steps", text="Number of Inference Steps")
                layout.prop(scene, "blendermcp_hunyuan3d_guidance_scale", text="Guidance Scale")
                layout.prop(scene, "blendermcp_hunyuan3d_texture", text="Generate Texture")
        
        if not scene.blendermcp_server_running:
            layout.operator("blendermcp.start_server", text="Connect to MCP server")
        else:
            layout.operator("blendermcp.stop_server", text="Disconnect from MCP server")
            layout.label(text=f"Running on port {scene.blendermcp_port}")

# Operator to set Hyper3D API Key
class BLENDERMCP_OT_SetFreeTrialHyper3DAPIKey(bpy.types.Operator):
    bl_idname = "blendermcp.set_hyper3d_free_trial_api_key"
    bl_label = "Set Free Trial API Key"

    def execute(self, context):
        context.scene.blendermcp_hyper3d_api_key = RODIN_FREE_TRIAL_KEY
        context.scene.blendermcp_hyper3d_mode = 'MAIN_SITE'
        self.report({'INFO'}, "API Key set successfully!")
        return {'FINISHED'}

# Operator to start the server
class BLENDERMCP_OT_StartServer(bpy.types.Operator):
    bl_idname = "blendermcp.start_server"
    bl_label = "Connect to Claude"
    bl_description = "Start the BlenderMCP server to connect with Claude"

    def execute(self, context):
        scene = context.scene

        # Create a new server instance
        if not hasattr(bpy.types, "blendermcp_server") or not bpy.types.blendermcp_server:
            bpy.types.blendermcp_server = BlenderMCPServer(port=scene.blendermcp_port)

        # Start the server
        bpy.types.blendermcp_server.start()
        scene.blendermcp_server_running = True

        return {'FINISHED'}

# Operator to stop the server
class BLENDERMCP_OT_StopServer(bpy.types.Operator):
    bl_idname = "blendermcp.stop_server"
    bl_label = "Stop the connection to Claude"
    bl_description = "Stop the connection to Claude"

    def execute(self, context):
        scene = context.scene

        # Stop the server if it exists
        if hasattr(bpy.types, "blendermcp_server") and bpy.types.blendermcp_server:
            bpy.types.blendermcp_server.stop()
            del bpy.types.blendermcp_server

        scene.blendermcp_server_running = False

        return {'FINISHED'}

# Operator to open Terms and Conditions
class BLENDERMCP_OT_OpenTerms(bpy.types.Operator):
    bl_idname = "blendermcp.open_terms"
    bl_label = "View Terms and Conditions"
    bl_description = "Open the Terms and Conditions document"

    def execute(self, context):
        # Open the Terms and Conditions on GitHub
        terms_url = "https://github.com/ahujasid/blender-mcp/blob/main/TERMS_AND_CONDITIONS.md"
        try:
            import webbrowser
            webbrowser.open(terms_url)
            self.report({'INFO'}, "Terms and Conditions opened in browser")
        except Exception as e:
            self.report({'ERROR'}, f"Could not open Terms and Conditions: {str(e)}")
        
        return {'FINISHED'}

# Registration functions
def register():
    bpy.types.Scene.blendermcp_port = IntProperty(
        name="Port",
        description="Port for the BlenderMCP server",
        default=9876,
        min=1024,
        max=65535
    )

    bpy.types.Scene.blendermcp_server_running = bpy.props.BoolProperty(
        name="Server Running",
        default=False
    )

    bpy.types.Scene.blendermcp_use_polyhaven = bpy.props.BoolProperty(
        name="Use Poly Haven",
        description="Enable Poly Haven asset integration",
        default=False
    )

    bpy.types.Scene.blendermcp_use_hyper3d = bpy.props.BoolProperty(
        name="Use Hyper3D Rodin",
        description="Enable Hyper3D Rodin generatino integration",
        default=False
    )

    bpy.types.Scene.blendermcp_hyper3d_mode = bpy.props.EnumProperty(
        name="Rodin Mode",
        description="Choose the platform used to call Rodin APIs",
        items=[
            ("MAIN_SITE", "hyper3d.ai", "hyper3d.ai"),
            ("FAL_AI", "fal.ai", "fal.ai"),
        ],
        default="MAIN_SITE"
    )

    bpy.types.Scene.blendermcp_hyper3d_api_key = bpy.props.StringProperty(
        name="Hyper3D API Key",
        subtype="PASSWORD",
        description="API Key provided by Hyper3D",
        default=""
    )

    bpy.types.Scene.blendermcp_use_hunyuan3d = bpy.props.BoolProperty(
        name="Use Hunyuan 3D",
        description="Enable Hunyuan asset integration",
        default=False
    )

    bpy.types.Scene.blendermcp_hunyuan3d_mode = bpy.props.EnumProperty(
        name="Hunyuan3D Mode",
        description="Choose a local or official APIs",
        items=[
            ("LOCAL_API", "local api", "local api"),
            ("OFFICIAL_API", "official api", "official api"),
        ],
        default="LOCAL_API"
    )

    bpy.types.Scene.blendermcp_hunyuan3d_secret_id = bpy.props.StringProperty(
        name="Hunyuan 3D SecretId",
        description="SecretId provided by Hunyuan 3D",
        default=""
    )

    bpy.types.Scene.blendermcp_hunyuan3d_secret_key = bpy.props.StringProperty(
        name="Hunyuan 3D SecretKey",
        subtype="PASSWORD",
        description="SecretKey provided by Hunyuan 3D",
        default=""
    )

    bpy.types.Scene.blendermcp_hunyuan3d_api_url = bpy.props.StringProperty(
        name="API URL",
        description="URL of the Hunyuan 3D API service",
        default="http://localhost:8081"
    )

    bpy.types.Scene.blendermcp_hunyuan3d_octree_resolution = bpy.props.IntProperty(
        name="Octree Resolution",
        description="Octree resolution for the 3D generation",
        default=256,
        min=128,
        max=512,
    )

    bpy.types.Scene.blendermcp_hunyuan3d_num_inference_steps = bpy.props.IntProperty(
        name="Number of Inference Steps",
        description="Number of inference steps for the 3D generation",
        default=20,
        min=20,
        max=50,
    )

    bpy.types.Scene.blendermcp_hunyuan3d_guidance_scale = bpy.props.FloatProperty(
        name="Guidance Scale",
        description="Guidance scale for the 3D generation",
        default=5.5,
        min=1.0,
        max=10.0,
    )

    bpy.types.Scene.blendermcp_hunyuan3d_texture = bpy.props.BoolProperty(
        name="Generate Texture",
        description="Whether to generate texture for the 3D model",
        default=False,
    )
    
    bpy.types.Scene.blendermcp_use_sketchfab = bpy.props.BoolProperty(
        name="Use Sketchfab",
        description="Enable Sketchfab asset integration",
        default=False
    )

    bpy.types.Scene.blendermcp_sketchfab_api_key = bpy.props.StringProperty(
        name="Sketchfab API Key",
        subtype="PASSWORD",
        description="API Key provided by Sketchfab",
        default=""
    )

    # Register preferences class
    bpy.utils.register_class(BLENDERMCP_AddonPreferences)

    bpy.utils.register_class(BLENDERMCP_PT_Panel)
    bpy.utils.register_class(BLENDERMCP_OT_SetFreeTrialHyper3DAPIKey)
    bpy.utils.register_class(BLENDERMCP_OT_StartServer)
    bpy.utils.register_class(BLENDERMCP_OT_StopServer)
    bpy.utils.register_class(BLENDERMCP_OT_OpenTerms)

    print("BlenderMCP addon registered")

def unregister():
    # Stop the server if it's running
    if hasattr(bpy.types, "blendermcp_server") and bpy.types.blendermcp_server:
        bpy.types.blendermcp_server.stop()
        del bpy.types.blendermcp_server

    bpy.utils.unregister_class(BLENDERMCP_PT_Panel)
    bpy.utils.unregister_class(BLENDERMCP_OT_SetFreeTrialHyper3DAPIKey)
    bpy.utils.unregister_class(BLENDERMCP_OT_StartServer)
    bpy.utils.unregister_class(BLENDERMCP_OT_StopServer)
    bpy.utils.unregister_class(BLENDERMCP_OT_OpenTerms)
    bpy.utils.unregister_class(BLENDERMCP_AddonPreferences)

    del bpy.types.Scene.blendermcp_port
    del bpy.types.Scene.blendermcp_server_running
    del bpy.types.Scene.blendermcp_use_polyhaven
    del bpy.types.Scene.blendermcp_use_hyper3d
    del bpy.types.Scene.blendermcp_hyper3d_mode
    del bpy.types.Scene.blendermcp_hyper3d_api_key
    del bpy.types.Scene.blendermcp_use_sketchfab
    del bpy.types.Scene.blendermcp_sketchfab_api_key
    del bpy.types.Scene.blendermcp_use_hunyuan3d
    del bpy.types.Scene.blendermcp_hunyuan3d_mode
    del bpy.types.Scene.blendermcp_hunyuan3d_secret_id
    del bpy.types.Scene.blendermcp_hunyuan3d_secret_key
    del bpy.types.Scene.blendermcp_hunyuan3d_api_url
    del bpy.types.Scene.blendermcp_hunyuan3d_octree_resolution
    del bpy.types.Scene.blendermcp_hunyuan3d_num_inference_steps
    del bpy.types.Scene.blendermcp_hunyuan3d_guidance_scale
    del bpy.types.Scene.blendermcp_hunyuan3d_texture

    print("BlenderMCP addon unregistered")

if __name__ == "__main__":
    register()
