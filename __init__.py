# SPDX-License-Identifier: GPL-3.0-or-later

bl_info = {
    "name": "CatTools",
    "author": "Woody",
    "version": (1, 0, 3),
    "blender": (4, 2, 0),
    "location": "View3D > UI > CatTools 탭",
    "description": "CAT 블록 모델링에 유용한 도구 모음",
    "warning": "",
    "doc_url": "",
    "category": "3D View",
}

import bpy, math, bmesh
from typing import Set
from bpy.types import Context, Panel, Operator
from bpy.props import StringProperty, FloatProperty, BoolProperty, IntProperty

# 머티리얼 체크 & 생성 & 리턴 (중복 방지)
def check_material_exist(material_name):
    if material_name in bpy.data.materials:
        material = bpy.data.materials[material_name]
        bpy.data.materials.remove(material)

    material = bpy.data.materials.new(material_name)
    material.use_nodes = True
    bsdf = material.node_tree.nodes["Principled BSDF"]
    bsdf.inputs[12].default_value = 0    # Specular = '0'

    return material


# 메시 체크 & 제거 (중복 방지)
def check_mesh_exist(mesh_name):
    if mesh_name in bpy.data.meshes:
        mesh = bpy.data.meshes[mesh_name]
        bpy.data.meshes.remove(mesh)


# 메인 패널: 사이드바 메뉴 UI 설정
class OBJECT_PT_WoodyTool(Panel):
    bl_label = "CatTools"
    bl_idname = "OBJECT_PT_woodytool"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "CatTools"

    def draw(self, context):
        layout = self.layout

    # 변환
        # selected_object = bpy.context.object

        # 선택한 오브젝트의 Properties 사용
        # layout.label(text="Transform :", icon="OUTLINER_DATA_EMPTY")
        # layout.prop(selected_object, "location", text="")
        # layout.prop(selected_object, "rotation_euler", text="")
        # layout.prop(selected_object, "scale", text="")

        # layout.separator(factor=1)

    # 실린더
        # layout.label(text="Cyliner :", icon='MESH_CYLINDER')
        # row = layout.row()
        # row.operator(Add_Cylinder_6.bl_idname, text= Add_Cylinder_6.bl_label) # 버튼 : 8각형
        # row.operator(Add_Cylinder_8.bl_idname, text= Add_Cylinder_8.bl_label) # 버튼 : 8각형
        # row.operator(Add_Cylinder_10.bl_idname, text= Add_Cylinder_10.bl_label) # 버튼 : 10각형
        # row.operator(Add_Cylinder_12.bl_idname, text= Add_Cylinder_12.bl_label) # 버튼 : 12각형

        # layout.separator(factor=1)

        # 원형 배열 버튼



        # 머티리얼 셰이더
        layout.label(text="Shader :", icon='SHADING_RENDERED')
        row = layout.row()
        row.operator(Add_Material.bl_idname, text= Add_Material.bl_label)
        row.operator(SHADER_OP_TwoSideTex.bl_idname, text= SHADER_OP_TwoSideTex.bl_label)

        # row = layout.row()
        # row.operator(SHADER_OP_Blend2Tex.bl_idname, text= SHADER_OP_Blend2Tex.bl_label)
        # row.operator(SHADER_OP_Blend3Tex.bl_idname, text= SHADER_OP_Blend3Tex.bl_label)
        # row.operator(SHADER_OP_Blend4Tex.bl_idname, text= SHADER_OP_Blend4Tex.bl_label)

        layout.separator(factor=1)

    # 팔레트
        # layout.label(text="Palette :", icon='GROUP_VCOL')
        # layout.operator(PALETTE_OP_RGB.bl_idname, text= PALETTE_OP_RGB.bl_label)

        # layout.separator(factor=1)

        # 모디파이어
        layout.label(text="Modifier :", icon= 'MODIFIER_DATA')

        row = layout.row()
        row.operator(Add_Lattice.bl_idname, text= Add_Lattice.bl_label, icon= 'MOD_LATTICE')
        row.operator(CircleArray.bl_idname, text=CircleArray.bl_label, icon="OUTLINER_DATA_POINTCLOUD")

        row = layout.row()
        # Mirror 모디파이어 추가 버튼
        row.operator(Add_Mirror_X_Modifier.bl_idname, text=Add_Mirror_X_Modifier.bl_label, icon="MOD_MIRROR")
        row.operator(Add_Mirror_Y_Modifier.bl_idname, text=Add_Mirror_Y_Modifier.bl_label, icon="MOD_MIRROR")
        row.operator(Add_Mirror_Z_Modifier.bl_idname, text=Add_Mirror_Z_Modifier.bl_label, icon="MOD_MIRROR")


        layout.separator(factor=1)

        # 텍스트 추가
        # layout.label(text="Text :", icon = 'OUTLINER_OB_FONT')
        # layout.operator(Add_Text.bl_idname, text= Add_Text.bl_label)


# 텍스트 패널: 텍스트 생성 후 간격 옵션 ----------------------------------------

class OBJECT_PT_Spacing(Panel):
    bl_label = "Text Spacing"
    bl_idname = "OBJECT_PT_spacing"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "CatTools"
    bl_parentid = "OBJECT_PT_woodytool"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        text = context.object.data

        row = layout.row()
        row.label(text= "텍스트 Spacing 옵션 설정")

        row = layout.split(factor= 0.45)
        row.label(text= "Character:")
        row.prop(text, "space_character", text= "")

        row = layout.split(factor= 0.45)
        row.label(text= "Word:")
        row.prop(text, "space_word", text= "")

        row = layout.split(factor= 0.45)
        row.label(text= "Line:")
        row.prop(text, "space_line", text= "")

