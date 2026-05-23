# Blender to XPS Export - 原理文档

## 1. XPS 格式概述

XPS (XNALara Pose Studio) 是一种 3D 模型格式，主要用于 XNALara/XPS 渲染器。
模型文件为 `.mesh`（二进制）或 `.mesh.ascii`（文本），结构如下：

```
┌─────────────────────────────┐
│  Header (可选, 含版本信息)    │
├─────────────────────────────┤
│  Bones (骨骼层级)            │
│  ├─ name, parent_id         │
│  └─ position (head)         │
├─────────────────────────────┤
│  Meshes (网格列表)           │
│  ├─ name (含渲染组编号)       │
│  ├─ textures (贴图槽位)      │
│  ├─ vertices (顶点数据)      │
│  │  ├─ position (3 float)   │
│  │  ├─ normal   (3 float)   │
│  │  ├─ color    (4 byte)    │
│  │  ├─ uv       (2 float)   │
│  │  └─ bone weights         │
│  └─ faces (三角面索引)        │
└─────────────────────────────┘
```

### 坐标系转换

Blender 和 XPS 使用不同的坐标系：

```
Blender: X→右, Y→前, Z→上 (右手坐标系)
XPS:     X→右, Y→上, Z→前

转换: XPS(x, y, z) = Blender(x, z, -y)
UV:   XPS(u, v) = Blender(u, 1-v)
面:   顶点顺序反转 (winding order)
```

### 渲染组 (Render Group)

XPS 通过**网格名称前缀数字**决定贴图槽位的含义：

| 组号 | 贴图槽位                           | 典型用途       |
|------|-------------------------------------|----------------|
| 1    | Diffuse                            | 纯色物体       |
| 3    | Diffuse, Bump                      | 基础纹理       |
| 4    | Diffuse, Bump, Specular            | 标准角色皮肤   |
| 6    | Diffuse, Lightmap, Bump, Specular  | 场景物体       |
| 7    | Diffuse, Lightmap, Bump, Spec, Env | 金属/反射      |
| 22   | Diffuse, Bump (Alpha透明)          | 头发/睫毛      |
| 24   | Diffuse, Bump, Spec (Alpha透明)    | 透明+高光      |

命名示例：`4_body` = 渲染组4的body网格 → 3张贴图(Diffuse, Bump, Specular)。

---

## 2. 核心问题：材质贴图映射

### 问题描述

现有的 XNALaraMesh 插件导出时，使用 `XPSShaderWrapper` 提取贴图。
该 Wrapper **只识别名为 "XPS Shader" 的自定义节点组**：

```python
# node_shader_utils.py 中的逻辑
if node_principled.bl_idname == 'ShaderNodeGroup' \
   and node_principled.node_tree.name == 'XPS Shader':
    # 找到了，从 XPS Shader 的输入端口读贴图
```

但绝大多数 Blender 模型使用的是标准 **Principled BSDF** 着色器，输入端口名称完全不同：

```
XPS Shader 节点:              Principled BSDF 节点:
├─ "Diffuse"     ──→          ├─ "Base Color"
├─ "Lightmap"    ──→          │  (无对应)
├─ "Specular"    ──→          ├─ "Specular IOR Level"
├─ "Bump"        ──→          ├─ "Normal"
└─ "Emission"    ──→          └─ "Emission Color"
```

**结果**：所有贴图都匹配不上，导出的 XPS 文件材质全部丢失。

### 解决方案

在贴图提取逻辑中加入 Principled BSDF 的支持。关键是**节点树回溯**：

```
                    Principled BSDF
                    ├─ Base Color ← RGB Curves ← Image Texture (body_basecolor.png)
                    ├─ Normal     ← Normal Map  ← Image Texture (body_normal.png)
                    └─ Specular   ←               Image Texture (body_specular.png)

问题：贴图节点不一定直接连接到 BSDF，中间可能有
     RGB Curves、Normal Map、Mix 等中间节点。
```

**解法：递归回溯节点链接，直到找到 Image Texture 节点。**

```python
def trace_image_node(node):
    """从任意节点向上游回溯，找到第一个 Image Texture 节点"""
    if node.bl_idname == "ShaderNodeTexImage" and node.image:
        return node                         # 找到了
    for inp in node.inputs:                 # 递归检查所有输入
        if inp.is_linked:
            result = trace_image_node(inp.links[0].from_node)
            if result:
                return result
    return None                             # 这条链路没有贴图
```

然后建立 Principled BSDF 输入端口到 XPS 贴图类型的映射：

```python
PRINCIPLED_TO_XPS = {
    "Base Color":        TextureType.DIFFUSE,
    "Normal":            TextureType.BUMP,
    "Specular IOR Level": TextureType.SPECULAR,  # Blender 4.x
    "Specular":          TextureType.SPECULAR,    # Blender 3.x
    "Emission Color":    TextureType.EMISSION,
    "Emission":          TextureType.EMISSION,
}
```

### 渲染组自动选择

根据检测到的贴图类型，自动选择最合适的渲染组：

```python
def choose_render_group(tex_types, has_alpha):
    has_diff = DIFFUSE in tex_types
    has_bump = BUMP in tex_types
    has_spec = SPECULAR in tex_types

    if has_alpha:
        if has_spec: return 24   # Alpha + Bump + Specular
        if has_bump: return 22   # Alpha + Bump
        return 21                # Alpha only
    if has_spec: return 4        # Diffuse + Bump + Specular
    if has_bump: return 3        # Diffuse + Bump
    return 1                     # Diffuse only
```

