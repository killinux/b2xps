import bpy
import bmesh
import os
import shutil
import numpy as np
from mathutils import Vector
from . import materials
from . import writer


def coord_transform(co):
    return (co[0], co[2], -co[1])


def normal_transform(n):
    return (n[0], n[2], -n[1])


def uv_transform(uv):
    return (uv[0], 1.0 - uv[1])


def export_bones(armature):
    bones = []
    if not armature:
        bones.append({"name": "root", "parent": -1, "position": (0, 0, 0)})
        return bones, {"root": 0}
    bone_name_to_idx = {}
    obj_mat = armature.matrix_local
    for i, bone in enumerate(armature.data.bones):
        bone_name_to_idx[bone.name] = i
        parent = -1
        if bone.parent:
            parent = bone_name_to_idx.get(bone.parent.name, -1)
        pos = coord_transform(obj_mat @ bone.head_local)
        bones.append({"name": bone.name, "parent": parent, "position": pos})
    return bones, bone_name_to_idx


def export_mesh(obj, armature, bone_name_to_idx, settings):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = obj.evaluated_get(depsgraph)
    mesh = eval_obj.to_mesh()

    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bm.to_mesh(mesh)
    bm.free()
    mesh.calc_loop_triangles()

    obj_mat = obj.matrix_world
    rot_mat = obj_mat.to_3x3()

    # batch read positions
    n_verts = len(mesh.vertices)
    co_buf = np.empty(n_verts * 3, dtype=np.float64)
    mesh.vertices.foreach_get("co", co_buf)
    all_co = co_buf.reshape(-1, 3)

    # batch read normals
    n_loops = len(mesh.loops)
    if hasattr(mesh, 'corner_normals') and len(mesh.corner_normals) > 0:
        nor_buf = np.empty(n_loops * 3, dtype=np.float32)
        mesh.corner_normals.foreach_get("vector", nor_buf)
        all_normals = nor_buf.reshape(-1, 3)
    else:
        nor_buf = np.empty(n_verts * 3, dtype=np.float32)
        mesh.vertices.foreach_get("normal", nor_buf)
        all_normals = nor_buf.reshape(-1, 3)

    # batch read UVs
    uv_layers = mesh.uv_layers
    uv_count = max(len(uv_layers), 1)
    all_uvs = []
    for uv_layer in uv_layers:
        uv_buf = np.empty(n_loops * 2, dtype=np.float32)
        uv_layer.data.foreach_get("uv", uv_buf)
        all_uvs.append(uv_buf.reshape(-1, 2))

    # batch read loop vertex indices
    loop_vidx = np.empty(n_loops, dtype=np.int32)
    mesh.loops.foreach_get("vertex_index", loop_vidx)

    # vertex colors
    has_colors = bool(mesh.color_attributes)
    color_data = None
    color_domain = None
    if has_colors:
        ca = mesh.color_attributes[0]
        color_domain = ca.domain
        n_entries = len(ca.data)
        cbuf = np.empty(n_entries * 4, dtype=np.float32)
        ca.data.foreach_get("color", cbuf)
        color_data = cbuf.reshape(-1, 4)

    # pre-compute bone weights per vertex (can't batch this)
    vert_weights = [[] for _ in range(n_verts)]
    for vi, vert in enumerate(mesh.vertices):
        for vg in vert.groups:
            if vg.group < len(obj.vertex_groups):
                gname = obj.vertex_groups[vg.group].name
                if gname in bone_name_to_idx and vg.weight > 1e-4:
                    vert_weights[vi].append(
                        (bone_name_to_idx[gname], vg.weight))
        if not vert_weights[vi]:
            vert_weights[vi].append((0, 1.0))

    # build XPS vertices from loop triangles with content-based dedup
    xps_verts = []
    vert_key_map = {}  # content key -> vertex index
    loop_to_vert = {}  # loop_idx -> vertex index
    tris = mesh.loop_triangles

    for tri in tris:
        for loop_idx in tri.loops:
            if loop_idx in loop_to_vert:
                continue
            vi = loop_vidx[loop_idx]

            wco = obj_mat @ mesh.vertices[vi].co
            pos = coord_transform(wco)

            if hasattr(mesh, 'corner_normals') and len(mesh.corner_normals) > 0:
                ln = Vector(all_normals[loop_idx])
            else:
                ln = Vector(all_normals[vi])
            wn = (rot_mat @ ln).normalized()
            normal = normal_transform(wn)

            uvs = []
            for uv_arr in all_uvs:
                u, v = uv_arr[loop_idx]
                uvs.append(uv_transform((u, v)))
            if not uvs:
                uvs.append((0.0, 0.0))

            color = (255, 255, 255, 255)
            if color_data is not None:
                ci = loop_idx if color_domain == 'CORNER' else vi
                if ci < len(color_data):
                    c = color_data[ci]
                    color = (int(c[0]*255), int(c[1]*255),
                             int(c[2]*255), int(c[3]*255))

            bw = vert_weights[vi]

            # dedup key: vertex index + normal + first UV
            key = (vi,
                   round(normal[0], 5), round(normal[1], 5), round(normal[2], 5),
                   round(uvs[0][0], 5), round(uvs[0][1], 5))

            if key in vert_key_map:
                loop_to_vert[loop_idx] = vert_key_map[key]
            else:
                idx = len(xps_verts)
                vert_key_map[key] = idx
                loop_to_vert[loop_idx] = idx
                xps_verts.append({
                    "position": pos,
                    "normal": normal,
                    "color": color,
                    "uvs": uvs,
                    "bone_weights": bw,
                })

    # build faces with reversed winding
    xps_faces = []
    for tri in tris:
        i0 = loop_to_vert[tri.loops[0]]
        i1 = loop_to_vert[tri.loops[1]]
        i2 = loop_to_vert[tri.loops[2]]
        xps_faces.append((i0, i2, i1))

    # material textures
    rg, tex_list = materials.build_texture_list(
        obj.material_slots[0].material if obj.material_slots else None)

    mesh_name = f"{rg}_{obj.name}"

    eval_obj.to_mesh_clear()

    return {
        "name": mesh_name,
        "uv_count": uv_count,
        "textures": tex_list,
        "vertices": xps_verts,
        "faces": xps_faces,
        "render_group": rg,
    }