class OBJECT_PT_Mirror_Modifier(Panel):
    bl_label = "Mirror Axis"
    bl_idname = "OBJECT_PT_Mirror_Modifier"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "CatTools"
    bl_parentid = "OBJECT_PT_woodytool"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        selected_object = context.object
        mirror_modifier = None

        # 선택한 오브젝트의 Mirror 모디파이어
        for modifier in selected_object.modifiers:
            if modifier.type == 'MIRROR':
                mirror_modifier = modifier
                break

        # Mirror Modifier가 존재하는 경우에만 UI를 그립니다.
        if mirror_modifier:
            # Mirror Axis 축 변경 toggle 버튼
            layout.prop(mirror_modifier, "use_axis", toggle=True)
        else:
            layout.label(text="Mirror Modifier를 찾을 수 없습니다.")

# 실린더 연산자 -----------------------------------------------------------------------------

class Add_Cylinder_6(Operator):
    bl_label = "6"
    bl_idname = "wm.add_cylinder_6"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        bpy.ops.mesh.primitive_cylinder_add(vertices=6, radius=0.5, depth=1, enter_editmode=False, align='WORLD', location=(0, 0, 0), scale=(1,1,1))
        return {'FINISHED'}

class Add_Cylinder_8(Operator):
    bl_label = "8"
    bl_idname = "wm.add_cylinder_8"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=0.5, depth=1, enter_editmode=False, align='WORLD', location=(0, 0, 0), scale=(1,1,1))
        return {'FINISHED'}

class Add_Cylinder_10(Operator):
    bl_label = "10"
    bl_idname = "wm.add_cylinder_10"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=0.5, depth=1, enter_editmode=False, align='WORLD', location=(0, 0, 0), scale=(1,1,1))
        return {'FINISHED'}

class Add_Cylinder_12(Operator):
    bl_label = "12"
    bl_idname = "wm.add_cylinder_12"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=0.5, depth=1, enter_editmode=False, align='WORLD', location=(0, 0, 0), scale=(1,1,1))
        return {'FINISHED'}


# 원형 배열 오브젝트
class CircleArray(Operator):
    bl_label = "Circle Array"
    bl_idname = "object.circle_array"
    bl_options = {'REGISTER', 'UNDO'}

    segment : IntProperty(name="Segment", default=6, min=3) # type: ignore
    radius : IntProperty(name="Radius", default=2, min=1) # type: ignore

    def execute(self, context):

        segment = self.segment
        angle_step = math.tau / segment
        radius = self.radius

        # 선택한 오브젝트
        origin_obj = bpy.context.active_object
        origin_obj.location = (0,0,0)


        for i in range(segment):

            current_angle_step = i * angle_step

            x = radius * math.sin(current_angle_step)
            y = radius * math.cos(current_angle_step)

            # 선택한 오브젝트를 복제한 후 원래의 오브젝트에 데이터 링크
            copy_obj = origin_obj.copy()
            # copy_obj.data = origin_obj.data.copy()
            copy_obj.location = (x, y, 0)

            # 메인 컬렉션에 복제된 오브젝트 링크
            bpy.context.collection.objects.link(copy_obj)

            # 데이터 링크
            copy_obj.select_set(True)
            origin_obj.select_set(True)
            bpy.context.view_layer.objects.active = origin_obj
            bpy.ops.object.make_links_data(type='OBDATA')
            bpy.ops.object.select_all(action='DESELECT')

        return {'FINISHED'}


# 머티리얼 추가 --------------------------------------------------------------------

class Add_Material(Operator):
    """선택한 오브젝트의 머티리얼을 오브젝트 이름으로 생성"""
    bl_label = "Material"
    bl_idname = "wm.add_material"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):

        # 선택한 오브젝트의 머티리얼 슬롯을 모두 제거
        obj = bpy.context.object
        obj.data.materials.clear()

        # 존재 여부 체크 후 머티리얼 할당
        mat = check_material_exist(obj.name)
        obj.data.materials.append(mat)

        return {'FINISHED'}

