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
    40: (False, [TexType.DIFFUSE, TexType.BUMP, TexType.SPECULAR]),
    41: (True,  [TexType.DIFFUSE, TexType.BUMP, TexType.SPECULAR]),
}


def trace_image_node(node, visited=None):
    if visited is None:
        visited = set()
    if id(node) in visited:
        return None
    visited.add(id(node))
    if node.bl_idname == "ShaderNodeTexImage" and node.image:
        return node
    for inp in node.inputs:
        if inp.is_linked:
            result = trace_image_node(inp.links[0].from_node, visited)
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
            img_node = trace_image_node(inp.links[0].from_node)
            if img_node:
                abs_path = bpy.path.abspath(img_node.image.filepath)
                tex_dic[PRINCIPLED_INPUT_MAP[inp.name]] = os.path.basename(abs_path)
    return tex_dic


def extract_textures_generic(material):
    if not material or not material.use_nodes:
        return {}
    tex_dic = {}
    images = []
    for node in material.node_tree.nodes:
        if node.bl_idname == "ShaderNodeTexImage" and node.image:
            abs_path = bpy.path.abspath(node.image.filepath)
            images.append(os.path.basename(abs_path))
    if images:
        tex_dic[TexType.DIFFUSE] = images[0]
    return tex_dic


def extract_textures(material):
    tex_dic = extract_textures_principled(material)
    if not tex_dic:
        tex_dic = extract_textures_generic(material)
    return tex_dic


def has_alpha_material(material):
    if not material:
        return False
    if material.blend_method in ('ALPHA', 'ALPHA_HASHED', 'BLEND'):
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
            return 41   # alpha + diff + bump + specular
        if has_emit:
            return 37   # alpha + diff + bump + emission
        if has_bump:
            return 6    # alpha + diff + bump
        return 7        # alpha + diff only
    else:
        if has_spec and has_emit:
            return 38   # diff + bump + spec + emission
        if has_spec:
            return 40   # diff + bump + specular
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
