import bpy
import os
from enum import Enum


class TexType(Enum):
    DIFFUSE = "diffuse"
    LIGHTMAP = "lightmap"
    BUMP = "bump"
    MASK = "mask"
    BUMP1 = "bump1"
    BUMP2 = "bump2"
    SPECULAR = "specular"
    ENVIRONMENT = "environment"
    EMISSION = "emission"


PRINCIPLED_INPUT_MAP = {
    "Base Color":        TexType.DIFFUSE,
    "Normal":            TexType.BUMP,
    "Specular IOR Level": TexType.SPECULAR,
    "Specular":          TexType.SPECULAR,
    "Emission Color":    TexType.EMISSION,
    "Emission":          TexType.EMISSION,
}

# render group number -> (alpha, [texture slot types])
# Must match XNALaraMesh xps_material.py definitions exactly
RENDER_GROUPS = {
    4:  (False, [TexType.DIFFUSE, TexType.BUMP]),
    5:  (False, [TexType.DIFFUSE]),
    6:  (True,  [TexType.DIFFUSE, TexType.BUMP]),
    7:  (True,  [TexType.DIFFUSE]),
    36: (False, [TexType.DIFFUSE, TexType.BUMP, TexType.EMISSION]),
    37: (True,  [TexType.DIFFUSE, TexType.BUMP, TexType.EMISSION]),
    38: (False, [TexType.DIFFUSE, TexType.BUMP, TexType.SPECULAR,
                 TexType.EMISSION]),
    39: (True,  [TexType.DIFFUSE, TexType.BUMP, TexType.SPECULAR,
                 TexType.EMISSION]),
    25: (False, [TexType.DIFFUSE, TexType.BUMP, TexType.SPECULAR]),
    26: (True,  [TexType.DIFFUSE, TexType.BUMP, TexType.SPECULAR]),
}


def trace_image_node(node, visited=None, from_socket=None):
    if visited is None:
        visited = set()
    if id(node) in visited:
        return None
    visited.add(id(node))
    if node.bl_idname == "ShaderNodeTexImage" and node.image:
        return node
    if node.bl_idname == "ShaderNodeGroup" and node.node_tree:
        for n in node.node_tree.nodes:
            if n.bl_idname == "NodeGroupOutput":
                if from_socket:
                    inp = n.inputs.get(from_socket.name)
                    if inp and inp.is_linked:
                        result = trace_image_node(
                            inp.links[0].from_node, visited,
                            inp.links[0].from_socket)
                        if result:
                            return result
                else:
                    for inp in n.inputs:
                        if inp.is_linked:
                            result = trace_image_node(
                                inp.links[0].from_node, visited,
                                inp.links[0].from_socket)
                            if result:
                                return result
    deferred = []
    for inp in node.inputs:
        if inp.is_linked:
            if inp.name in ("Fac", "Factor"):
                deferred.append(inp)
                continue
            result = trace_image_node(
                inp.links[0].from_node, visited,
                inp.links[0].from_socket)
            if result:
                return result
    for inp in deferred:
        result = trace_image_node(
            inp.links[0].from_node, visited,
            inp.links[0].from_socket)
        if result:
            return result
    return None


def extract_textures_principled(material):
    if not material or not material.use_nodes:
        return {}
    bsdf = None
    for node in material.node_tree.nodes:
        if node.bl_idname == "ShaderNodeBsdfPrincipled":
            bsdf = node
            break
    if not bsdf:
        return {}
    tex_dic = {}
    for inp in bsdf.inputs:
        if inp.name in PRINCIPLED_INPUT_MAP and inp.is_linked:
            img_node = trace_image_node(
                inp.links[0].from_node, from_socket=inp.links[0].from_socket)
            if img_node:
                abs_path = bpy.path.abspath(img_node.image.filepath)
                tex_dic[PRINCIPLED_INPUT_MAP[inp.name]] = os.path.basename(abs_path)
    if TexType.DIFFUSE not in tex_dic:
        alpha_inp = bsdf.inputs.get("Alpha")
        if alpha_inp and alpha_inp.is_linked:
            img_node = trace_image_node(
                alpha_inp.links[0].from_node,
                from_socket=alpha_inp.links[0].from_socket)
            if img_node:
                abs_path = bpy.path.abspath(img_node.image.filepath)
                tex_dic[TexType.DIFFUSE] = os.path.basename(abs_path)
    return tex_dic


def _collect_images(node_tree, images):
    for node in node_tree.nodes:
        if node.bl_idname == "ShaderNodeTexImage" and node.image:
            abs_path = bpy.path.abspath(node.image.filepath)
            basename = os.path.basename(abs_path)
            if basename not in images:
                images.append(basename)
        elif node.bl_idname == "ShaderNodeGroup" and node.node_tree:
            _collect_images(node.node_tree, images)