class SHADER_OP_Blend2Tex(Operator):
    bl_label = "2Tex"
    bl_idname = 'shader.blend2tex_operator'

    def execute(self, context):

        # 선택한 오브젝트의 머티리얼 슬롯을 모두 제거
        obj = bpy.context.object
        obj.data.materials.clear()

        # 머티리얼 노드 트리 기본
        material = check_material_exist(obj.name)
        node_tree = material.node_tree
        nodes = node_tree.nodes
        nodes.remove(nodes.get('Principled BSDF'))

    # 노드 리스트

        # 머티리얼 출력 노드
        node_output = nodes.get('Material Output')
        node_output.location = (1000, 0)

        # Texture Coordinate 노드
        node_TexCoord = nodes.new(type='ShaderNodeTexCoord')
        node_TexCoord.location = (-600, 0)
        node_TexCoord.object = obj

        # Mapping 노드 1
        node_Mapping_1 = nodes.new(type='ShaderNodeMapping')
        node_Mapping_1.location = (-370, 250)
        node_Mapping_1.inputs[3].default_value[0] = 2
        node_Mapping_1.inputs[3].default_value[1] = 2

        # Mapping 노드 2
        node_Mapping_2 = nodes.new(type='ShaderNodeMapping')
        node_Mapping_2.location = (-370, -250)
        node_Mapping_2.inputs[3].default_value[0] = 2
        node_Mapping_2.inputs[3].default_value[1] = 2

        # 이미지 텍스처 노드 1
        node_TexImage_1 = nodes.new(type='ShaderNodeTexImage')
        node_TexImage_1.location = (-70, 250)

        # 이미지 텍스처 노드 2
        node_TexImage_2 = nodes.new(type='ShaderNodeTexImage')
        node_TexImage_2.location = (-70, -250)

        # Principled BSDF 노드 1
        node_BSDF_1 = nodes.new(type='ShaderNodeBsdfPrincipled')
        node_BSDF_1.location = (230, 250)
        node_BSDF_1.inputs[12].default_value = 0

        # Principled BSDF 노드 2
        node_BSDF_2 = nodes.new(type='ShaderNodeBsdfPrincipled')
        node_BSDF_2.location = (230, -250)
        node_BSDF_2.inputs[12].default_value = 0

        # 믹스 셰이더 노드
        node_MixShader = nodes.new(type='ShaderNodeMixShader')
        node_MixShader.location = (730, 0)

        # VertexColor 노드
        node_VertexColor = nodes.new(type='ShaderNodeVertexColor')
        node_VertexColor.location = (230, 500)


        # 노드 연결
        node_tree.links.new(node_TexCoord.outputs['UV'], node_Mapping_1.inputs['Vector'])
        node_tree.links.new(node_TexCoord.outputs['UV'], node_Mapping_2.inputs['Vector'])
        node_tree.links.new(node_Mapping_1.outputs['Vector'], node_TexImage_1.inputs['Vector'])
        node_tree.links.new(node_Mapping_2.outputs['Vector'], node_TexImage_2.inputs['Vector'])
        node_tree.links.new(node_TexImage_1.outputs['Color'], node_BSDF_1.inputs['Base Color'])
        node_tree.links.new(node_TexImage_2.outputs['Color'], node_BSDF_2.inputs['Base Color'])
        node_tree.links.new(node_VertexColor.outputs['Color'], node_MixShader.inputs['Fac'])
        node_tree.links.new(node_BSDF_1.outputs['BSDF'], node_MixShader.inputs[1])
        node_tree.links.new(node_BSDF_2.outputs['BSDF'], node_MixShader.inputs[2])
        node_tree.links.new(node_MixShader.outputs[0], node_output.inputs['Surface'])

        # 머티리얼 할당
        obj.data.materials.append(material)

        return {'FINISHED'}


class SHADER_OP_Blend3Tex(Operator):
    bl_label = "3Tex"
    bl_idname = 'shader.blend3tex_operator'

    def execute(self, context):

        # 선택한 오브젝트의 머티리얼 슬롯을 모두 제거
        obj = bpy.context.object
        obj.data.materials.clear()

        # 머티리얼 노드 트리 기본
        material = check_material_exist(obj.name)
        node_tree = material.node_tree
        nodes = node_tree.nodes
        nodes.remove(nodes.get('Principled BSDF'))

        # 머티리얼 출력 노드
        node_output = nodes.get('Material Output')
        node_output.location = (1700, -250)

        # Texture Coordinate 노드
        node_TexCoord = nodes.new(type='ShaderNodeTexCoord')
        node_TexCoord.location = (-600, 0)
        node_TexCoord.object = obj

        # Mapping 노드 1
        node_Mapping_1 = nodes.new(type='ShaderNodeMapping')
        node_Mapping_1.location = (-370, 250)
        node_Mapping_1.inputs[3].default_value[0] = 2
        node_Mapping_1.inputs[3].default_value[1] = 2

        # Mapping 노드 2
        node_Mapping_2 = nodes.new(type='ShaderNodeMapping')
        node_Mapping_2.location = (-370, -250)
        node_Mapping_2.inputs[3].default_value[0] = 2
        node_Mapping_2.inputs[3].default_value[1] = 2

        # Mapping 노드 3
        node_Mapping_3 = nodes.new(type='ShaderNodeMapping')
        node_Mapping_3.location = (-370, -750)
        node_Mapping_3.inputs[3].default_value[0] = 2
        node_Mapping_3.inputs[3].default_value[1] = 2

        # 이미지 텍스처 노드 1
        node_TexImage_1 = nodes.new(type='ShaderNodeTexImage')
        node_TexImage_1.location = (-70, 250)

        # 이미지 텍스처 노드 2
        node_TexImage_2 = nodes.new(type='ShaderNodeTexImage')
        node_TexImage_2.location = (-70, -250)

        # 이미지 텍스처 노드 3
        node_TexImage_3 = nodes.new(type='ShaderNodeTexImage')
        node_TexImage_3.location = (-70, -750)

        # Principled BSDF 노드 1
        node_BSDF_1 = nodes.new(type='ShaderNodeBsdfPrincipled')
        node_BSDF_1.location = (230, 250)
        node_BSDF_1.inputs[12].default_value = 0

        # Principled BSDF 노드 2
        node_BSDF_2 = nodes.new(type='ShaderNodeBsdfPrincipled')
        node_BSDF_2.location = (230, -250)
        node_BSDF_2.inputs[12].default_value = 0

        # Principled BSDF 노드 3
        node_BSDF_3 = nodes.new(type='ShaderNodeBsdfPrincipled')
        node_BSDF_3.location = (230, -750)
        node_BSDF_3.inputs[12].default_value = 0

        # 믹스 셰이더 노드 1
        node_MixShader_1 = nodes.new(type='ShaderNodeMixShader')
        node_MixShader_1.location = (730, 0)

        # 믹스 셰이더 노드 2
        node_MixShader_2 = nodes.new(type='ShaderNodeMixShader')
        node_MixShader_2.location = (1230, -250)

        # 색상 속성 노드
        node_VertexColor = nodes.new(type='ShaderNodeVertexColor')
        node_VertexColor.location = (0, 500)

        # 색상 분리 노드
        node_SeparateColor = nodes.new(type='ShaderNodeSeparateColor')
        node_SeparateColor.location = (300, 500)


        # 노드 연결
        node_tree.links.new(node_TexCoord.outputs['UV'], node_Mapping_1.inputs['Vector'])
        node_tree.links.new(node_TexCoord.outputs['UV'], node_Mapping_2.inputs['Vector'])
        node_tree.links.new(node_TexCoord.outputs['UV'], node_Mapping_3.inputs['Vector'])
        node_tree.links.new(node_Mapping_1.outputs['Vector'], node_TexImage_1.inputs['Vector'])
        node_tree.links.new(node_Mapping_2.outputs['Vector'], node_TexImage_2.inputs['Vector'])
        node_tree.links.new(node_Mapping_3.outputs['Vector'], node_TexImage_3.inputs['Vector'])
        node_tree.links.new(node_TexImage_1.outputs['Color'], node_BSDF_1.inputs['Base Color'])
        node_tree.links.new(node_TexImage_2.outputs['Color'], node_BSDF_2.inputs['Base Color'])
        node_tree.links.new(node_TexImage_3.outputs['Color'], node_BSDF_3.inputs['Base Color'])
        node_tree.links.new(node_VertexColor.outputs['Color'], node_SeparateColor.inputs['Color'])
        node_tree.links.new(node_SeparateColor.outputs['Red'], node_MixShader_1.inputs['Fac'])
        node_tree.links.new(node_SeparateColor.outputs['Green'], node_MixShader_2.inputs['Fac'])
        node_tree.links.new(node_BSDF_1.outputs[0], node_MixShader_1.inputs[1])
        node_tree.links.new(node_BSDF_2.outputs[0], node_MixShader_1.inputs[2])
        node_tree.links.new(node_BSDF_3.outputs[0], node_MixShader_2.inputs[2])
        node_tree.links.new(node_MixShader_1.outputs[0], node_MixShader_2.inputs[1])
        node_tree.links.new(node_MixShader_2.outputs[0], node_output.inputs['Surface'])

        # 머티리얼 할당
        obj.data.materials.append(material)

        return {'FINISHED'}


