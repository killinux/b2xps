"""
Export Blender model to XPS format on remote Windows machine.
Uses base64 to send script, timer for async execution, polling for status.
"""
import urllib.request
import json
import base64
import time
import sys

SERVER = "https://unclamped-unclamped-afoot.ngrok-free.dev"

EXPORT_SCRIPT = '''
import bpy, bmesh, os, json

blend_dir = os.path.dirname(bpy.data.filepath)
output_dir = os.path.join(blend_dir, "xps_export")
os.makedirs(output_dir, exist_ok=True)
output_file = os.path.join(output_dir, "model.mesh.ascii")
status_file = os.path.join(output_dir, "export_status.json")

def write_status(s):
    with open(status_file, 'w') as f:
        json.dump(s, f)

try:
    write_status({"status": "running", "progress": "init"})

    armature = None
    for obj in bpy.data.objects:
        if obj.type == 'ARMATURE':
            armature = obj
            break

    bones = []
    bone_name_to_idx = {}
    if armature:
        for i, bone in enumerate(armature.data.bones):
            bone_name_to_idx[bone.name] = i
            parent_idx = bone_name_to_idx.get(bone.parent.name, -1) if bone.parent else -1
            pos = armature.matrix_world @ bone.head_local
            bones.append((bone.name, parent_idx, pos))

    mesh_objects = [obj for obj in bpy.data.objects if obj.type == 'MESH' and obj.data.vertices]

    write_status({"status": "running", "progress": f"bones:{len(bones)} meshes:{len(mesh_objects)}"})

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(str(len(bones)) + '\\n')
        for name, pidx, pos in bones:
            f.write(name + '\\n')
            f.write(str(pidx) + '\\n')
            f.write(f"{pos.x:.6f} {pos.y:.6f} {pos.z:.6f}\\n")

        f.write(str(len(mesh_objects)) + '\\n')

        for mi, obj in enumerate(mesh_objects):
            write_status({"status": "running", "progress": f"mesh {mi+1}/{len(mesh_objects)}: {obj.name}"})

            depsgraph = bpy.context.evaluated_depsgraph_get()
            eval_obj = obj.evaluated_get(depsgraph)
            mesh = eval_obj.to_mesh()

            bm = bmesh.new()
            bm.from_mesh(mesh)
            bmesh.ops.triangulate(bm, faces=bm.faces[:])
            bm.to_mesh(mesh)
            bm.free()

            mesh.calc_loop_triangles()
            uv_layers = mesh.uv_layers
            uv_count = max(len(uv_layers), 1)

            textures = []
            if obj.material_slots:
                seen = set()
                for slot in obj.material_slots:
                    mat = slot.material
                    if mat and mat.use_nodes:
                        for node in mat.node_tree.nodes:
                            if node.type == 'TEX_IMAGE' and node.image:
                                fpath = node.image.filepath_from_user()
                                if fpath:
                                    bn = os.path.basename(fpath)
                                    if bn not in seen:
                                        seen.add(bn)
                                        textures.append(bn)
            if not textures:
                textures = ["default.png"]

            f.write(obj.name + '\\n')
            f.write(str(uv_count) + '\\n')
            f.write(str(len(textures)) + '\\n')
            for tex in textures:
                f.write(tex + '\\n')
                f.write('0\\n')

            verts_data = []
            vert_map = {}
            tris = mesh.loop_triangles

            for tri in tris:
                for loop_idx in tri.loops:
                    if loop_idx in vert_map:
                        continue
                    loop = mesh.loops[loop_idx]
                    vert = mesh.vertices[loop.vertex_index]
                    pos = obj.matrix_world @ vert.co

                    if hasattr(mesh, 'corner_normals') and len(mesh.corner_normals) > 0:
                        cn = mesh.corner_normals[loop_idx].vector
                    else:
                        cn = vert.normal
                    normal = (obj.matrix_world.to_3x3() @ cn).normalized()

                    uvs = []
                    for uv_layer in uv_layers:
                        uv = uv_layer.data[loop_idx].uv
                        uvs.append((uv[0], 1.0 - uv[1]))
                    if not uvs:
                        uvs.append((0.0, 0.0))

                    color = (255, 255, 255, 255)
                    if mesh.color_attributes:
                        ca = mesh.color_attributes[0]
                        try:
                            if ca.domain == 'CORNER':
                                c = ca.data[loop_idx].color
                            else:
                                c = ca.data[loop.vertex_index].color
                            color = (int(c[0]*255), int(c[1]*255), int(c[2]*255), int(c[3]*255) if len(c)>3 else 255)
                        except:
                            pass

                    weights = []
                    for vg in vert.groups:
                        if vg.group < len(obj.vertex_groups):
                            gname = obj.vertex_groups[vg.group].name
                            if gname in bone_name_to_idx and vg.weight > 0.0001:
                                weights.append((bone_name_to_idx[gname], vg.weight))
                    if not weights:
                        weights.append((0, 1.0))

                    vert_map[loop_idx] = len(verts_data)
                    verts_data.append((pos, normal, color, uvs, weights))

            f.write(str(len(verts_data)) + '\\n')
            for pos, normal, color, uvs, weights in verts_data:
                f.write(f"{pos.x:.6f} {pos.y:.6f} {pos.z:.6f}\\n")
                f.write(f"{normal[0]:.6f} {normal[1]:.6f} {normal[2]:.6f}\\n")
                f.write(f"{color[0]} {color[1]} {color[2]} {color[3]}\\n")
                for u, v in uvs:
                    f.write(f"{u:.6f} {v:.6f}\\n")
                f.write(str(len(weights)) + '\\n')
                for bidx, w in weights:
                    f.write(f"{bidx} {w:.6f}\\n")

            face_data = []
            for tri in tris:
                face_data.append(f"{vert_map[tri.loops[0]]} {vert_map[tri.loops[1]]} {vert_map[tri.loops[2]]}")
            f.write(str(len(face_data)) + '\\n')
            for fd in face_data:
                f.write(fd + '\\n')

            eval_obj.to_mesh_clear()

    # Copy textures
    tex_copied = []
    import shutil
    for obj in mesh_objects:
        if obj.material_slots:
            for slot in obj.material_slots:
                mat = slot.material
                if mat and mat.use_nodes:
                    for node in mat.node_tree.nodes:
                        if node.type == 'TEX_IMAGE' and node.image:
                            src = node.image.filepath_from_user()
                            if src and os.path.isfile(src):
                                dst = os.path.join(output_dir, os.path.basename(src))
                                if not os.path.exists(dst):
                                    try:
                                        shutil.copy2(src, dst)
                                        tex_copied.append(os.path.basename(src))
                                    except:
                                        pass

    file_size = os.path.getsize(output_file)
    result = {
        "status": "done",
        "output_file": output_file,
        "file_size_mb": round(file_size / 1024 / 1024, 2),
        "bones": len(bones),
        "meshes": len(mesh_objects),
        "textures_copied": tex_copied
    }
    write_status(result)

except Exception as e:
    import traceback
    err = {"status": "error", "error": str(e), "traceback": traceback.format_exc()}
    try:
        write_status(err)
    except:
        pass
'''


