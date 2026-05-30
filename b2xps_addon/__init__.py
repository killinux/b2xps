bl_info = {
    "name": "B2XPS - Universal Blender to XPS Exporter",
    "author": "b2xps",
    "version": (1, 1, 0),
    "blender": (4, 0, 0),
    "location": "File > Export, 3D Viewport > Sidebar > B2XPS",
    "description": "Export Blender models to XPS/XNALara format with "
                   "automatic Principled BSDF material mapping",
    "category": "Import-Export",
}

import bpy
import os
from bpy.props import StringProperty, BoolProperty, EnumProperty
from bpy_extras.io_utils import ExportHelper


class B2XPS_OT_export(bpy.types.Operator, ExportHelper):
    bl_idname = "b2xps.export_model"
    bl_label = "Export XPS Model"
    bl_options = {'PRESET'}

    filename_ext = ".mesh"

    filter_glob: StringProperty(
        default="*.mesh;*.mesh.ascii;*.xps",
        options={'HIDDEN'},
    )

    export_format: EnumProperty(
        name="Format",
        items=[
            ('MESH', "Binary (.mesh)", "Standard binary format, no header, with tangent"),
            ('XPS', "Binary (.xps)", "Binary format with header, no tangent"),
            ('ASCII', "ASCII (.mesh.ascii)", "Text-based format"),
        ],
        default='MESH',
    )

    export_selected: BoolProperty(
        name="Selected Only",
        description="Export only selected objects",
        default=False,
    )

    visible_only: BoolProperty(
        name="Visible Only",
        description="Skip hidden objects",
        default=True,
    )

    copy_textures: BoolProperty(
        name="Copy Textures",
        description="Copy texture files to export directory",
        default=True,
    )

    def execute(self, context):
        filepath = self.filepath
        base = filepath.rsplit(".", 1)[0]
        if self.export_format == 'ASCII':
            if not filepath.endswith(".mesh.ascii"):
                filepath = base + ".mesh.ascii"
        elif self.export_format == 'XPS':
            if not filepath.endswith(".xps"):
                filepath = base + ".xps"
        else:
            if not filepath.endswith(".mesh"):
                filepath = base + ".mesh"

        from . import exporter
        settings = {
            "export_selected": self.export_selected,
            "visible_only": self.visible_only,
            "copy_textures": self.copy_textures,
            "format": self.export_format,
        }
        result = exporter.export(filepath, settings)
        self.report({'INFO'},
                    f"Exported {result['meshes']} meshes, "
                    f"{result['bones']} bones to {filepath}")
        return {'FINISHED'}

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "export_format")
        layout.prop(self, "export_selected")
        layout.prop(self, "visible_only")
        layout.prop(self, "copy_textures")


class B2XPS_OT_export_selected(bpy.types.Operator):
    bl_idname = "b2xps.export_selected"
    bl_label = "Export Selected"
    bl_description = "Export selected objects to XPS format"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return any(obj.type == 'MESH' for obj in context.selected_objects)

    def execute(self, context):
        scene = context.scene
        fmt = scene.b2xps_format
        filepath = bpy.path.abspath(scene.b2xps_export_path)

        if not filepath:
            self.report({'ERROR'}, "Export path is empty")
            return {'CANCELLED'}

        ext_map = {'MESH': '.mesh', 'XPS': '.xps', 'ASCII': '.mesh.ascii'}
        expected_ext = ext_map[fmt]
        base = filepath
        for ext in ('.mesh.ascii', '.mesh', '.xps'):
            if filepath.endswith(ext):
                base = filepath[:-len(ext)]
                break
        filepath = base + expected_ext

        dirpath = os.path.dirname(filepath)
        if dirpath:
            os.makedirs(dirpath, exist_ok=True)

        from . import exporter
        settings = {
            "export_selected": True,
            "visible_only": scene.b2xps_visible_only,
            "copy_textures": scene.b2xps_copy_textures,
            "format": fmt,
        }
        result = exporter.export(filepath, settings)
        self.report({'INFO'},
                    f"Exported {result['meshes']} meshes, "
                    f"{result['bones']} bones")
        return {'FINISHED'}


class B2XPS_PT_panel(bpy.types.Panel):
    bl_label = "B2XPS Export"
    bl_idname = "B2XPS_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "B2XPS"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # Selection info
        mesh_objs = [o for o in context.selected_objects if o.type == 'MESH']
        arm_objs = [o for o in context.selected_objects if o.type == 'ARMATURE']

        box = layout.box()
        box.label(text="Selection", icon='RESTRICT_SELECT_OFF')
        box.label(text=f"Meshes: {len(mesh_objs)}")
        box.label(text=f"Armature: {arm_objs[0].name if arm_objs else 'None'}")
        if mesh_objs:
            col = box.column(align=True)
            for obj in mesh_objs[:10]:
                col.label(text=f"  {obj.name}", icon='MESH_DATA')
            if len(mesh_objs) > 10:
                col.label(text=f"  ... +{len(mesh_objs) - 10} more")

        # Export settings
        layout.separator()
        layout.label(text="Settings", icon='EXPORT')
        layout.prop(scene, "b2xps_format")
        layout.prop(scene, "b2xps_export_path")
        layout.prop(scene, "b2xps_visible_only")
        layout.prop(scene, "b2xps_copy_textures")

        # Export button
        layout.separator()
        row = layout.row(align=True)
        row.scale_y = 1.5
        row.operator("b2xps.export_selected", icon='EXPORT')


def menu_func_export(self, context):
    self.layout.operator(B2XPS_OT_export.bl_idname,
                         text="XPS Model (.mesh/.xps/.mesh.ascii)")


classes = (
    B2XPS_OT_export,
    B2XPS_OT_export_selected,
    B2XPS_PT_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)

    bpy.types.Scene.b2xps_format = EnumProperty(
        name="Format",
        items=[
            ('MESH', ".mesh", "Binary, no header, with tangent"),
            ('XPS', ".xps", "Binary, with header, no tangent"),
            ('ASCII', ".mesh.ascii", "Text format"),
        ],
        default='MESH',
    )
    bpy.types.Scene.b2xps_export_path = StringProperty(
        name="Path",
        description="Export file path",
        default="//export/model",
        subtype='FILE_PATH',
    )
    bpy.types.Scene.b2xps_visible_only = BoolProperty(
        name="Visible Only",
        description="Skip hidden objects",
        default=True,
    )
    bpy.types.Scene.b2xps_copy_textures = BoolProperty(
        name="Copy Textures",
        description="Copy texture files to export directory",
        default=True,
    )


def unregister():
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.b2xps_format
    del bpy.types.Scene.b2xps_export_path
    del bpy.types.Scene.b2xps_visible_only
    del bpy.types.Scene.b2xps_copy_textures


if __name__ == "__main__":
    register()
