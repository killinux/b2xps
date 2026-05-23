"""
Patch XNALaraMesh material_creator.py for Blender 4.x compatibility.
"""
import urllib.request
import json
import base64

SERVER = "https://unclamped-unclamped-afoot.ngrok-free.dev"

PATCH_CODE = r'''
import bpy, os, re

path = os.path.join(
    bpy.utils.resource_path('USER'),
    "scripts", "addons", "XNALaraMesh", "material_creator.py"
)

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# Remove any previous compat patch
if '# B2XPS compat patch' in content:
    start = content.find('\n# B2XPS compat patch')
    # Find the next function that's NOT a compat function
    rest = content[start+1:]
    lines = rest.split('\n')
    end_offset = 0
    in_compat = True
    for line in lines:
        if line.startswith('def ') and not line.startswith('def _compat'):
            break
        end_offset += len(line) + 1
    content = content[:start+1] + content[start+1+end_offset:]

# Remove previous _SOCKET_TYPE_MAP if present
if '_SOCKET_TYPE_MAP' in content:
    content = re.sub(r'\n_SOCKET_TYPE_MAP\s*=\s*\{[^}]*\}\n', '\n', content)

# Now add fresh compat functions
compat_block = '''
# B2XPS compat patch for Blender 4.x
_SOCKET_COMPAT = {
    "NodeSocketFloatFactor": "NodeSocketFloat",
    "NodeSocketFloatUnsigned": "NodeSocketFloat",
}

def _compat_clear(node_tree):
    if hasattr(node_tree, "interface"):
        node_tree.interface.clear()
    else:
        node_tree.inputs.clear()
        node_tree.outputs.clear()

def _compat_new_input(node_tree, socket_type, name):
    if hasattr(node_tree, "interface"):
        st = _SOCKET_COMPAT.get(socket_type, socket_type)
        return node_tree.interface.new_socket(name=name, in_out="INPUT", socket_type=st)
    return node_tree.inputs.new(socket_type, name)

def _compat_new_output(node_tree, socket_type, name):
    if hasattr(node_tree, "interface"):
        st = _SOCKET_COMPAT.get(socket_type, socket_type)
        return node_tree.interface.new_socket(name=name, in_out="OUTPUT", socket_type=st)
    return node_tree.outputs.new(socket_type, name)

'''

if '_compat_clear' not in content:
    # Insert after last import
    last_import = max(content.rfind('\nimport '), content.rfind('\nfrom '))
    next_nl = content.index('\n', last_import + 1)
    content = content[:next_nl+1] + compat_block + content[next_nl+1:]

    # Replace API calls
    content = content.replace(
        "    node_tree.inputs.clear()\n    node_tree.outputs.clear()",
        "    _compat_clear(node_tree)"
    )
    content = re.sub(
        r'node_tree\.inputs\.new\((\w+),\s*([\'"][^\'"]+[\'"])\)',
        r'_compat_new_input(node_tree, \1, \2)',
        content
    )
    content = re.sub(
        r'node_tree\.outputs\.new\((\w+),\s*([\'"][^\'"]+[\'"])\)',
        r'_compat_new_output(node_tree, \1, \2)',
        content
    )

with open(path, "w", encoding="utf-8") as f:
    f.write(content)
print("Patched: " + path)
'''


def send(data, timeout=60):
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        SERVER, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def main():
    b64 = base64.b64encode(PATCH_CODE.encode("utf-8")).decode("ascii")

    print("Step 1: Writing patch...")
    result = send({
        "type": "execute_code",
        "params": {
            "code": (
                "import base64, os, bpy\n"
                f"b64 = '{b64}'\n"
                "script = base64.b64decode(b64).decode('utf-8')\n"
                "p = os.path.join(os.path.dirname(bpy.data.filepath), '_patch_import.py')\n"
                "with open(p, 'w', encoding='utf-8') as f:\n"
                "    f.write(script)\n"
                "print('Written: ' + p)"
            )
        }
    })
    print(f"  {result}")

    print("Step 2: Applying...")
    result = send({
        "type": "execute_code",
        "params": {
            "code": (
                "import bpy, os\n"
                "p = os.path.join(os.path.dirname(bpy.data.filepath), '_patch_import.py')\n"
                "exec(open(p, encoding='utf-8').read())"
            )
        }
    })
    print(f"  {result}")

    print("Step 3: Reloading...")
    result = send({
        "type": "execute_code",
        "params": {
            "code": (
                "import importlib\n"
                "from XNALaraMesh import material_creator\n"
                "importlib.reload(material_creator)\n"
                "print('OK')"
            )
        }
    })
    print(f"  {result}")

    print("Step 4: Test import...")
    result = send({
        "type": "execute_code",
        "params": {
            "code": (
                "import bpy\n"
                "fpath = r'E:\\Downloads\\Yennefer\\xps_export\\verify_test.mesh'\n"
                "bpy.ops.xps_tools.import_model(filepath=fpath)\n"
                "meshes = [o for o in bpy.context.scene.objects if o.type=='MESH']\n"
                "print(f'Imported {len(meshes)} meshes')\n"
                "for m in meshes[:3]:\n"
                "    print(f'  {m.name}: {len(m.data.vertices)} verts')"
            )
        }
    }, timeout=120)
    print(f"  {result}")


if __name__ == "__main__":
    main()