def send(data, timeout=30):
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        SERVER, data=body,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def main():
    # Encode the script as base64 and write to file on Windows
    b64 = base64.b64encode(EXPORT_SCRIPT.encode('utf-8')).decode('ascii')

    print("Step 1: Writing export script to Windows...")
    result = send({
        "type": "execute_code",
        "params": {
            "code": (
                "import bpy, os, base64\n"
                f"b64 = '{b64}'\n"
                "script = base64.b64decode(b64).decode('utf-8')\n"
                "path = os.path.join(os.path.dirname(bpy.data.filepath), 'xps_export_script.py')\n"
                "with open(path, 'w', encoding='utf-8') as f:\n"
                "    f.write(script)\n"
                "print(f'Written to: {path}, size: {len(script)} bytes')"
            )
        }
    }, timeout=60)
    print(f"  {result}")

    if result.get("status") != "success":
        print("Failed to write script!")
        return

    # Step 2: Execute via timer (non-blocking for the MCP connection)
    print("\nStep 2: Launching async export in Blender...")
    result = send({
        "type": "execute_code",
        "params": {
            "code": (
                "import bpy, os, threading\n"
                "path = os.path.join(os.path.dirname(bpy.data.filepath), 'xps_export_script.py')\n"
                "def run_export():\n"
                "    exec(open(path, encoding='utf-8').read())\n"
                "t = threading.Thread(target=run_export)\n"
                "t.start()\n"
                "print('Export thread started')"
            )
        }
    }, timeout=60)
    print(f"  {result}")

    # Step 3: Poll for status
    print("\nStep 3: Polling export status...")
    for i in range(120):
        time.sleep(3)
        try:
            result = send({
                "type": "execute_code",
                "params": {
                    "code": (
                        "import os, json, bpy\n"
                        "sf = os.path.join(os.path.dirname(bpy.data.filepath), 'xps_export', 'export_status.json')\n"
                        "if os.path.exists(sf):\n"
                        "    with open(sf) as f:\n"
                        "        print(f.read())\n"
                        "else:\n"
                        "    print('{\"status\": \"waiting\"}')"
                    )
                }
            }, timeout=10)

            status_str = result.get("result", {}).get("result", "")
            if status_str:
                try:
                    status = json.loads(status_str.strip())
                except:
                    status = {"raw": status_str}
            else:
                status = {"status": "no response"}

            print(f"  [{i*3}s] {status}")

            if status.get("status") == "done":
                print(f"\n=== Export complete! ===")
                print(f"File: {status.get('output_file')}")
                print(f"Size: {status.get('file_size_mb')} MB")
                print(f"Bones: {status.get('bones')}")
                print(f"Meshes: {status.get('meshes')}")
                print(f"Textures copied: {status.get('textures_copied')}")
                return

            if status.get("status") == "error":
                print(f"\n=== Export failed! ===")
                print(status.get("error"))
                print(status.get("traceback", ""))
                return

        except Exception as e:
            print(f"  [{i*3}s] poll error: {e}")

    print("Timeout waiting for export!")


if __name__ == "__main__":
    main()
