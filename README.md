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

1. **材质提取** — 从 Principled BSDF 节点递归回溯，穿过 RGB Curves / Normal Map 等中间节点找到 Image Texture
2. **贴图映射** — Base Color → Diffuse, Normal → Bump, Specular → Specular, Emission → Emission
3. **渲染组选择** — 根据检测到的贴图类型自动选择 XPS render group 编号
4. **坐标转换** — Blender (X,Y,Z) → XPS (X,Z,-Y)，UV 翻转，面序反转
5. **三角化 + 去重** — bmesh 三角化，基于内容的顶点去重
6. **贴图复制** — 自动把引用的贴图文件复制到导出目录

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
