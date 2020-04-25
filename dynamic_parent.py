# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

# <pep8 compliant>

bl_info = {
    "name": "Dynamic Parent",
    "author": "Roman Volodin, roman.volodin@gmail.com",
    "version": (0, 51),
    "blender": (2, 80, 0),
    "location": "View3D > Tool Panel",
    "description": "Allows to create and disable an animated ChildOf constraint",
    "warning": "The addon still in progress! Be careful!",
    "wiki_url": "http://wiki.blender.org/index.php/Extensions:2.6/Py/Scripts/Animation/Dynamic_Parent",
    "tracker_url": "",
    "category": "Animation"}

import bpy
import mathutils


def get_rotation_mode(obj):
    if obj.rotation_mode in ('QUATERNION', 'AXIS_ANGLE'):
        return obj.rotation_mode.lower()
    return 'euler'


def insert_keyframe(obj, frame=bpy.context.scene.frame_current):
    rotation_mode = get_rotation_mode(obj)
    
    data_paths = (
         'location',
        f'rotation_{rotation_mode}',
         'scale',
    )
        
    for data_path in data_paths:
        obj.keyframe_insert(data_path=data_path, frame=frame)


def insert_keyframe_constraint(constraint, frame=bpy.context.scene.frame_current):
    constraint.keyframe_insert(data_path='influence', frame=frame) 


def get_selected_objects(context):
    if context.mode not in ('OBJECT', 'POSE'):
        return
    
    if context.mode == 'OBJECT':
        active = context.active_object
        selected = [obj for obj in context.selected_objects if obj != active]
    
    if context.mode == 'POSE':
        active = context.active_pose_bone
        selected = [bone for bone in context.selected_pose_bones if bone != active]
    
    # if active.select_get():    #  DOESNT WORK IN POSE MODE
    #     selected.append(active)
    selected.append(active)
    
    return selected


def get_last_dymanic_parent_constraint(obj):
    if not obj.constraints:
        return
    const = obj.constraints[-1]
    if const.name.startswith("DP_") and const.influence == 1:
        return const


def is_same_armature(pbone_parent, pbone_child):
    return pbone_parent.id_data == pbone_child.id_data


def calc_reverse_matrix(parent, child):
    if type(parent) == bpy.types.PoseBone:
        matrix = parent.id_data.matrix_world @ parent.matrix
        if type(child) == bpy.types.PoseBone:
            matrix = child.id_data.matrix_world.inverted() @ parent.id_data.matrix_world @ parent.matrix
        if is_same_armature(parent, child):
            matrix = parent.matrix
        return matrix.inverted()
    return parent.matrix_world.inverted()


def create_constraint(parent, child, frame):
    parent_pbone = None
    if type(parent) == bpy.types.PoseBone:
        parent_pbone = parent
        parent = parent.id_data
    
    const = child.constraints.new('CHILD_OF') 
    if parent_pbone:
        const.target = parent
        const.subtarget = parent_pbone.name
        matrix = calc_reverse_matrix(parent_pbone, child)
        name = f'DP_{parent.name}_{parent_pbone.name}'
    else:
        const.target = parent
        matrix = calc_reverse_matrix(parent, child)
        name = f'DP_{parent.name}'
    const.name = name
    const.inverse_matrix = matrix
    const.show_expanded = False
    # return const

    const.influence = 0
    insert_keyframe(child, frame=frame-1)
    insert_keyframe_constraint(const, frame=frame-1)

    const.influence = 1
    insert_keyframe(child, frame=frame)
    insert_keyframe_constraint(const, frame=frame)


def disable_constraint(obj, const, frame):
    if type(obj) == bpy.types.PoseBone:
        matrix_final = obj.matrix
    else:
        matrix_final = obj.matrix_world
    
    insert_keyframe(obj, frame=frame-1)
    insert_keyframe_constraint(const, frame=frame-1)
    
    const.influence = 0
    if type(obj) == bpy.types.PoseBone:
        obj.matrix = matrix_final
    else:
        obj.matrix_world = matrix_final

    insert_keyframe(obj, frame=frame)
    insert_keyframe_constraint(const, frame=frame)
    return


def dp_clear(obj, pbone):
    dp_curves = []
    dp_keys = []
    for fcurve in obj.animation_data.action.fcurves:
        if "constraints" in fcurve.data_path and "DP_" in fcurve.data_path:
            dp_curves.append(fcurve)
    
    for f in dp_curves:
        for key in f.keyframe_points:
            dp_keys.append(key.co[0])
    
    dp_keys = list(set(dp_keys))
    dp_keys.sort()
    
    for fcurve in obj.animation_data.action.fcurves[:]:
        # Removing constraints fcurves
        if fcurve.data_path.startswith("constraints") and "DP_" in fcurve.data_path:
            obj.animation_data.action.fcurves.remove(fcurve)
        # Removing keys for loc, rot, scale fcurves
        else:
            for frame in dp_keys:
                for key in fcurve.keyframe_points[:]:
                    if key.co[0] == frame:
                        fcurve.keyframe_points.remove(key)
            if not fcurve.keyframe_points:
                obj.animation_data.action.fcurves.remove(fcurve)

 
    # Removing constraints
    if pbone:
        obj = pbone
    for const in obj.constraints[:]:
        if const.name.startswith("DP_"):
            obj.constraints.remove(const)
        
        

