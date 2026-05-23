import struct


def _write_string(f, s):
    encoded = s.encode("utf-8")
    length = len(encoded)
    # 7-bit variable-length encoding (.NET BinaryReader style)
    if length < 128:
        f.write(bytes([length]))
    else:
        f.write(bytes([length % 128 + 128, length // 128]))
    f.write(encoded)


def _write_header(f):
    f.write(struct.pack("<I", 323232))       # magic
    f.write(struct.pack("<H", 3))            # version major
    f.write(struct.pack("<H", 15))           # version minor
    _write_string(f, "XNAaraL")             # xna_aral
    # settings: 275 uint32 values (1100 bytes) to match XNALaraMesh format
    settings_count = 275
    f.write(struct.pack("<I", settings_count))
    _write_string(f, "b2xps")               # machine
    _write_string(f, "b2xps")               # user
    _write_string(f, "")                     # files
    # settings data: hash + items + padding
    settings = struct.pack("<III", 180, 3, 1)  # hash, items, type
    settings += struct.pack("<II", 0, 0)       # pose length, bone count
    # empty type/count block
    settings += struct.pack("<13I", 2, 4, 4, 2, 1, 3, 0, 4, 3, 5, 4, 0, 256)
    # pad remaining to settings_count * 4 bytes
    remaining = settings_count * 4 - len(settings)
    settings += b'\x00' * remaining
    f.write(settings)


def _write_model_data(f, bones, meshes, has_tangent=True,
                      variable_weights=False):
    # Bones
    f.write(struct.pack("<I", len(bones)))
    for bone in bones:
        _write_string(f, bone["name"])
        f.write(struct.pack("<h", bone["parent"]))
        f.write(struct.pack("<3f", *bone["position"]))
    # Meshes
    f.write(struct.pack("<I", len(meshes)))
    for mesh in meshes:
        _write_string(f, mesh["name"])
        uv_count = mesh["uv_count"]
        f.write(struct.pack("<I", uv_count))
        textures = mesh["textures"]
        f.write(struct.pack("<I", len(textures)))
        for tex_name in textures:
            _write_string(f, tex_name)
            f.write(struct.pack("<I", 0))
        # Vertices
        verts = mesh["vertices"]
        f.write(struct.pack("<I", len(verts)))
        for v in verts:
            f.write(struct.pack("<3f", *v["position"]))
            f.write(struct.pack("<3f", *v["normal"]))
            f.write(struct.pack("<4B", *v["color"]))
            for uv in v["uvs"]:
                f.write(struct.pack("<2f", *uv))
            if has_tangent:
                f.write(struct.pack("<4f", 1, 0, 0, 0))
            bw = sorted(v["bone_weights"], key=lambda x: x[1],
                        reverse=True)
            if variable_weights:
                # variable: uint16 count, then ids, then weights
                f.write(struct.pack("<H", len(bw)))
                for idx, _ in bw:
                    f.write(struct.pack("<H", idx))
                for _, w in bw:
                    f.write(struct.pack("<f", w))
            else:
                # fixed 4 bone weights
                bw = bw[:4]
                indices = [w[0] for w in bw]
                weights = [w[1] for w in bw]
                while len(indices) < 4:
                    indices.append(0)
                    weights.append(0.0)
                total = sum(weights)
                if total > 0:
                    weights = [w / total for w in weights]
                f.write(struct.pack("<4H", *indices))
                f.write(struct.pack("<4f", *weights))
        # Faces: count = number of triangles
        faces = mesh["faces"]
        f.write(struct.pack("<I", len(faces)))
        for face in faces:
            f.write(struct.pack("<3I", *face))


def write_xps(filepath, bones, meshes):
    # v3.15 with header: no tangent, variable weights
    with open(filepath, "wb") as f:
        _write_header(f)
        _write_model_data(f, bones, meshes,
                          has_tangent=False, variable_weights=True)


def write_binary(filepath, bones, meshes):
    # v3.15 with header: no tangent, variable weights
    with open(filepath, "wb") as f:
        _write_header(f)
        _write_model_data(f, bones, meshes,
                          has_tangent=False, variable_weights=True)


def write_ascii(filepath, bones, meshes):
    lines = []
    lines.append(str(len(bones)))
    for bone in bones:
        lines.append(bone["name"])
        lines.append(str(bone["parent"]))
        p = bone["position"]
        lines.append(f"{p[0]:.6f} {p[1]:.6f} {p[2]:.6f}")

    lines.append(str(len(meshes)))
    for mesh in meshes:
        lines.append(mesh["name"])
        lines.append(str(mesh["uv_count"]))
        textures = mesh["textures"]
        lines.append(str(len(textures)))
        for tex_name in textures:
            lines.append(tex_name)
            lines.append("0")

        verts = mesh["vertices"]
        lines.append(str(len(verts)))
        for v in verts:
            p = v["position"]
            lines.append(f"{p[0]:.6f} {p[1]:.6f} {p[2]:.6f}")
            n = v["normal"]
            lines.append(f"{n[0]:.6f} {n[1]:.6f} {n[2]:.6f}")
            c = v["color"]
            lines.append(f"{c[0]} {c[1]} {c[2]} {c[3]}")
            for uv in v["uvs"]:
                lines.append(f"{uv[0]:.6f} {uv[1]:.6f}")
            bw = v["bone_weights"]
            lines.append(str(len(bw)))
            for idx, weight in bw:
                lines.append(f"{idx} {weight:.6f}")

        faces = mesh["faces"]
        lines.append(str(len(faces)))
        for face in faces:
            lines.append(f"{face[0]} {face[1]} {face[2]}")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