class SHADER_OP_Blend4Tex(Operator):
    bl_label = "4Tex"
    bl_idname = 'shader.blend4tex_operator'

    def execute(self, context):

        # 선택한 오브젝트의 머티리얼 슬롯을 모두 제거
        obj = bpy.context.object
        obj.data.materials.clear()

        # 머티리얼 노드 트리 기본
        material = check_material_exist(obj.name)
        node_tree = material.node_tree
        nodes = node_tree.nodes
        nodes.remove(nodes.get('Principled BSDF'))

        # 머티리얼 출력 노드
        node_output = nodes.get('Material Output')
        node_output.location = (2200, -250)

        # Texture Coordinate 노드
        node_TexCoord = nodes.new(type='ShaderNodeTexCoord')
        node_TexCoord.location = (-600, 0)
        node_TexCoord.object = obj

        # Mapping 노드 1
        node_Mapping_1 = nodes.new(type='ShaderNodeMapping')
        node_Mapping_1.location = (-370, 250)
        node_Mapping_1.inputs[3].default_value[0] = 2
        node_Mapping_1.inputs[3].default_value[1] = 2

        # Mapping 노드 2
        node_Mapping_2 = nodes.new(type='ShaderNodeMapping')
        node_Mapping_2.location = (-370, -250)
        node_Mapping_2.inputs[3].default_value[0] = 2
        node_Mapping_2.inputs[3].default_value[1] = 2

        # Mapping 노드 3
        node_Mapping_3 = nodes.new(type='ShaderNodeMapping')
        node_Mapping_3.location = (-370, -750)
        node_Mapping_3.inputs[3].default_value[0] = 2
        node_Mapping_3.inputs[3].default_value[1] = 2

        # Mapping 노드 4
        node_Mapping_4 = nodes.new(type='ShaderNodeMapping')
        node_Mapping_4.location = (-370, -1250)
        node_Mapping_4.inputs[3].default_value[0] = 2
        node_Mapping_4.inputs[3].default_value[1] = 2

        # 이미지 텍스처 노드 1
        node_TexImage_1 = nodes.new(type='ShaderNodeTexImage')
        node_TexImage_1.location = (-70, 250)

        # 이미지 텍스처 노드 2
        node_TexImage_2 = nodes.new(type='ShaderNodeTexImage')
        node_TexImage_2.location = (-70, -250)

        # 이미지 텍스처 노드 3
        node_TexImage_3 = nodes.new(type='ShaderNodeTexImage')
        node_TexImage_3.location = (-70, -750)

        # 이미지 텍스처 노드 4
        node_TexImage_4 = nodes.new(type='ShaderNodeTexImage')
        node_TexImage_4.location = (-70, -1250)

        # Principled BSDF 노드 1
        node_BSDF_1 = nodes.new(type='ShaderNodeBsdfPrincipled')
        node_BSDF_1.location = (230, 250)
        node_BSDF_1.inputs[12].default_value = 0

        # Principled BSDF 노드 2
        node_BSDF_2 = nodes.new(type='ShaderNodeBsdfPrincipled')
        node_BSDF_2.location = (230, -250)
        node_BSDF_2.inputs[12].default_value = 0

        # Principled BSDF 노드 3
        node_BSDF_3 = nodes.new(type='ShaderNodeBsdfPrincipled')
        node_BSDF_3.location = (230, -750)
        node_BSDF_3.inputs[12].default_value = 0

        # Principled BSDF 노드 4
        node_BSDF_4 = nodes.new(type='ShaderNodeBsdfPrincipled')
        node_BSDF_4.location = (230, -1250)
        node_BSDF_4.inputs[12].default_value = 0

        # 믹스 셰이더 노드 1
        node_MixShader_1 = nodes.new(type='ShaderNodeMixShader')
        node_MixShader_1.location = (730, 0)

        # 믹스 셰이더 노드 2
        node_MixShader_2 = nodes.new(type='ShaderNodeMixShader')
        node_MixShader_2.location = (1230, -250)

        # 믹스 셰이더 노드 3
        node_MixShader_3 = nodes.new(type='ShaderNodeMixShader')
        node_MixShader_3.location = (1730, -500)

        # 색상 속성 노드
        node_VertexColor = nodes.new(type='ShaderNodeVertexColor')
        node_VertexColor.location = (0, 500)

        # 색상 분리 노드
        node_SeparateColor = nodes.new(type='ShaderNodeSeparateColor')
        node_SeparateColor.location = (300, 500)


        # 노드 연결
        node_tree.links.new(node_TexCoord.outputs['UV'], node_Mapping_1.inputs['Vector'])
        node_tree.links.new(node_TexCoord.outputs['UV'], node_Mapping_2.inputs['Vector'])
        node_tree.links.new(node_TexCoord.outputs['UV'], node_Mapping_3.inputs['Vector'])
        node_tree.links.new(node_TexCoord.outputs['UV'], node_Mapping_4.inputs['Vector'])
        node_tree.links.new(node_Mapping_1.outputs['Vector'], node_TexImage_1.inputs['Vector'])
        node_tree.links.new(node_Mapping_2.outputs['Vector'], node_TexImage_2.inputs['Vector'])
        node_tree.links.new(node_Mapping_3.outputs['Vector'], node_TexImage_3.inputs['Vector'])
        node_tree.links.new(node_Mapping_4.outputs['Vector'], node_TexImage_4.inputs['Vector'])
        node_tree.links.new(node_TexImage_1.outputs['Color'], node_BSDF_1.inputs['Base Color'])
        node_tree.links.new(node_TexImage_2.outputs['Color'], node_BSDF_2.inputs['Base Color'])
        node_tree.links.new(node_TexImage_3.outputs['Color'], node_BSDF_3.inputs['Base Color'])
        node_tree.links.new(node_TexImage_4.outputs['Color'], node_BSDF_4.inputs['Base Color'])
        node_tree.links.new(node_VertexColor.outputs['Color'], node_SeparateColor.inputs['Color'])
        node_tree.links.new(node_SeparateColor.outputs['Red'], node_MixShader_1.inputs['Fac'])
        node_tree.links.new(node_SeparateColor.outputs['Green'], node_MixShader_2.inputs['Fac'])
        node_tree.links.new(node_SeparateColor.outputs['Blue'], node_MixShader_3.inputs['Fac'])
        node_tree.links.new(node_BSDF_1.outputs[0], node_MixShader_1.inputs[1])
        node_tree.links.new(node_BSDF_2.outputs[0], node_MixShader_1.inputs[2])
        node_tree.links.new(node_BSDF_3.outputs[0], node_MixShader_2.inputs[2])
        node_tree.links.new(node_BSDF_4.outputs[0], node_MixShader_3.inputs[2])
        node_tree.links.new(node_MixShader_1.outputs[0], node_MixShader_2.inputs[1])
        node_tree.links.new(node_MixShader_2.outputs[0], node_MixShader_3.inputs[1])
        node_tree.links.new(node_MixShader_3.outputs[0], node_output.inputs['Surface'])

        # 머티리얼 할당
        obj.data.materials.append(material)

        return {'FINISHED'}