class DYNAMIC_PARENT_OT_create(bpy.types.Operator):
    """Create a new animated Child Of constraint"""
    bl_idname = "dynamic_parent.create"
    bl_label = "Create Constraint"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        return context.mode in ('OBJECT', 'POSE')

    def execute(self, context):
        frame = context.scene.frame_current
        counter = 0
        *children, parent = get_selected_objects(context)
        
        if not parent or not children:
            self.report({'ERROR'}, 'Select at least two objects or bones.')
            return {'CANCELLED'}

        for child in children:
            const = get_last_dymanic_parent_constraint(child)
            if const:
                disable_constraint(child, const, frame)
            create_constraint(parent, child, frame)
            counter += 1

        # parent.select_set(False)  # FIXME: DOESNT WORK FOR POSE BONES
        self.report({'INFO'}, f'{counter} constraint(s) created.')
        return {'FINISHED'}    


class DYNAMIC_PARENT_OT_disable(bpy.types.Operator):
    """Disable the current animated Child Of constraint"""
    bl_idname = "dynamic_parent.disable"
    bl_label = "Disable Constraint"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        return context.mode in ('OBJECT', 'POSE')

    def execute(self, context):
        frame = context.scene.frame_current
        objects = get_selected_objects(context)
        counter = 0

        if not objects:
            self.report({'ERROR'}, 'Nothing selected. Ваще.')
            return {'CANCELLED'}
        
        for obj in objects:
            const = get_last_dymanic_parent_constraint(obj)
            if const is None:
                continue
            disable_constraint(obj, const, frame)
            counter += 1

        self.report({'INFO'}, f'{counter} constraints were disabled.')
        return {'FINISHED'}

class DpClear(bpy.types.Operator):
    """Clear Dynamic Parent constraints"""
    bl_idname = "dp.clear"
    bl_label = "Clear Dynamic Parent"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        pbone = None
        obj = bpy.context.active_object
        if obj.type == 'ARMATURE':
            pbone = bpy.context.active_pose_bone
        
        dp_clear(obj, pbone)
        
        return {'FINISHED'}

class DpBake(bpy.types.Operator):
    """Bake Dynamic Parent animation"""
    bl_idname = "dp.bake"
    bl_label = "Bake Dynamic Parent"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        obj = bpy.context.active_object
        scn = bpy.context.scene
        
        if obj.type == 'ARMATURE':
            obj = bpy.context.active_pose_bone
            bpy.ops.nla.bake(frame_start=scn.frame_start, 
                             frame_end=scn.frame_end, step=1, 
                             only_selected=True, visual_keying=True,
                             clear_constraints=False, clear_parents=False, 
                             bake_types={'POSE'})
            # Removing constraints
            for const in obj.constraints[:]:
                if const.name.startswith("DP_"):
                    obj.constraints.remove(const)
        else:
            bpy.ops.nla.bake(frame_start=scn.frame_start,
                             frame_end=scn.frame_end, step=1, 
                             only_selected=True, visual_keying=True,
                             clear_constraints=False, clear_parents=False, 
                             bake_types={'OBJECT'})
            # Removing constraints
            for const in obj.constraints[:]:
                if const.name.startswith("DP_"):
                    obj.constraints.remove(const)
        
        return {'FINISHED'}

class DpClearMenu(bpy.types.Menu):
    """Clear or bake Dynamic Parent constraints"""
    bl_label = "Clear Dynamic Parent?"
    bl_idname = "DP_MT_clear_menu"
    
    def draw(self, context):
        layout = self.layout
        layout.operator("dp.clear", text="Clear", icon="X")
        layout.operator("dp.bake", text="Bake and clear", icon="REC")

class DpUI(bpy.types.Panel):
    """User interface for Dynamic Parent addon"""
    bl_label = "Dynamic Parent"
    bl_idname = "DP_PT_ui"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Dynamic Parent"
    
    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        col.operator("dynamic_parent.create", text="Create", icon="KEY_HLT")
        col.operator("dynamic_parent.disable", text="Disable", icon="KEY_DEHLT")
        #col.operator("dp.clear", text="Clear", icon="X")
        #col.operator("wm.call_menu", text="Clear", icon="RIGHTARROW_THIN").name="dp.clear_menu"
        col.menu("DP_MT_clear_menu", text="Clear")


classes = (
    DYNAMIC_PARENT_OT_create,
    DYNAMIC_PARENT_OT_disable,
    DpClear,
    DpBake,
    DpClearMenu,
    DpUI,
)

register, unregister = bpy.utils.register_classes_factory(classes)

if __name__ == "__main__":
    register()
