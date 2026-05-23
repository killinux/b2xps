bl_info = {
    "name": "B2XPS - Universal Blender to XPS Exporter",
    "author": "b2xps",
    "version": (1, 0, 0),
    "blender": (4, 0, 0),
    "location": "File > Export > XPS Model (.mesh/.mesh.ascii)",
    "description": "Export Blender models to XPS/XNALara format with "
                   "automatic Principled BSDF material mapping",
    "category": "Import-Export",
}

import bpy
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
            ('BIN', "Binary (.mesh)", "Standard binary XPS format"),
            ('ASCII', "ASCII (.mesh.ascii)", "Text-based XPS format"),
        ],
        default='BIN',
    )

    export_selected: BoolProperty(
        name="Selected Only",
        description="Export only selected objects",
        default=False,
    )

    copy_textures: BoolProperty(
        name="Copy Textures",
        description="Copy texture files to export directory",
        default=True,
    )

    def execute(self, context):
        filepath = self.filepath
        if self.export_format == 'ASCII':
            if not filepath.endswith(".mesh.ascii"):
                filepath = filepath.rsplit(".", 1)[0] + ".mesh.ascii"

        from . import exporter
        settings = {
            "export_selected": self.export_selected,
            "copy_textures": self.copy_textures,
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
        layout.prop(self, "copy_textures")


def menu_func_export(self, context):
    self.layout.operator(B2XPS_OT_export.bl_idname,
                         text="XPS Model (.mesh/.mesh.ascii)")


def register():
    bpy.utils.register_class(B2XPS_OT_export)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)


def unregister():
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
    bpy.utils.unregister_class(B2XPS_OT_export)


if __name__ == "__main__":
    register()
