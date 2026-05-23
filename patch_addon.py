"""
Patch the XNALaraMesh addon to support Principled BSDF texture mapping.
Sends the patch as base64 to avoid quoting issues.
"""
import urllib.request
import json
import base64

SERVER = "https://unclamped-unclamped-afoot.ngrok-free.dev"

# This is the Python code that will run inside Blender to patch the addon file.
PATCH_CODE = r"""
import os, bpy

path = os.path.join(
    bpy.utils.resource_path('USER'),
    "scripts", "addons", "XNALaraMesh", "export_xnalara_model.py"
)

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# Restore original makeXpsTexture first (in case of previous broken patch)
# Find the current makeXpsTexture block
start = content.find("def _trace_image(")
if start == -1:
    start = content.find("MISSING_TEX =")
if start == -1:
    start = content.find("def makeXpsTexture(")
end = content.find("\ndef getTextures(", start)

old_block = content[start:end]

new_block = '''def _trace_image_tex(node):
    # Walk backwards through node links to find an Image Texture node.
    if node.bl_idname == "ShaderNodeTexImage" and node.image:
        return node
    for inp in node.inputs:
        if inp.is_linked:
            result = _trace_image_tex(inp.links[0].from_node)
            if result:
                return result
    return None


def _get_principled_tex_dic(material):
    # Extract texture dict from Principled BSDF node.
    if not material or not material.use_nodes:
        return {}
    bsdf = None
    for node in material.node_tree.nodes:
        if node.bl_idname == "ShaderNodeBsdfPrincipled":
            bsdf = node
            break
    if not bsdf:
        return {}
    input_to_xps = {
        "Base Color": xps_material.TextureType.DIFFUSE,
        "Normal": xps_material.TextureType.BUMP,
        "Specular IOR Level": xps_material.TextureType.SPECULAR,
        "Specular": xps_material.TextureType.SPECULAR,
        "Emission Color": xps_material.TextureType.EMISSION,
        "Emission": xps_material.TextureType.EMISSION,
    }
    tex_dic = {}
    for inp in bsdf.inputs:
        if inp.name in input_to_xps and inp.is_linked:
            img_node = _trace_image_tex(inp.links[0].from_node)
            if img_node:
                abs_path = bpy.path.abspath(img_node.image.filepath)
                tex_dic[input_to_xps[inp.name]] = os.path.basename(abs_path)
    return tex_dic


def makeXpsTexture(mesh, material):
    active_uv = mesh.data.uv_layers.active
    active_uv_index = mesh.data.uv_layers.active_index
    xpsShaderWrapper = node_shader_utils.XPSShaderWrapper(material)

    tex_dic = {}
    texture = getTextureFilename(xpsShaderWrapper.diffuse_texture)
    addTexture(tex_dic, xps_material.TextureType.DIFFUSE, texture)
    texture = getTextureFilename(xpsShaderWrapper.lightmap_texture)
    addTexture(tex_dic, xps_material.TextureType.LIGHT, texture)
    texture = getTextureFilename(xpsShaderWrapper.normalmap_texture)
    addTexture(tex_dic, xps_material.TextureType.BUMP, texture)
    texture = getTextureFilename(xpsShaderWrapper.normal_mask_texture)
    addTexture(tex_dic, xps_material.TextureType.MASK, texture)
    texture = getTextureFilename(xpsShaderWrapper.microbump1_texture)
    addTexture(tex_dic, xps_material.TextureType.BUMP1, texture)
    texture = getTextureFilename(xpsShaderWrapper.microbump2_texture)
    addTexture(tex_dic, xps_material.TextureType.BUMP2, texture)
    texture = getTextureFilename(xpsShaderWrapper.specular_texture)
    addTexture(tex_dic, xps_material.TextureType.SPECULAR, texture)
    texture = getTextureFilename(xpsShaderWrapper.environment_texture)
    addTexture(tex_dic, xps_material.TextureType.ENVIRONMENT, texture)
    texture = getTextureFilename(xpsShaderWrapper.emission_texture)
    addTexture(tex_dic, xps_material.TextureType.EMISSION, texture)

    # Fallback: if XPS Shader not found, read from Principled BSDF
    if not tex_dic:
        tex_dic = _get_principled_tex_dic(material)

    renderType = xps_material.makeRenderType(mesh.name)
    renderGroup = xps_material.RenderGroup(renderType)
    rgTextures = renderGroup.rgTexType

    texutre_list = []
    _missing = "missing.png"
    for tex_type in rgTextures:
        texture = tex_dic.get(tex_type, _missing)
        texutre_list.append(texture)

    xpsTextures = []
    for id, textute in enumerate(texutre_list):
        xpsTexture = xps_types.XpsTexture(id, textute, 0)
        xpsTextures.append(xpsTexture)

    return xpsTextures


'''

content = content[:start] + new_block + content[end:]

with open(path, "w", encoding="utf-8") as f:
    f.write(content)

print(f"Patched: {path}")
print(f"File size: {len(content)}")
"""


def main():
    b64 = base64.b64encode(PATCH_CODE.encode("utf-8")).decode("ascii")

    # Step 1: Write patch script to disk
    print("Writing patch script...")
    result = send({
        "type": "execute_code",
        "params": {
            "code": (
                "import base64, os, bpy\n"
                f"b64 = '{b64}'\n"
                "script = base64.b64decode(b64).decode('utf-8')\n"
                "p = os.path.join(os.path.dirname(bpy.data.filepath), '_patch.py')\n"
                "with open(p, 'w', encoding='utf-8') as f:\n"
                "    f.write(script)\n"
                "print('Written to: ' + p)"
            )
        }
    })
    print(f"  {result}")

    # Step 2: Execute the patch
    print("Applying patch...")
    result = send({
        "type": "execute_code",
        "params": {
            "code": (
                "import bpy, os\n"
                "p = os.path.join(os.path.dirname(bpy.data.filepath), '_patch.py')\n"
                "exec(open(p, encoding='utf-8').read())"
            )
        }
    })
    print(f"  {result}")

    # Step 3: Reload module
    print("Reloading module...")
    result = send({
        "type": "execute_code",
        "params": {
            "code": (
                "import importlib\n"
                "from XNALaraMesh import export_xnalara_model\n"
                "importlib.reload(export_xnalara_model)\n"
                "print('Reloaded')"
            )
        }
    })
    print(f"  {result}")

    # Step 4: Re-export
    print("Exporting...")
    result = send({
        "type": "execute_code",
        "params": {
            "code": (
                "import bpy, os\n"
                "bpy.ops.object.mode_set(mode='OBJECT')\n"
                "bpy.ops.object.select_all(action='SELECT')\n"
                "outdir = os.path.join(os.path.dirname(bpy.data.filepath), 'xps_export')\n"
                "os.makedirs(outdir, exist_ok=True)\n"
                "outpath = os.path.join(outdir, 'Yennefer.mesh')\n"
                "bpy.ops.xps_tools.export_model(filepath=outpath)\n"
                "size = os.path.getsize(outpath)\n"
                "print(f'Done: {outpath} ({round(size/1024/1024,2)} MB)')"
            )
        }
    }, timeout=120)
    print(f"  {result}")


def send(data, timeout=60):
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        SERVER, data=body,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


if __name__ == "__main__":
    main()