class SHADER_OP_TwoSideTex(Operator):
    bl_label = "TwoSideTex"
    bl_idname = 'shader.twosidetex_operator'

    def execute(self, context):

        # 선택한 오브젝트의 머티리얼 슬롯을 모두 제거
        obj = bpy.context.object
        obj.data.materials.clear()

        # 머티리얼 노드 트리 기본
        material = check_material_exist(obj.name)
        material.blend_method = 'CLIP'
        node_tree = material.node_tree
        nodes = node_tree.nodes
        nodes.remove(nodes.get('Principled BSDF'))

# 외부 노드 목록

        # 머티리얼 출력 노드
        material_output = nodes.get('Material Output')
        material_output.location = (100, 0)

        # 이미지 텍스처 노드 1
        node_TexImage_1 = nodes.new(type='ShaderNodeTexImage')
        node_TexImage_1.location = (-600, 200)

        # 이미지 텍스처 노드 2
        node_TexImage_2 = nodes.new(type='ShaderNodeTexImage')
        node_TexImage_2.location = (-600, -200)

# 노드 그룹 관련 ========================================

        two_side_tex_group = bpy.data.node_groups.get("TwoSideTexGroup")

        # 노드 그룹 데이터 블록이 존재한다면 제거합니다.
        if two_side_tex_group is not None:
            bpy.data.node_groups.remove(two_side_tex_group)

        # 'TwoSideTexGroup' 노드 그룹 데이터 블록 생성
        bpy.data.node_groups.new('TwoSideTexGroup', 'ShaderNodeTree')
        node_group = nodes.new(type='ShaderNodeGroup')
        node_group.node_tree = bpy.data.node_groups['TwoSideTexGroup']
        node_group.location = (-100, 0)
        group = node_group.node_tree