def extract_textures_generic(material):
    if not material or not material.use_nodes:
        return {}
    tex_dic = {}
    images = []
    _collect_images(material.node_tree, images)
    # guess texture type by filename convention
    type_order = [TexType.DIFFUSE, TexType.BUMP, TexType.SPECULAR, TexType.EMISSION]
    for i, img in enumerate(images):
        low = img.lower()
        if "_n." in low or "_n_" in low or "normal" in low or "_norm" in low:
            tex_dic[TexType.BUMP] = img
        elif "_s." in low or "_s_" in low or "specular" in low or "spec" in low or "_orm" in low:
            tex_dic[TexType.SPECULAR] = img
        elif "_e." in low or "_e_" in low or "emission" in low or "emiss" in low:
            tex_dic[TexType.EMISSION] = img
        elif TexType.DIFFUSE not in tex_dic:
            tex_dic[TexType.DIFFUSE] = img
        elif i < len(type_order):
            t = type_order[i]
            if t not in tex_dic:
                tex_dic[t] = img
    return tex_dic


GROUP_INPUT_MAP = {
    "Color":          TexType.DIFFUSE,
    "Base Color":     TexType.DIFFUSE,
    "Diffuse":        TexType.DIFFUSE,
    "Normal":         TexType.BUMP,
    "Normal 1":       TexType.BUMP,
    "Bump":           TexType.BUMP,
    "Specular":       TexType.SPECULAR,
    "Emission":       TexType.EMISSION,
    "Emission Color": TexType.EMISSION,
}


def _find_output_groups(node_tree):
    output_groups = set()
    for node in node_tree.nodes:
        if node.bl_idname == "ShaderNodeOutputMaterial":
            for inp in node.inputs:
                if inp.is_linked:
                    fn = inp.links[0].from_node
                    if fn.bl_idname == "ShaderNodeGroup":
                        output_groups.add(id(fn))
    return output_groups


def _extract_from_group(node):
    tex_dic = {}
    for inp in node.inputs:
        if inp.name in GROUP_INPUT_MAP and inp.is_linked:
            img_node = trace_image_node(
                inp.links[0].from_node,
                from_socket=inp.links[0].from_socket)
            if img_node:
                abs_path = bpy.path.abspath(img_node.image.filepath)
                tex_dic[GROUP_INPUT_MAP[inp.name]] = os.path.basename(
                    abs_path)
    return tex_dic


def extract_textures_group(material):
    if not material or not material.use_nodes:
        return {}
    output_groups = _find_output_groups(material.node_tree)
    groups = []
    for node in material.node_tree.nodes:
        if node.bl_idname == "ShaderNodeGroup" and node.node_tree:
            if id(node) in output_groups:
                groups.insert(0, node)
            else:
                groups.append(node)
    for node in groups:
        tex_dic = _extract_from_group(node)
        if tex_dic:
            return tex_dic
    return {}


def extract_textures(material):
    tex_dic = extract_textures_principled(material)
    if not tex_dic:
        tex_dic = extract_textures_group(material)
    if not tex_dic:
        tex_dic = extract_textures_generic(material)
    return tex_dic


def has_alpha_material(material):
    if not material:
        return False
    if hasattr(material, 'surface_render_method'):
        if material.surface_render_method == 'BLENDED':
            return True
    elif hasattr(material, 'blend_method'):
        if material.blend_method in ('CLIP', 'HASHED', 'BLEND'):
            return True
    if material.use_nodes:
        for node in material.node_tree.nodes:
            if node.bl_idname == "ShaderNodeBsdfPrincipled":
                alpha_input = node.inputs.get("Alpha")
                if alpha_input and alpha_input.is_linked:
                    return True
                if alpha_input and alpha_input.default_value < 1.0:
                    return True
    return False


def choose_render_group(tex_types, alpha=False):
    has_bump = TexType.BUMP in tex_types
    has_spec = TexType.SPECULAR in tex_types
    has_emit = TexType.EMISSION in tex_types

    if alpha:
        if has_spec and has_emit:
            return 39   # alpha + diff + bump + spec + emission
        if has_spec:
            return 26   # alpha + diff + bump + specular
        if has_emit:
            return 37   # alpha + diff + bump + emission
        if has_bump:
            return 6    # alpha + diff + bump
        return 7        # alpha + diff only
    else:
        if has_spec and has_emit:
            return 38   # diff + bump + spec + emission
        if has_spec:
            return 25   # diff + bump + specular
        if has_emit:
            return 36   # diff + bump + emission
        if has_bump:
            return 4    # diff + bump
        return 5        # diff only


def build_texture_list(material):
    tex_dic = extract_textures(material)
    alpha = has_alpha_material(material)
    rg = choose_render_group(tex_dic, alpha)

    if rg in RENDER_GROUPS:
        _, slot_types = RENDER_GROUPS[rg]
    else:
        slot_types = list(tex_dic.keys()) or [TexType.DIFFUSE]

    textures = []
    for st in slot_types:
        textures.append(tex_dic.get(st, "missing.png"))

    return rg, textures
