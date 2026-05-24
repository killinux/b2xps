# B2XPS - Universal Blender to XPS Exporter

将任意 Blender 模型导出为 XPS/XNALara 格式（`.mesh` / `.mesh.ascii`），自动处理 Principled BSDF 材质映射。

## 安装

### 本地安装

```bash
# 打包插件
cd b2xps
zip -r b2xps_addon.zip b2xps_addon/
```

在 Blender 中：**Edit → Preferences → Add-ons → Install** → 选择 `b2xps_addon.zip` → 勾选启用。

### 远程安装（通过 client.py/server.py）

```bash
python3 deploy_test.py
```

会自动打包、上传、安装并测试导出。

## 使用

### Blender 界面

**方式一：File → Export → XPS Model (.mesh/.xps/.mesh.ascii)**

导出面板选项：

| 选项 | 说明 |
|------|------|
| Format | Binary (.mesh) / Binary (.xps) / ASCII (.mesh.ascii) |
| Selected Only | 只导出选中物体 |
| Copy Textures | 复制贴图文件到导出目录 |

**方式二：3D Viewport → 侧边栏 → B2XPS**

1. 在视口中选中要导出的物体（Mesh + Armature）
2. 按 `N` 打开侧边栏，切换到 **B2XPS** 标签
3. Panel 显示选中的 Mesh 列表和 Armature
4. 设置导出格式和路径，点击 **Export Selected**

### Python / 远程调用

```python
import bpy

# 导出所有可见物体（binary）
bpy.ops.object.select_all(action="SELECT")
bpy.ops.b2xps.export_model(filepath="C:/output/model.mesh")

# 导出 ASCII 格式
bpy.ops.b2xps.export_model(filepath="C:/output/model.mesh.ascii")

# 只导出选中物体，不复制贴图
bpy.ops.b2xps.export_model(
    filepath="C:/output/model.mesh",
    export_selected=True,
    copy_textures=False,
)
```

通过远程控制：

```bash
python3 client.py execute '{"code": "import bpy; bpy.ops.object.select_all(action=\"SELECT\"); bpy.ops.b2xps.export_model(filepath=\"E:/output/model.mesh\")"}'
```

## 插件做了什么

1. **材质提取** — 三级贴图提取策略（见下文）
2. **贴图映射** — Base Color → Diffuse, Normal → Bump, Specular → Specular, Emission → Emission
3. **渲染组选择** — 根据检测到的贴图类型自动选择 XPS render group 编号
4. **坐标转换** — Blender (X,Y,Z) → XPS (X,Z,-Y)，UV 翻转，面序反转
5. **三角化 + 去重** — bmesh 三角化，基于内容的顶点去重
6. **贴图复制** — 自动把引用的贴图文件复制到导出目录

### 贴图提取策略

插件按以下优先级提取材质贴图：

**第一级：Principled BSDF 直连**

从 Principled BSDF 节点的输入端口（Base Color、Normal、Specular IOR Level、Emission Color）反向追踪，穿过 RGB Curves、Normal Map 等中间节点，找到 Image Texture。

**第二级：节点组输入端口映射**

很多模型使用自定义节点组（如 "Skin"、"FF Casual Pictures"）代替 Principled BSDF。插件检查节点组的输入端口名称，按以下映射提取：

| 端口名称 | 贴图类型 |
|----------|----------|
| Color / Base Color / Diffuse | DIFFUSE |
| Normal / Normal 1 / Bump | BUMP |
| Specular | SPECULAR |
| Emission / Emission Color | EMISSION |

**第三级：文件名猜测**

如果前两级都没结果，收集所有 Image Texture 节点（含节点组内部），根据文件名模式猜测类型：`_n`/`normal` → Bump，`_s`/`spec`/`_orm` → Specular，`_e`/`emission` → Emission，其余 → Diffuse。

### 节点追踪机制 (trace_image_node)

递归追踪节点链接，找到上游的 Image Texture 节点。有两个关键优化：

- **Mix 节点 Factor 跳过** — Mix/MixRGB 节点的 Factor 输入通常连接遮罩贴图（如控制唇色区域的 Lips.png），而非实际颜色。追踪时优先走 A/B 颜色通道，避免找到错误贴图。
- **节点组穿透** — 遇到 ShaderNodeGroup 时，进入组的内部节点树，从 GroupOutput 节点反向追踪。通过 `from_socket` 参数定位正确的输出通道，避免从 Color 通道误跳到 Normal 通道。

### 渲染组映射

根据检测到的贴图类型和透明度，自动选择 XNALaraMesh 标准渲染组：

| 渲染组 | 透明 | 贴图槽位 | 典型用途 |
|--------|------|----------|----------|
| 4 | 否 | Diffuse, Bump | 基础纹理 |
| 5 | 否 | Diffuse | 纯色物体 |
| 6 | 是 | Diffuse, Bump | 头发、睫毛 |
| 7 | 是 | Diffuse | 简单透明 |
| 25 | 否 | Diffuse, Bump, Specular | 角色皮肤 |
| 26 | 是 | Diffuse, Bump, Specular | 透明+高光 |
| 36 | 否 | Diffuse, Bump, Emission | 自发光 |
| 37 | 是 | Diffuse, Bump, Emission | 透明自发光 |
| 38 | 否 | Diffuse, Bump, Specular, Emission | 完整材质 |
| 39 | 是 | Diffuse, Bump, Specular, Emission | 完整透明材质 |

### Blender 4.0+ 兼容性

- **Alpha 检测** — Blender 4.0 移除了 `material.blend_method`，替换为 `material.surface_render_method`。插件通过 `hasattr` 检测 API 版本，分别处理。
- **法线** — 优先使用 `mesh.corner_normals`（4.0+），回退到 `calc_normals_split()`（3.x）。
- **顶点色** — 优先使用 `mesh.color_attributes`（4.0+），回退到 `mesh.vertex_colors`（3.x）。
- **Specular 输入** — 同时识别 `Specular IOR Level`（4.x）和 `Specular`（3.x）。

## 对比 XNALaraMesh 插件

| | XNALaraMesh | B2XPS |
|---|---|---|
| Principled BSDF | 不支持（只认 XPS Shader 节点组） | 支持 |
| 渲染组 | 从网格名称解析 | 自动根据材质选择 |
| 性能 | 纯 Python 循环 | foreach_get + numpy 批量读取 |
| Blender 4.x | 需要手动改代码 | 原生兼容 |

## 文件结构

```
b2xps/
├── README.md
├── docs/
│   └── PRINCIPLE.md          # 技术原理文档
├── b2xps_addon/              # Blender 插件
│   ├── __init__.py           # 注册、导出 operator、UI
│   ├── exporter.py           # 骨骼/网格导出
│   ├── materials.py          # 材质贴图提取
│   └── writer.py             # .mesh / .mesh.ascii 写入
├── deploy_test.py            # 远程部署测试
└── patch_addon.py            # XNALaraMesh 补丁（备用方案）
```

## 技术细节

详见 [docs/PRINCIPLE.md](docs/PRINCIPLE.md)。