# 노드 그룹 내부 노드 목록 ===================================

        # Group Input 노드
        group_in = group.nodes.new(type='NodeGroupInput')
        group_in.location = (-600, 0)

        # Group Output 노드
        group_out = group.nodes.new(type='NodeGroupOutput')
        group_out.location = (1000, 0)

    # Group Input / Output 소켓 추가 ===================================
        group.interface.new_socket(name="Face Image", in_out='INPUT', socket_type='NodeSocketColor')
        group.interface.new_socket(name="Face Tint", in_out='INPUT', socket_type='NodeSocketColor')
        group.interface.new_socket(name="Face Alpha", in_out='INPUT', socket_type='NodeSocketFloat')
        group.interface.new_socket(name="Back Image", in_out='INPUT', socket_type='NodeSocketColor')
        group.interface.new_socket(name="Back Tint", in_out='INPUT', socket_type='NodeSocketColor')
        group.interface.new_socket(name="Back Alpha", in_out='INPUT', socket_type='NodeSocketFloat')
        group.interface.new_socket(name="Shader", in_out='OUTPUT', socket_type='NodeSocketShader')

        # 소켓 디폴트값 설정
        node_group.inputs.get('Face Tint').default_value = (1.0, 1.0, 1.0, 1.0)
        node_group.inputs.get('Back Tint').default_value = (1.0, 1.0, 1.0, 1.0)

        # Mix Color 노드 1
        node_MixColor_1 = group.nodes.new(type='ShaderNodeMix')
        node_MixColor_1.location = (-250, 200)
        node_MixColor_1.data_type = 'RGBA'
        node_MixColor_1.blend_type = 'MULTIPLY'

        # Mix Color 노드 2
        node_MixColor_2 = group.nodes.new(type='ShaderNodeMix')
        node_MixColor_2.location = (-250, -200)
        node_MixColor_2.data_type = 'RGBA'
        node_MixColor_2.blend_type = 'MULTIPLY'

        # Principled BSDF 노드 1
        node_BSDF_1 = group.nodes.new(type='ShaderNodeBsdfPrincipled')
        node_BSDF_1.location = (230, 250)
        node_BSDF_1.inputs[12].default_value = 0

        # Principled BSDF 노드 2
        node_BSDF_2 = group.nodes.new(type='ShaderNodeBsdfPrincipled')
        node_BSDF_2.location = (230, -250)
        node_BSDF_2.inputs[12].default_value = 0

        # 믹스 셰이더 노드
        node_MixShader = group.nodes.new(type='ShaderNodeMixShader')
        node_MixShader.location = (730, 0)

        # Geometry 노드
        node_Geometry = group.nodes.new(type='ShaderNodeNewGeometry')
        node_Geometry.location = (0, 90)

    # 노드 링크 ===============================================================================
        group.links.new(group_in.outputs['Face Image'], node_MixColor_1.inputs['A'])
        group.links.new(group_in.outputs['Face Tint'], node_MixColor_1.inputs['B'])
        group.links.new(group_in.outputs['Face Alpha'], node_BSDF_1.inputs['Alpha'])

        group.links.new(group_in.outputs['Back Image'], node_MixColor_2.inputs['A'])
        group.links.new(group_in.outputs['Back Tint'], node_MixColor_2.inputs['B'])
        group.links.new(group_in.outputs['Back Alpha'], node_BSDF_2.inputs['Alpha'])

        group.links.new(node_MixColor_1.outputs['Result'], node_BSDF_1.inputs['Base Color'])  # BSDF 1
        group.links.new(node_MixColor_2.outputs['Result'], node_BSDF_2.inputs['Base Color'])  # BSDF 2
        group.links.new(node_Geometry.outputs['Backfacing'], node_MixShader.inputs['Fac']) # Geometry
        group.links.new(node_BSDF_1.outputs['BSDF'], node_MixShader.inputs[1])   # Mix Shader
        group.links.new(node_BSDF_2.outputs['BSDF'], node_MixShader.inputs[2])   # Mix Shader
        group.links.new(node_MixShader.outputs[0], group_out.inputs[0])     # Group Output

        # 머티리얼 출력 노드에 Node Group 적용
        material.node_tree.links.new(node_TexImage_1.outputs['Color'], node_group.inputs['Face Image']) # Image 1
        material.node_tree.links.new(node_TexImage_1.outputs['Alpha'], node_group.inputs['Face Alpha']) # Alpha 1
        material.node_tree.links.new(node_TexImage_2.outputs['Color'], node_group.inputs['Back Image']) # Image 2
        material.node_tree.links.new(node_TexImage_2.outputs['Alpha'], node_group.inputs['Back Alpha']) # Alpha 2
        material.node_tree.links.new(node_group.outputs[0], material_output.inputs[0]) # Material Output

        # 머티리얼 할당
        obj.data.materials.append(material)

        return {'FINISHED'}


