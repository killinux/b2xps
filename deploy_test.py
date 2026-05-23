"""
Deploy b2xps_addon to remote Blender via base64, install, and test export.
"""
import urllib.request
import json
import base64
import os
import zipfile
import io

SERVER = "https://unclamped-unclamped-afoot.ngrok-free.dev"

ADDON_DIR = os.path.join(os.path.dirname(__file__), "b2xps_addon")


def send(data, timeout=60):
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        SERVER, data=body,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def make_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(ADDON_DIR):
            for fname in files:
                if fname.endswith('.py'):
                    fpath = os.path.join(root, fname)
                    arcname = os.path.join("b2xps_addon",
                                           os.path.relpath(fpath, ADDON_DIR))
                    zf.write(fpath, arcname)
    return buf.getvalue()


def main():
    # Step 1: Create zip and send to Windows
    print("Step 1: Creating and sending addon zip...")
    zip_bytes = make_zip()
    b64 = base64.b64encode(zip_bytes).decode("ascii")
    print(f"  Zip size: {len(zip_bytes)} bytes, base64: {len(b64)} bytes")

    result = send({
        "type": "execute_code",
        "params": {
            "code": (
                "import base64, os, bpy\n"
                f"b64 = '{b64}'\n"
                "zdata = base64.b64decode(b64)\n"
                "zpath = os.path.join(os.path.dirname(bpy.data.filepath), 'b2xps_addon.zip')\n"
                "with open(zpath, 'wb') as f:\n"
                "    f.write(zdata)\n"
                "print('Written zip to: ' + zpath + ' size: ' + str(len(zdata)))"
            )
        }
    })
    print(f"  {result}")
    if result.get("status") != "success":
        return

    # Step 2: Install addon
    print("\nStep 2: Installing addon...")
    result = send({
        "type": "execute_code",
        "params": {
            "code": (
                "import bpy, os, sys, zipfile\n"
                "zpath = os.path.join(os.path.dirname(bpy.data.filepath), 'b2xps_addon.zip')\n"
                "addon_dir = os.path.join(bpy.utils.resource_path('USER'), 'scripts', 'addons')\n"
                "target = os.path.join(addon_dir, 'b2xps_addon')\n"
                "import shutil\n"
                "if os.path.exists(target):\n"
                "    shutil.rmtree(target)\n"
                "with zipfile.ZipFile(zpath) as zf:\n"
                "    zf.extractall(addon_dir)\n"
                "print('Installed to: ' + target)\n"
                "# Register\n"
                "if 'b2xps_addon' in sys.modules:\n"
                "    del sys.modules['b2xps_addon']\n"
                "    for k in list(sys.modules.keys()):\n"
                "        if k.startswith('b2xps_addon.'):\n"
                "            del sys.modules[k]\n"
                "import importlib\n"
                "import b2xps_addon\n"
                "importlib.reload(b2xps_addon)\n"
                "b2xps_addon.register()\n"
                "print('Registered!')"
            )
        }
    })
    print(f"  {result}")
    if result.get("status") != "success":
        return

    # Step 3: Test export
    print("\nStep 3: Testing export...")
    result = send({
        "type": "execute_code",
        "params": {
            "code": (
                "import bpy, os\n"
                "bpy.ops.object.mode_set(mode='OBJECT')\n"
                "bpy.ops.object.select_all(action='SELECT')\n"
                "outdir = os.path.join(os.path.dirname(bpy.data.filepath), 'xps_export')\n"
                "os.makedirs(outdir, exist_ok=True)\n"
                "outpath = os.path.join(outdir, 'Yennefer_b2xps.mesh')\n"
                "bpy.ops.b2xps.export_model(filepath=outpath)\n"
                "size = os.path.getsize(outpath)\n"
                "print(f'Exported: {outpath} ({round(size/1024/1024,2)} MB)')"
            )
        }
    }, timeout=120)
    print(f"  {result}")


if __name__ == "__main__":
    main()