def copy_textures(mesh_objects, output_dir):
    copied = set()
    for obj in mesh_objects:
        if not obj.material_slots:
            continue
        for slot in obj.material_slots:
            mat = slot.material
            if not mat or not mat.use_nodes:
                continue
            for node in mat.node_tree.nodes:
                if node.bl_idname == "ShaderNodeTexImage" and node.image:
                    src = bpy.path.abspath(node.image.filepath)
                    if src and os.path.isfile(src):
                        basename = os.path.basename(src)
                        if basename not in copied:
                            dst = os.path.join(output_dir, basename)
                            if not os.path.exists(dst):
                                shutil.copy2(src, dst)
                            copied.add(basename)
    return list(copied)


def export(filepath, settings):
    if settings.get("export_selected"):
        objects = bpy.context.selected_objects
    else:
        objects = bpy.context.visible_objects

    armature = None
    mesh_objects = []
    for obj in objects:
        if obj.type == "ARMATURE":
            armature = obj
        elif obj.type == "MESH" and obj.data.vertices:
            mesh_objects.append(obj)

    bones, bone_name_to_idx = export_bones(armature)

    xps_meshes = []
    for obj in mesh_objects:
        xps_mesh = export_mesh(obj, armature, bone_name_to_idx, settings)
        xps_meshes.append(xps_mesh)

    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".ascii" or filepath.endswith(".mesh.ascii"):
        writer.write_ascii(filepath, bones, xps_meshes)
    else:
        writer.write_binary(filepath, bones, xps_meshes)

    # copy textures
    output_dir = os.path.dirname(filepath)
    if settings.get("copy_textures", True):
        copy_textures(mesh_objects, output_dir)

    return {"bones": len(bones), "meshes": len(xps_meshes)}