class PALETTE_OP_RGB(Operator):
    bl_label = "RGB palette"
    bl_idname = 'palette.rgb_operator'

    def execute(self, context):

        palette_name = "RGB Palette"

        for palette in bpy.data.palettes:
            if palette.name == palette_name:
                bpy.data.palettes.remove(palette)

        # 신규 팔레트 생성 및 컬러 등록
        palette = bpy.data.palettes.new(palette_name)
        palette.colors.new().color = (1.0, 0.0, 0.0) # R
        palette.colors.new().color = (0.0, 1.0, 0.0) # G
        palette.colors.new().color = (0.0, 0.0, 1.0) # B
        palette.colors.new().color = (0.0, 0.0, 0.0) # Black
        palette.colors.new().color = (1.0, 1.0, 1.0) # White

        # 객체의 모드를 'VERTEX_PAINT'로 변경합니다.
        bpy.ops.object.mode_set(mode='VERTEX_PAINT')

        return {'FINISHED'}

# 래티스 추가 --------------------------------------------------------------------

class Add_Lattice(Operator):
    """선택한 오브젝트를 기준으로 Lattice를 생성합니다."""
    bl_label = "Lattice"
    bl_idname = "wm.add_lattice"
    bl_options = {'REGISTER', 'UNDO'}

    lattice_resolution: bpy.props.IntProperty(name="Resolution", default=0, min=0, max=10) # type: ignore

    def execute(self, context):
        # 래티스 해상도 --------------------------

        resolution = self.lattice_resolution

        # ---------------------------------------------

        selObj = bpy.context.selected_objects

        # 전체 선택 해제
        bpy.ops.object.select_all(action='DESELECT')

        for obj in selObj:

            obj_loc = bpy.data.objects[obj.name].location

        # 선택 오브젝트의 위치와 스케일을 기준으로 래티스 생성
            bpy.ops.object.add(type='LATTICE', enter_editmode=False, align='WORLD', location=obj_loc, scale=(1, 1, 1))
            curObj = bpy.context.selected_objects[0]
            curObj.name = obj.name + "_Lattice"
            latticeName = curObj.name
            curObj.data.name = latticeName
            size = obj.dimensions
            curObj.scale = (size[0] + 0.1, size[1] + 0.1, size[2] + 0.1)

        # 래티스 해상도
            latticeObj = bpy.context.selected_objects[0]
            latticeObj.data.points_u = 2 + resolution
            latticeObj.data.points_v = 2 + resolution
            latticeObj.data.points_w = 2 + resolution

            bpy.ops.object.select_all(action='DESELECT')

        # "Lattice" 모디파이어를 추가하고 "Lattice" 오브젝트 연결
            obj.select_set(True)
            selObj = bpy.context.selected_objects[0]
            selObj.modifiers.new(name='Lattice', type='LATTICE')
            selObj.modifiers["Lattice"].object = bpy.data.objects[latticeName]

            bpy.ops.object.select_all(action='DESELECT')

        return {'FINISHED'}


# 텍스트 추가 연산자 -----------------------------------------------------------------

class Add_Text(Operator):
    """Open the Text Tool Dialog Box"""
    bl_label = "Text"
    bl_idname = "wm.add_text"
    bl_options = {'REGISTER', 'UNDO'}

    text : StringProperty(name="Enter Text", default="") # type: ignore
    scale : FloatProperty(name= "Scale", default= 1) # type: ignore
    rotation : BoolProperty(name= "Z up", default= False) # type: ignore
    center : BoolProperty(name= "Center Origin", default= False) # type: ignore
    extrude : BoolProperty(name= "Extrude", default= False) # type: ignore
    extrude_amount : FloatProperty(name= "Extrude Amount", default= 0.06) # type: ignore

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self)

    def draw(self, context):

        layout = self.layout

        layout.prop(self, "text")
        layout.prop(self, "scale")

        layout.separator(factor= 1)

        box = layout.box()

        row = box.row()
        row.prop(self, "rotation")
        if self.rotation == True:
            row.label(text= "Orientation: Z up", icon= 'EMPTY_SINGLE_ARROW')
        elif self.rotation == False:
            row.label(text= "Orientation: Default", icon= 'ARROW_LEFTRIGHT')


        row = box.row()
        row.prop(self, "center")
        if self.center == True:
            row.label(text= "Align: Center", icon= 'ALIGN_CENTER')
        elif self.center == False:
            row.label(text= "Align: Left", icon= 'ALIGN_LEFT')

        row = box.row()
        row.prop(self, "extrude")
        if self.extrude == True:
            row.prop(self, "extrude_amount")

    def execute(self, context):

        text = self.text
        scale = self.scale
        center = self.center
        extrude = self.extrude
        extrude_amount = self.extrude_amount
        rotation = self.rotation

        bpy.ops.object.text_add(enter_editmode=True)
        bpy.ops.font.delete(type='PREVIOUS_WORD')
        bpy.ops.font.text_insert(text= text)
        bpy.ops.object.editmode_toggle()
        bpy.context.object.data.size = scale

        if rotation == True:
            bpy.context.object.rotation_euler[0] = 1.5708

        if extrude == True:
            bpy.context.object.data.extrude = extrude_amount

        if center == True:
            bpy.context.object.data.align_x = 'CENTER'
            bpy.context.object.data.align_y = 'CENTER'


        return {'FINISHED'}