---

## 3. 导出性能优化

### 瓶颈分析

导出 14 万顶点模型时，逐顶点 Python 循环提取数据是最大瓶颈：

```python
# 慢：每次访问触发 Python→C 跨语言调用
for v in mesh.vertices:           # 14万次
    pos = v.co                     # 每次都是一次 C 调用
    for g in v.groups:             # 再嵌套循环
        weight = g.weight
```

### foreach_get 批量提取

Blender 的 `foreach_get` 将整个 C 数组一次性拷贝到 Python，速度快 50-100 倍：

```python
import numpy as np

# 位置：一次读取所有顶点
n = len(mesh.vertices)
positions = np.empty(n * 3, dtype=np.float32)
mesh.vertices.foreach_get("co", positions)
positions = positions.reshape(-1, 3)

# 法线：一次读取所有 corner normals
cn = np.empty(len(mesh.loops) * 3, dtype=np.float32)
mesh.corner_normals.foreach_get("vector", cn)
cn = cn.reshape(-1, 3)

# UV：一次读取
uv = np.empty(len(uv_layer.data) * 2, dtype=np.float32)
uv_layer.data.foreach_get("uv", uv)
uv = uv.reshape(-1, 2)
```

### 不能批量提取的部分

**骨骼权重**是唯一不能用 foreach_get 的部分，因为每个顶点的权重数量不同。
但通常骨骼权重的访问只占总时间的 10-15%，所以整体性能仍然大幅提升。

---

## 4. .mesh 与 .xps 二进制格式差异

两者是同一种数据结构，差异在文件头和顶点字段：

```
.mesh 文件:                         .xps 文件:
┌─────────────────────┐            ┌─────────────────────┐
│  (无 header)         │            │  Header              │
│                     │            │  ├─ magic: 323232    │
│                     │            │  ├─ version: 2.15    │
│                     │            │  ├─ xna_aral string  │
│                     │            │  └─ settings[]       │
├─────────────────────┤            ├─────────────────────┤
│  Bones              │            │  Bones (相同)        │
├─────────────────────┤            ├─────────────────────┤
│  Meshes             │            │  Meshes              │
│  └─ Vertex:         │            │  └─ Vertex:          │
│     ├─ pos (3f)     │            │     ├─ pos (3f)      │
│     ├─ normal (3f)  │            │     ├─ normal (3f)   │
│     ├─ color (4B)   │            │     ├─ color (4B)    │
│     ├─ uv (2f)      │            │     ├─ uv (2f)       │
│     ├─ tangent (4f) │ ← 有       │     │                │ ← 无
│     ├─ bones (4H)   │            │     ├─ bones (4H)    │
│     └─ weights (4f) │            │     └─ weights (4f)  │
└─────────────────────┘            └─────────────────────┘
```

| 特性 | .mesh | .xps |
|------|-------|------|
| Header | 无 | 有 (magic + version + settings) |
| Tangent | 有 (4 float/顶点) | 无 (由 header version 2.15 决定) |
| 骨骼权重 | 固定 4 个/顶点 | 固定 4 个 (version < 3 时) |
| 文件大小 | 较大 (+16 bytes/顶点) | 较小 |
| 兼容性 | 最广泛 | 较新工具 |

Header version 的影响（通过 `bin_ops.hasTangentVersion` 判断）：
- version 2.15 + hasHeader: `hasTangent=False`
- 无 header (.mesh): `hasTangent=True`（默认行为）

---

## 5. 顶点去重

### 问题

Blender 的 `loop_triangles` 为每个三角形的每个角分配独立的 loop index。
如果直接用 loop_idx 做顶点标识，共享边的相邻三角形会产生大量重复顶点。

例：一个顶点被 6 个三角形共享 → 产生 6 个 XPS 顶点（实际只需 1-2 个）。

### 解决方案

用内容做去重 key，而非 loop_idx：

```python
key = (vertex_index,
       round(normal_x, 5), round(normal_y, 5), round(normal_z, 5),
       round(uv_u, 5), round(uv_v, 5))
```

同一顶点、同一法线、同一 UV 的 loop corner 共享同一个 XPS 顶点。
只有在法线或 UV 不同时（如硬边、UV 接缝处）才拆分。

效果：14 万顶点模型从 61 MB 降至 13.8 MB（接近 XNALaraMesh 的 12.4 MB）。

---

## 6. 插件架构

```
Blender Model
    │
    ├─ Armature ──→ 提取骨骼层级 ──→ XPS Bones
    │
    ├─ Mesh Objects ──→ 三角化 + foreach_get ──→ XPS Vertices/Faces
    │                   + 内容去重
    │
    └─ Materials (Principled BSDF)
         │
         ├─ trace_image_node() 回溯找贴图
         ├─ PRINCIPLED_TO_XPS 映射贴图类型
         ├─ choose_render_group() 选渲染组
         └─ 坐标系转换 (Y↔Z, UV flip, winding)
                │
                ├──→ .mesh    (write_binary: 无header, 有tangent)
                ├──→ .xps     (write_xps: 有header, 无tangent)
                └──→ .mesh.ascii (write_ascii: 纯文本)
```

### UI 入口

1. **File → Export → XPS Model** — 标准文件浏览器，支持全部/选中导出
2. **3D Viewport → Sidebar → B2XPS** — Panel 面板，显示选中物体列表，一键导出选中