# Mirror 모디파이어
class Add_Mirror_X_Modifier(Operator):
    bl_idname = "wm.add_mirror_x_modifier"
    bl_label = "X"

    def execute(self, context):
        # 선택한 오브젝트 가져오기
        obj = bpy.context.object

        # Edit 모드로 전환
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='EDIT')

        # BMesh 생성
        bm = bmesh.from_edit_mesh(obj.data)

        # 0 < x < 0.01 사이의 버텍스는 모두 0으로 이동
        for vertex in bm.verts:
            if 0 < vertex.co.x < 0.01:
                vertex.co.x = 0

        # 양수 X 영역만 제거하고, 제거할 버텍스가 없어도 미러 추가를 계속 진행
        vertices_to_delete = [vertex for vertex in bm.verts if vertex.co.x > 0.0]
        if vertices_to_delete:
            bmesh.ops.delete(
                bm,
                geom=vertices_to_delete,
                context='VERTS'
            )

        # BMesh 데이터를 오브젝트에 적용
        bmesh.update_edit_mesh(obj.data)

        #Object 모드로 전환
        bpy.ops.object.mode_set(mode='OBJECT')

        # 모디파이어 리스트
        modifiers = obj.modifiers

        for modifier in modifiers:
            if modifier.type == 'MIRROR':
                modifiers.remove(modifier)

        # Mirror 모디파이어 추가
        mirror_modifier = obj.modifiers.new("Mirror", 'MIRROR')
        mirror_modifier.use_axis[0] = True
        mirror_modifier.use_axis[1] = False
        mirror_modifier.use_axis[2] = False

        return {'FINISHED'}

# Mirror 모디파이어
class Add_Mirror_Y_Modifier(Operator):
    bl_idname = "wm.add_mirror_y_modifier"
    bl_label = "Y"

    def execute(self, context):
        # 선택한 오브젝트 가져오기
        obj = bpy.context.object

        # Edit 모드로 전환
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='EDIT')

        # BMesh 생성
        bm = bmesh.from_edit_mesh(obj.data)

        # -0.01 < y < 0 사이의 버텍스는 모두 0으로 이동
        for vertex in bm.verts:
            if -0.01 < vertex.co.y < 0:
                vertex.co.y = 0

        # 음수 Y 영역만 제거하고, 제거할 버텍스가 없어도 미러 추가를 계속 진행
        vertices_to_delete = [vertex for vertex in bm.verts if vertex.co.y < 0.0]
        if vertices_to_delete:
            bmesh.ops.delete(
                bm,
                geom=vertices_to_delete,
                context='VERTS'
            )

        # BMesh 데이터를 오브젝트에 적용
        bmesh.update_edit_mesh(obj.data)

        #Object 모드로 전환
        bpy.ops.object.mode_set(mode='OBJECT')

        # 모디파이어 리스트
        modifiers = obj.modifiers

        for modifier in modifiers:
            if modifier.type == 'MIRROR':
                modifiers.remove(modifier)

        # Mirror 모디파이어 추가
        mirror_modifier = obj.modifiers.new("Mirror", 'MIRROR')
        mirror_modifier.use_axis[0] = False
        mirror_modifier.use_axis[1] = True
        mirror_modifier.use_axis[2] = False

        return {'FINISHED'}

# Mirror 모디파이어
class Add_Mirror_Z_Modifier(Operator):
    bl_idname = "wm.add_mirror_z_modifier"
    bl_label = "Z"

    def execute(self, context):
        # 선택한 오브젝트 가져오기
        obj = bpy.context.object

        # Edit 모드로 전환
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='EDIT')

        # BMesh 생성
        bm = bmesh.from_edit_mesh(obj.data)

        # -0.01 < z < 0 사이의 버텍스는 모두 0으로 이동
        for vertex in bm.verts:
            if -0.01 < vertex.co.z < 0:
                vertex.co.z = 0

        # 음수 Z 영역만 제거하고, 제거할 버텍스가 없어도 미러 추가를 계속 진행
        vertices_to_delete = [vertex for vertex in bm.verts if vertex.co.z < 0.0]
        if vertices_to_delete:
            bmesh.ops.delete(
                bm,
                geom=vertices_to_delete,
                context='VERTS'
            )

        # BMesh 데이터를 오브젝트에 적용
        bmesh.update_edit_mesh(obj.data)

        #Object 모드로 전환
        bpy.ops.object.mode_set(mode='OBJECT')

        # 모디파이어 리스트
        modifiers = obj.modifiers

        for modifier in modifiers:
            if modifier.type == 'MIRROR':
                modifiers.remove(modifier)

        # Mirror 모디파이어 추가
        mirror_modifier = obj.modifiers.new("Mirror", 'MIRROR')
        mirror_modifier.use_axis[0] = False
        mirror_modifier.use_axis[1] = False
        mirror_modifier.use_axis[2] = True

        return {'FINISHED'}


classes = [
    OBJECT_PT_WoodyTool,
    # OBJECT_PT_Spacing,
    # OBJECT_PT_Mirror_Modifier,
    # Add_Cylinder_6,
    # Add_Cylinder_8,
    # Add_Cylinder_10,
    # Add_Cylinder_12,
    CircleArray,
    Add_Material,
    SHADER_OP_Blend2Tex,
    SHADER_OP_Blend3Tex,
    SHADER_OP_Blend4Tex,
    SHADER_OP_TwoSideTex,
    # PALETTE_OP_RGB,
    Add_Lattice,
    Add_Mirror_X_Modifier,
    Add_Mirror_Y_Modifier,
    Add_Mirror_Z_Modifier,
    # Add_Text
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
