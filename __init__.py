# SPDX-License-Identifier: GPL-3.0-or-later

bl_info = {
    "name": "CatTools",
    "author": "Woody",
    "version": (1, 8, 1),
    "blender": (4, 2, 0),
    "location": "View3D > UI > CatTools 탭",
    "description": "CAT 블록 모델링에 유용한 도구 모음",
    "warning": "",
    "doc_url": "",
    "category": "3D View",
}

import bpy, math, bmesh, bisect
from typing import Set
from bpy.types import Context, Panel, Operator
from bpy.props import StringProperty, FloatProperty, BoolProperty, IntProperty, EnumProperty
from mathutils import Euler, Matrix, Quaternion, Vector
from mathutils.bvhtree import BVHTree
from mathutils.geometry import tessellate_polygon

# Transform / Align 행의 (기본 라벨, 축약 라벨, 대상) — 3x3 축약 그리드
TRANSFORM_ROWS = (
    ("Loc", "L", "location"),
    ("Rot", "R", "rotation_euler"),
    ("Sca", "S", "scale"),
)
ALIGN_ROWS = (
    ("Loc", "L", 'LOCATION'),
    ("Rot", "R", 'ROTATION'),
    ("Sca", "S", 'SCALE'),
)
ALIGN_BUTTONS = (
    ('X', "X"),
    ('Y', "Y"),
    ('Z', "Z"),
    ('ALL', "All"),
)
# 행 라벨 칸의 고정 폭(UI 단위). 비율 분할과 달리 사이드바 폭이 변해도 여백이
# 늘어나지 않고, 라벨이 잘리지 않는 최소값으로 맞춘다.
TRANSFORM_LABEL_UNITS = 1.5
TRANSFORM_COMPACT_LABEL_UNITS = 0.8
# 사이드바 논리 폭이 이 값 미만이면 라벨을 한 글자로 축약한다.
# 기본 사이드바 폭은 약 280 논리 픽셀이므로 기본 상태에서는 축약되지 않는다.
TRANSFORM_COMPACT_WIDTH = 200

CATOON_BASE_IMAGE_NAME = "CatoonBaseColor"

# 사이드바 탭 이름. 패널 bl_category와 N 키 오버라이드가 같은 값을 공유한다.
CAT_CATEGORY = "CatTools"

# Catoon 셀셰이딩 노드 그룹의 (소켓명, 타입, 기본값).
# Light Color를 흰색으로 두어 밝은 면은 텍스처 색이 그대로 살아나고,
# 그림자 면은 Shadow Color를 곱해 만화적인 2톤이 된다.
CATOON_SOCKETS = (
    ("Base Color", 'NodeSocketColor', (1.0, 1.0, 1.0, 1.0)),
    ("Alpha", 'NodeSocketFloat', 1.0),
    ("Light Color", 'NodeSocketColor', (1.0, 1.0, 1.0, 1.0)),
    ("Shadow Color", 'NodeSocketColor', (0.45, 0.5, 0.62, 1.0)),
    ("Threshold", 'NodeSocketFloat', 0.5),
    ("Softness", 'NodeSocketFloat', 0.0),
)

ALIGN_AXIS_INDICES = {'X': 0, 'Y': 1, 'Z': 2}
ALIGN_PROPERTIES = {
    'LOCATION': "location",
    'ROTATION': "rotation_euler",
    'SCALE': "scale",
}

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


# 이미지를 지정하지 않은 Image Texture 노드는 검은색으로 평가된다. 그 값이 텍스처
# 색으로 곱해지면 머티리얼 전체가 검게 나오므로, 흰색 기본 이미지를 넣어 텍스처를
# 지정하기 전에도 2톤 음영이 보이게 한다.
def catoon_base_image():
    image = bpy.data.images.get(CATOON_BASE_IMAGE_NAME)
    if image is None or image.source != 'GENERATED':
        image = bpy.data.images.new(CATOON_BASE_IMAGE_NAME, width=4, height=4)
    image.generated_color = (1.0, 1.0, 1.0, 1.0)
    return image


# ShaderNodeMix/MapRange는 data_type마다 같은 이름의 소켓을 중복으로 들고 있어
# 이름이나 인덱스로 찾으면 비활성 소켓이 잡힌다. 활성 소켓만 골라 쓴다.
def enabled_socket(sockets, name):
    for socket in sockets:
        if socket.name == name and socket.enabled:
            return socket
    raise KeyError(f"활성 소켓을 찾을 수 없습니다: {name}")


# 사이드바가 좁아지면 라벨을 한 글자로 줄이고 라벨 칸 폭도 함께 좁힌다.
def transform_label_metrics(context) -> tuple[bool, float]:
    region = context.region
    ui_scale = context.preferences.system.ui_scale or 1.0
    if region is None:
        return False, TRANSFORM_LABEL_UNITS
    if region.width / ui_scale < TRANSFORM_COMPACT_WIDTH:
        return True, TRANSFORM_COMPACT_LABEL_UNITS
    return False, TRANSFORM_LABEL_UNITS


# rotation_mode가 오일러가 아니어도 정렬이 조용히 무시되지 않도록 오일러로 환산
def rotation_as_euler(obj) -> Euler:
    if obj.rotation_mode == 'QUATERNION':
        return obj.rotation_quaternion.to_euler('XYZ')
    if obj.rotation_mode == 'AXIS_ANGLE':
        angle, x, y, z = obj.rotation_axis_angle
        return Quaternion((x, y, z), angle).to_euler('XYZ')
    return obj.rotation_euler.copy()


# rotation_as_euler로 얻어 수정한 오일러 값을 원래 rotation_mode로 되돌려 적용
def apply_rotation_euler(obj, euler: Euler) -> None:
    if obj.rotation_mode == 'QUATERNION':
        obj.rotation_quaternion = euler.to_quaternion()
    elif obj.rotation_mode == 'AXIS_ANGLE':
        axis, angle = euler.to_quaternion().to_axis_angle()
        obj.rotation_axis_angle = (angle, axis.x, axis.y, axis.z)
    else:
        obj.rotation_euler = euler


# ---------------------------------------------------------------------------
# Edit 모드 선택 요소(점/선/면) Transform
# 선/면 선택도 select flush로 정점 선택에 반영되므로, 선택 정점 집합 하나로 처리한다.
# 값은 모두 월드 좌표 기준이며 여러 오브젝트를 함께 편집 중이어도 한 번에 다룬다.
# ---------------------------------------------------------------------------

# 요소에는 회전/스케일 절대값이 없으므로, 같은 선택에서 누적 입력한 값을 보관해
# 새 입력과의 차이만큼만 적용한다. 선택이 바뀌거나 Undo하면 초기화된다.
_edit_transform_state = {"signature": None, "rotation": (0.0, 0.0, 0.0), "scale": (1.0, 1.0, 1.0)}


def edit_mesh_targets(context):
    """선택 요소 Transform 대상이 되는 (오브젝트, BMesh, 선택 정점 목록)을 반환합니다."""
    if context.mode != 'EDIT_MESH':
        return []
    # 메시를 공유하는 오브젝트가 있어도 같은 데이터를 두 번 변형하지 않도록 unique_data 사용
    objects = getattr(context, "objects_in_mode_unique_data", None) or [context.edit_object]
    targets = []
    for obj in objects:
        if obj is None or obj.type != 'MESH':
            continue
        bm = bmesh.from_edit_mesh(obj.data)
        verts = [v for v in bm.verts if v.select and not v.hide]
        if verts:
            targets.append((obj, bm, verts))
    return targets


def edit_selection_median(targets):
    total = Vector()
    count = 0
    for obj, _bm, verts in targets:
        matrix = obj.matrix_world
        for vert in verts:
            total += matrix @ vert.co
        count += len(verts)
    return total / count if count else None


def edit_selection_signature(targets):
    signature = []
    for obj, bm, verts in targets:
        bm.verts.index_update()
        signature.append((obj.name, len(bm.verts), tuple(v.index for v in verts)))
    return tuple(signature)


def edit_transform_state(targets):
    signature = edit_selection_signature(targets)
    if _edit_transform_state["signature"] != signature:
        _edit_transform_state.update(signature=signature, rotation=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0))
    return _edit_transform_state


def apply_edit_world_matrix(targets, world_matrix: Matrix) -> None:
    """월드 공간 변환 행렬을 각 오브젝트 로컬 공간으로 환산해 선택 정점에 적용합니다."""
    for obj, _bm, verts in targets:
        matrix = obj.matrix_world
        local = matrix.inverted_safe() @ world_matrix @ matrix
        for vert in verts:
            vert.co = local @ vert.co
        bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)


def pivot_matrix(pivot: Vector, matrix: Matrix) -> Matrix:
    return Matrix.Translation(pivot) @ matrix @ Matrix.Translation(-pivot)


def _get_edit_location(_self):
    median = edit_selection_median(edit_mesh_targets(bpy.context))
    return tuple(median) if median is not None else (0.0, 0.0, 0.0)


def _set_edit_location(_self, value):
    targets = edit_mesh_targets(bpy.context)
    median = edit_selection_median(targets)
    if median is None:
        return
    apply_edit_world_matrix(targets, Matrix.Translation(Vector(value) - median))
    # 이동은 선택 정점 인덱스를 바꾸지 않으므로 누적 회전/스케일은 유지된다.


def _get_edit_rotation(_self):
    targets = edit_mesh_targets(bpy.context)
    return edit_transform_state(targets)["rotation"] if targets else (0.0, 0.0, 0.0)


def _set_edit_rotation(_self, value):
    targets = edit_mesh_targets(bpy.context)
    median = edit_selection_median(targets)
    if median is None:
        return
    state = edit_transform_state(targets)
    old = Euler(state["rotation"], 'XYZ').to_matrix()
    new = Euler(value, 'XYZ').to_matrix()
    delta = (new @ old.transposed()).to_4x4()
    apply_edit_world_matrix(targets, pivot_matrix(median, delta))
    state["rotation"] = tuple(value)


def _get_edit_scale(_self):
    targets = edit_mesh_targets(bpy.context)
    return edit_transform_state(targets)["scale"] if targets else (1.0, 1.0, 1.0)


def _set_edit_scale(_self, value):
    targets = edit_mesh_targets(bpy.context)
    median = edit_selection_median(targets)
    if median is None:
        return
    state = edit_transform_state(targets)
    old = state["scale"]
    # 0으로 눌린 축은 비율을 되돌릴 수 없으므로 해당 축은 건너뛰고 이전 값을 유지한다.
    factors = [new / prev if abs(prev) > 1e-9 else 1.0 for new, prev in zip(value, old)]
    delta = Matrix.Diagonal((*factors, 1.0))
    apply_edit_world_matrix(targets, pivot_matrix(median, delta))
    state["scale"] = tuple(new if abs(prev) > 1e-9 else prev for new, prev in zip(value, old))


@bpy.app.handlers.persistent
def _reset_edit_transform_state(*_args) -> None:
    # Undo/Redo 후 메시와 누적값이 어긋나지 않도록 초기화
    _edit_transform_state["signature"] = None


EDIT_TRANSFORM_PROPERTIES = {
    "cat_edit_location": lambda: bpy.props.FloatVectorProperty(
        name="Location", description="선택 요소의 중앙값 위치(월드)", subtype='TRANSLATION',
        unit='LENGTH', size=3, get=_get_edit_location, set=_set_edit_location,
    ),
    "cat_edit_rotation": lambda: bpy.props.FloatVectorProperty(
        name="Rotation", description="선택 요소를 중앙값 기준으로 회전(월드 축)", subtype='EULER',
        unit='ROTATION', size=3, get=_get_edit_rotation, set=_set_edit_rotation,
    ),
    "cat_edit_scale": lambda: bpy.props.FloatVectorProperty(
        name="Scale", description="선택 요소를 중앙값 기준으로 스케일(월드 축)", subtype='XYZ',
        size=3, get=_get_edit_scale, set=_set_edit_scale,
    ),
}
EDIT_TRANSFORM_ROWS = (
    ("Loc", "L", "cat_edit_location"),
    ("Rot", "R", "cat_edit_rotation"),
    ("Sca", "S", "cat_edit_scale"),
)
EDIT_RESET_HANDLERS = (bpy.app.handlers.undo_post, bpy.app.handlers.redo_post)


# 커서의 rotation_mode에 맞는 회전 속성을 골라, 쿼터니언/축-각도 모드에서도 실제 값을 편집하게 한다.
def cursor_rows(cursor):
    if cursor.rotation_mode == 'QUATERNION':
        rotation_property = "rotation_quaternion"
    elif cursor.rotation_mode == 'AXIS_ANGLE':
        rotation_property = "rotation_axis_angle"
    else:
        rotation_property = "rotation_euler"
    return (
        ("Loc", "L", "location"),
        ("Rot", "R", rotation_property),
    )


# 메인 패널: 사이드바 메뉴 UI 설정
class OBJECT_PT_WoodyTool(Panel):
    bl_label = "CatTools"
    bl_idname = "OBJECT_PT_woodytool"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CAT_CATEGORY

    def draw(self, context):
        layout = self.layout

    # 변환
        selected_object = context.object

        compact, label_units = transform_label_metrics(context)

        # Transform 축약 필드: 행 라벨 + 한 줄 3열로 공간을 최소화
        layout.label(text="Transform :", icon="OUTLINER_DATA_EMPTY")
        if context.mode == 'EDIT_MESH':
            self.draw_edit_transform(context, layout, compact, label_units)
        elif selected_object:
            column = layout.column(align=True)
            for full_label, short_label, property_name in TRANSFORM_ROWS:
                row = column.row(align=True)
                label_column = row.column(align=True)
                label_column.ui_units_x = label_units
                label_column.label(text=short_label if compact else full_label)
                fields = row.row(align=True)
                for index in range(3):
                    fields.prop(selected_object, property_name, index=index, text="")
        else:
            layout.label(text="오브젝트를 선택하세요.")

        layout.separator(factor=1)

    # 3D 커서: View 탭의 3D Cursor 위치/회전을 Transform과 같은 축약 그리드로 표시
        layout.label(text="3D Cursor :", icon="PIVOT_CURSOR")
        cursor = context.scene.cursor
        column = layout.column(align=True)
        for full_label, short_label, property_name in cursor_rows(cursor):
            row = column.row(align=True)
            label_column = row.column(align=True)
            label_column.ui_units_x = label_units
            label_column.label(text=short_label if compact else full_label)
            fields = row.row(align=True)
            for index in range(len(getattr(cursor, property_name))):
                fields.prop(cursor, property_name, index=index, text="")

        layout.separator(factor=1)

    # 정렬: 활성 오브젝트를 기준으로 선택 오브젝트를 맞춤
        layout.label(text="Align :", icon="SNAP_ON")
        column = layout.column(align=True)
        for full_label, short_label, align_mode in ALIGN_ROWS:
            row = column.row(align=True)
            label_column = row.column(align=True)
            label_column.ui_units_x = label_units
            label_column.label(text=short_label if compact else full_label)
            buttons = row.row(align=True)
            for axis, axis_label in ALIGN_BUTTONS:
                operator = buttons.operator(
                    OBJECT_OT_CatAlign.bl_idname, text=axis_label
                )
                operator.mode = align_mode
                operator.axis = axis

        layout.separator(factor=1)

    # 선택: 기준과 같은 축 값(X·Y·Z), 또는 기준보다 양(+)/음(-) 방향에 있는 대상을 모두 선택
        layout.label(text="Select :", icon="RESTRICT_SELECT_OFF")
        column = layout.column(align=True)
        for direction, prefix in (('SAME', ""), ('POSITIVE', "+"), ('NEGATIVE', "-")):
            row = column.row(align=True)
            for axis in ('X', 'Y', 'Z'):
                operator = row.operator(
                    OBJECT_OT_CatSelectSamePivot.bl_idname, text=f"{prefix}{axis}"
                )
                operator.axis = axis
                operator.direction = direction
        # 노멀 방향(면이 회전돼 있어도 같은 방향을 보는 면)이 같은 대상 선택
        # 은면(어느 방향에서도 보이지 않는 면) 선택은 Edit 모드에서만 동작한다.
        row = column.row(align=True)
        row.operator(OBJECT_OT_CatSelectSameNormal.bl_idname, text="Normal")
        row.operator(OBJECT_OT_CatSelectHiddenFaces.bl_idname, text="Hidden")

        layout.separator(factor=1)

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
        row.operator(SHADER_OP_Catoon.bl_idname, text= SHADER_OP_Catoon.bl_label)

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

        # Mirror 모디파이어 추가 버튼: 축마다 남길 쪽(-/+)을 고른다.
        column = layout.column(align=True)
        for side, sign, _description in reversed(MIRROR_SIDE_ITEMS):
            row = column.row(align=True)
            for operator_class in (Add_Mirror_X_Modifier, Add_Mirror_Y_Modifier, Add_Mirror_Z_Modifier):
                operator = row.operator(
                    operator_class.bl_idname,
                    text=f"{sign}{operator_class.bl_label}",
                    icon="MOD_MIRROR",
                )
                operator.side = side


        layout.separator(factor=1)

        # 텍스트 추가
        # layout.label(text="Text :", icon = 'OUTLINER_OB_FONT')
        # layout.operator(Add_Text.bl_idname, text= Add_Text.bl_label)


    # Edit 모드: 선택한 점/선/면의 중앙값 위치와 중앙값 기준 회전/스케일
    @staticmethod
    def draw_edit_transform(context, layout, compact, label_units):
        targets = edit_mesh_targets(context)
        if not targets:
            layout.label(text="점, 선, 면을 선택하세요.")
            return
        count = sum(len(verts) for _obj, _bm, verts in targets)
        layout.label(text=f"{'Vertex' if count == 1 else 'Median'} (Global) · {count} verts")
        column = layout.column(align=True)
        for full_label, short_label, property_name in EDIT_TRANSFORM_ROWS:
            row = column.row(align=True)
            label_column = row.column(align=True)
            label_column.ui_units_x = label_units
            label_column.label(text=short_label if compact else full_label)
            fields = row.row(align=True)
            for index in range(3):
                fields.prop(context.scene, property_name, index=index, text="")


# 텍스트 패널: 텍스트 생성 후 간격 옵션 ----------------------------------------

class OBJECT_PT_Spacing(Panel):
    bl_label = "Text Spacing"
    bl_idname = "OBJECT_PT_spacing"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CAT_CATEGORY
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
    bl_category = CAT_CATEGORY
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
    bl_label = "TwoSide"
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


class SHADER_OP_Catoon(Operator):
    """텍스처 색을 그대로 살리면서 2톤 만화풍 그림자를 만드는 셀셰이딩 머티리얼"""
    bl_label = "Catoon"
    bl_idname = 'shader.catoon_operator'

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
        material_output.location = (150, 0)

        # 이미지 텍스처 노드 (사용자가 카툰 텍스처를 지정, 기본은 흰색)
        node_TexImage = nodes.new(type='ShaderNodeTexImage')
        node_TexImage.location = (-700, 100)
        node_TexImage.image = catoon_base_image()

# 노드 그룹 관련 ========================================

        catoon_group = bpy.data.node_groups.get("CatoonGroup")

        # 노드 그룹 데이터 블록이 존재한다면 제거합니다.
        if catoon_group is not None:
            bpy.data.node_groups.remove(catoon_group)

        # 'CatoonGroup' 노드 그룹 데이터 블록 생성
        bpy.data.node_groups.new('CatoonGroup', 'ShaderNodeTree')
        node_group = nodes.new(type='ShaderNodeGroup')
        node_group.node_tree = bpy.data.node_groups['CatoonGroup']
        node_group.location = (-200, 0)
        group = node_group.node_tree

# 노드 그룹 내부 노드 목록 ===================================

        # Group Input 노드
        group_in = group.nodes.new(type='NodeGroupInput')
        group_in.location = (-900, 0)

        # Group Output 노드
        group_out = group.nodes.new(type='NodeGroupOutput')
        group_out.location = (900, 0)

    # Group Input / Output 소켓 추가 ===================================
        for socket_name, socket_type, default_value in CATOON_SOCKETS:
            interface_socket = group.interface.new_socket(
                name=socket_name, in_out='INPUT', socket_type=socket_type
            )
            interface_socket.default_value = default_value
            if socket_type == 'NodeSocketFloat':
                interface_socket.min_value = 0.0
                interface_socket.max_value = 1.0
        group.interface.new_socket(name="Shader", in_out='OUTPUT', socket_type='NodeSocketShader')

        # 노드 그룹 인스턴스는 소켓이 추가되기 전에 만들어져 인터페이스 기본값을
        # 물려받지 못한다. 인스턴스 소켓에 기본값을 직접 넣어야 검은색으로 시작하지 않는다.
        for socket_name, _socket_type, default_value in CATOON_SOCKETS:
            node_group.inputs[socket_name].default_value = default_value

        # Diffuse BSDF 노드: 순수한 램버트 음영만 뽑기 위해 흰색으로 고정
        node_Diffuse = group.nodes.new(type='ShaderNodeBsdfDiffuse')
        node_Diffuse.location = (-700, -250)
        node_Diffuse.inputs['Color'].default_value = (1.0, 1.0, 1.0, 1.0)

        # Shader to RGB 노드: 조명 결과를 색으로 변환 (EEVEE 전용)
        node_ShaderToRGB = group.nodes.new(type='ShaderNodeShaderToRGB')
        node_ShaderToRGB.location = (-500, -250)

        # RGB to BW 노드: 조명 밝기를 하나의 값으로
        node_RGBToBW = group.nodes.new(type='ShaderNodeRGBToBW')
        node_RGBToBW.location = (-320, -250)

        # Softness가 0이어도 Map Range 구간이 0이 되지 않도록 최소값을 보장
        node_SoftClamp = group.nodes.new(type='ShaderNodeMath')
        node_SoftClamp.location = (-600, 200)
        node_SoftClamp.operation = 'MAXIMUM'
        node_SoftClamp.inputs[1].default_value = 0.001

        # 경계 하한 = Threshold - Softness
        node_EdgeMin = group.nodes.new(type='ShaderNodeMath')
        node_EdgeMin.location = (-400, 300)
        node_EdgeMin.operation = 'SUBTRACT'

        # 경계 상한 = Threshold + Softness
        node_EdgeMax = group.nodes.new(type='ShaderNodeMath')
        node_EdgeMax.location = (-400, 120)
        node_EdgeMax.operation = 'ADD'

        # Map Range 노드: 밝기를 경계 구간에서 0/1로 잘라 2톤을 만든다.
        node_MapRange = group.nodes.new(type='ShaderNodeMapRange')
        node_MapRange.location = (-120, -100)
        node_MapRange.interpolation_type = 'SMOOTHSTEP'
        node_MapRange.clamp = True

        # Mix Color 노드: 그림자 톤과 밝은 톤 중 하나를 고른다.
        node_MixTone = group.nodes.new(type='ShaderNodeMix')
        node_MixTone.location = (150, 100)
        node_MixTone.data_type = 'RGBA'
        node_MixTone.blend_type = 'MIX'

        # Mix Color 노드: 텍스처 색에 톤을 곱해 색감을 유지한다.
        node_MixBase = group.nodes.new(type='ShaderNodeMix')
        node_MixBase.location = (370, 200)
        node_MixBase.data_type = 'RGBA'
        node_MixBase.blend_type = 'MULTIPLY'
        enabled_socket(node_MixBase.inputs, 'Factor').default_value = 1.0

        # Emission 노드: 추가 음영 없이 계산된 2톤을 그대로 출력
        node_Emission = group.nodes.new(type='ShaderNodeEmission')
        node_Emission.location = (580, 200)

        # Transparent BSDF 노드: 텍스처 알파 컷아웃 처리용
        node_Transparent = group.nodes.new(type='ShaderNodeBsdfTransparent')
        node_Transparent.location = (580, -100)

        # 알파로 Emission과 Transparent를 섞는다.
        node_MixShader = group.nodes.new(type='ShaderNodeMixShader')
        node_MixShader.location = (750, 0)

    # 노드 링크 ===============================================================================
        # 경계 구간 계산
        group.links.new(group_in.outputs['Softness'], node_SoftClamp.inputs[0])
        group.links.new(group_in.outputs['Threshold'], node_EdgeMin.inputs[0])
        group.links.new(node_SoftClamp.outputs['Value'], node_EdgeMin.inputs[1])
        group.links.new(group_in.outputs['Threshold'], node_EdgeMax.inputs[0])
        group.links.new(node_SoftClamp.outputs['Value'], node_EdgeMax.inputs[1])

        # 조명 밝기를 2톤으로 자르기
        group.links.new(node_Diffuse.outputs['BSDF'], node_ShaderToRGB.inputs['Shader'])
        group.links.new(node_ShaderToRGB.outputs['Color'], node_RGBToBW.inputs['Color'])
        group.links.new(node_RGBToBW.outputs['Val'], enabled_socket(node_MapRange.inputs, 'Value'))
        group.links.new(node_EdgeMin.outputs['Value'], enabled_socket(node_MapRange.inputs, 'From Min'))
        group.links.new(node_EdgeMax.outputs['Value'], enabled_socket(node_MapRange.inputs, 'From Max'))

        # 그림자 톤 / 밝은 톤 선택 후 텍스처 색과 곱하기
        group.links.new(enabled_socket(node_MapRange.outputs, 'Result'), enabled_socket(node_MixTone.inputs, 'Factor'))
        group.links.new(group_in.outputs['Shadow Color'], enabled_socket(node_MixTone.inputs, 'A'))
        group.links.new(group_in.outputs['Light Color'], enabled_socket(node_MixTone.inputs, 'B'))
        group.links.new(group_in.outputs['Base Color'], enabled_socket(node_MixBase.inputs, 'A'))
        group.links.new(enabled_socket(node_MixTone.outputs, 'Result'), enabled_socket(node_MixBase.inputs, 'B'))

        # 출력
        group.links.new(enabled_socket(node_MixBase.outputs, 'Result'), node_Emission.inputs['Color'])
        group.links.new(group_in.outputs['Alpha'], node_MixShader.inputs['Factor'])
        group.links.new(node_Transparent.outputs['BSDF'], node_MixShader.inputs[1])
        group.links.new(node_Emission.outputs['Emission'], node_MixShader.inputs[2])
        group.links.new(node_MixShader.outputs['Shader'], group_out.inputs[0])

        # 머티리얼 출력 노드에 Node Group 적용
        node_tree.links.new(node_TexImage.outputs['Color'], node_group.inputs['Base Color'])
        node_tree.links.new(node_TexImage.outputs['Alpha'], node_group.inputs['Alpha'])
        node_tree.links.new(node_group.outputs[0], material_output.inputs[0])

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


# Mirror 모디파이어 -----------------------------------------------------------------
# side는 남길(원본) 쪽이다. +X면 +X 절반을 남기고 -X 쪽으로 미러한다.
MIRROR_SIDE_ITEMS = (
    ('NEGATIVE', "-", "음수 쪽을 남기고 양수 쪽으로 미러"),
    ('POSITIVE', "+", "양수 쪽을 남기고 음수 쪽으로 미러"),
)
# 경계 근처 버텍스를 0으로 스냅할 허용 거리
MIRROR_SNAP_DISTANCE = 0.01


def apply_axis_mirror(obj, axis_index: int, side: str) -> None:
    """반대쪽 절반을 제거하고 지정 축 하나만 켠 Mirror 모디파이어를 다시 만듭니다."""
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(obj.data)

    # 남길 쪽 부호로 좌표를 뒤집어 비교하면 양방향을 한 규칙으로 처리할 수 있다.
    sign = 1.0 if side == 'POSITIVE' else -1.0
    for vertex in bm.verts:
        if -MIRROR_SNAP_DISTANCE < vertex.co[axis_index] * sign < 0:
            vertex.co[axis_index] = 0

    # 반대쪽 영역만 제거하고, 제거할 버텍스가 없어도 미러 추가를 계속 진행
    vertices_to_delete = [vertex for vertex in bm.verts if vertex.co[axis_index] * sign < 0.0]
    if vertices_to_delete:
        bmesh.ops.delete(bm, geom=vertices_to_delete, context='VERTS')

    bmesh.update_edit_mesh(obj.data)
    bpy.ops.object.mode_set(mode='OBJECT')

    # 순회 중 삭제하면 항목을 건너뛰므로 목록을 먼저 만든다.
    for modifier in [m for m in obj.modifiers if m.type == 'MIRROR']:
        obj.modifiers.remove(modifier)

    mirror_modifier = obj.modifiers.new("Mirror", 'MIRROR')
    for index in range(3):
        mirror_modifier.use_axis[index] = index == axis_index


class MirrorModifierOperator:
    bl_options = {'REGISTER', 'UNDO'}
    axis_index = 0

    side: EnumProperty(name="Side", items=MIRROR_SIDE_ITEMS, default='POSITIVE')

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.type == 'MESH'

    def execute(self, context):
        apply_axis_mirror(context.object, self.axis_index, self.side)
        return {'FINISHED'}


class Add_Mirror_X_Modifier(MirrorModifierOperator, Operator):
    """선택한 쪽 X 절반을 남기고 X축 Mirror 모디파이어를 추가합니다."""
    bl_idname = "wm.add_mirror_x_modifier"
    bl_label = "X"
    axis_index = 0

    # 기존 호출 호환: X는 원래 음수 쪽을 남겼다.
    side: EnumProperty(name="Side", items=MIRROR_SIDE_ITEMS, default='NEGATIVE')


class Add_Mirror_Y_Modifier(MirrorModifierOperator, Operator):
    """선택한 쪽 Y 절반을 남기고 Y축 Mirror 모디파이어를 추가합니다."""
    bl_idname = "wm.add_mirror_y_modifier"
    bl_label = "Y"
    axis_index = 1


class Add_Mirror_Z_Modifier(MirrorModifierOperator, Operator):
    """선택한 쪽 Z 절반을 남기고 Z축 Mirror 모디파이어를 추가합니다."""
    bl_idname = "wm.add_mirror_z_modifier"
    bl_label = "Z"
    axis_index = 2


# 정렬 연산자 -----------------------------------------------------------------------------

class OBJECT_OT_CatAlign(Operator):
    """활성 오브젝트를 기준으로 선택한 오브젝트의 Transform을 축별로 정렬합니다."""
    bl_idname = "object.cat_align"
    bl_label = "Align"
    bl_options = {'REGISTER', 'UNDO'}

    mode: EnumProperty(
        name="Mode",
        items=[
            ('LOCATION', "Location", "위치 정렬"),
            ('ROTATION', "Rotation", "회전 정렬"),
            ('SCALE', "Scale", "크기 정렬"),
        ],
        default='LOCATION',
    )
    axis: EnumProperty(
        name="Axis",
        items=[
            ('X', "X", "X축만 정렬"),
            ('Y', "Y", "Y축만 정렬"),
            ('Z', "Z", "Z축만 정렬"),
            ('ALL', "All", "X/Y/Z 모두 정렬"),
        ],
        default='X',
    )

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and len(context.selected_objects) > 1

    def execute(self, context) -> Set[str]:
        active_object = context.active_object
        targets = [obj for obj in context.selected_objects if obj is not active_object]
        if not targets:
            self.report({'WARNING'}, "활성 오브젝트와 정렬할 오브젝트를 함께 선택하세요.")
            return {'CANCELLED'}

        indices = (0, 1, 2) if self.axis == 'ALL' else (ALIGN_AXIS_INDICES[self.axis],)

        if self.mode == 'ROTATION':
            reference = rotation_as_euler(active_object)
            for obj in targets:
                euler = rotation_as_euler(obj)
                for index in indices:
                    euler[index] = reference[index]
                apply_rotation_euler(obj, euler)
        else:
            property_name = ALIGN_PROPERTIES[self.mode]
            reference = getattr(active_object, property_name)
            for obj in targets:
                values = getattr(obj, property_name)
                for index in indices:
                    values[index] = reference[index]

        return {'FINISHED'}


# 사이드바 탭 활성화 -----------------------------------------------------------------------

def activate_cat_tab_in_open_sidebars() -> None:
    """열려 있는 모든 3D 뷰 사이드바의 활성 탭을 CatTools로 맞춘다.

    사이드바를 방금 연 프레임에는 탭 목록이 아직 만들어지지 않아 대입이
    read-only로 거부된다. 그래서 실패하면 다음 프레임에 다시 시도한다.
    """
    retry = False
    for window in bpy.context.window_manager.windows:
        screen = window.screen
        if screen is None:
            continue
        for area in screen.areas:
            if area.type != 'VIEW_3D':
                continue
            space = area.spaces.active
            if space is None or not space.show_region_ui:
                continue
            region = next((r for r in area.regions if r.type == 'UI'), None)
            if region is None:
                continue
            try:
                region.active_panel_category = CAT_CATEGORY
            except (AttributeError, TypeError, ValueError):
                retry = True

    if retry and not bpy.app.timers.is_registered(_activate_cat_tab_timer):
        bpy.app.timers.register(_activate_cat_tab_timer, first_interval=0.0)


def _activate_cat_tab_timer():
    activate_cat_tab_in_open_sidebars()
    return None


EDIT_ELEMENT_TYPES = {
    'VERT': bmesh.types.BMVert,
    'EDGE': bmesh.types.BMEdge,
    'FACE': bmesh.types.BMFace,
}


def edit_elements(bm, element_kind):
    return {'VERT': bm.verts, 'EDGE': bm.edges, 'FACE': bm.faces}[element_kind]


def edit_element_center(element) -> Vector:
    """요소의 로컬 중심 좌표: 점은 위치, 선은 양 끝 중점, 면은 정점 중앙값."""
    if isinstance(element, bmesh.types.BMVert):
        return element.co
    if isinstance(element, bmesh.types.BMEdge):
        return (element.verts[0].co + element.verts[1].co) / 2
    return element.calc_center_median()


# 면 모드 같은 값 선택에서 노멀 방향을 같다고 볼 최대 각도(1도)의 코사인
SELECT_NORMAL_MATCH_COS = math.cos(math.radians(1.0))

# 선택 방향별 보고 문구
SELECT_DIRECTION_LABELS = {'SAME': "같은", 'POSITIVE': "양(+) 방향에 있는", 'NEGATIVE': "음(-) 방향에 있는"}


def select_axis_matches(
    value: float, reference: float, direction: str, tolerance: float, distance: float = 0.0
) -> bool:
    """
    축 좌표가 선택 방향 조건을 만족하는지 판정한다.

    Args:
        value: 비교할 대상의 축 좌표
        reference: 기준 축 좌표
        direction: 'SAME'(같은 값), 'POSITIVE'(기준 + distance 이상), 'NEGATIVE'(기준 - distance 이하)
        tolerance: 허용 오차 (경계와 같은 위치의 대상은 선택에 포함된다)
        distance: 양/음 방향 선택을 시작할 기준으로부터의 거리 (0이면 기준 자신도 포함)

    Returns:
        조건 만족 여부
    """
    if direction == 'POSITIVE':
        return value >= reference + distance - tolerance
    if direction == 'NEGATIVE':
        return value <= reference - distance + tolerance
    return abs(value - reference) <= tolerance


def select_axis_matches_any(
    value: float, references, direction: str, tolerance: float, distance: float = 0.0
) -> bool:
    """
    축 좌표가 여러 기준 중 하나라도 선택 방향 조건을 만족하는지 판정한다.

    Args:
        value: 비교할 대상의 축 좌표
        references: 오름차순으로 정렬된 기준 축 좌표 목록 (비어 있으면 안 된다)
        direction, tolerance, distance: select_axis_matches와 같다

    Returns:
        조건 만족 여부 (각 기준별 선택 결과의 합집합)
    """
    # +/- 방향 선택의 합집합은 가장 느슨한 기준(+는 최솟값, -는 최댓값) 하나의 결과와 같다.
    if direction == 'POSITIVE':
        return select_axis_matches(value, references[0], direction, tolerance, distance)
    if direction == 'NEGATIVE':
        return select_axis_matches(value, references[-1], direction, tolerance, distance)
    # 같은 값 선택은 가장 가까운 기준 둘만 비교하면 된다.
    position = bisect.bisect_left(references, value)
    neighbors = references[max(0, position - 1):position + 1]
    return any(abs(value - reference) <= tolerance for reference in neighbors)


class OBJECT_OT_CatSelectSamePivot(Operator):
    """지정 축의 월드 좌표가 기준과 같거나 기준보다 +/- 방향에 있는 오브젝트(Object 모드) 또는 점/선/면(Edit 모드)을 모두 선택합니다."""
    bl_idname = "object.cat_select_same_pivot"
    bl_label = "Select Same Pivot"
    bl_options = {'REGISTER', 'UNDO'}

    axis: EnumProperty(
        name="Axis",
        items=[
            ('X', "X", "X축 피벗이 같은 오브젝트 선택"),
            ('Y', "Y", "Y축 피벗이 같은 오브젝트 선택"),
            ('Z', "Z", "Z축 피벗이 같은 오브젝트 선택"),
        ],
        default='Z',
    )
    direction: EnumProperty(
        name="Direction",
        items=[
            ('SAME', "Same", "기준과 축 값이 같은 대상 선택"),
            ('POSITIVE', "+", "기준에서 Distance 이상 떨어진 축의 양(+) 방향 대상 모두 선택"),
            ('NEGATIVE', "-", "기준에서 Distance 이상 떨어진 축의 음(-) 방향 대상 모두 선택"),
        ],
        default='SAME',
    )
    # 양/음 방향 선택의 시작 거리. 0보다 크게 주면 기준(자기 자신)을 제외할 수 있다.
    distance: FloatProperty(
        name="Distance",
        description="기준으로부터 이 거리 이상 떨어진 대상부터 선택 (+/- 방향 선택에만 적용)",
        default=0.0, min=0.0, soft_max=100.0,
        precision=4, subtype='DISTANCE', unit='LENGTH',
    )
    # 모델링 중 생기는 부동소수 오차 때문에 완전 일치 비교는 쓰지 않는다.
    tolerance: FloatProperty(
        name="Tolerance", default=0.0001, min=0.0, soft_max=0.1,
        precision=4, subtype='DISTANCE', unit='LENGTH',
    )
    # 면 모드의 같은 값 선택에서 축 값뿐 아니라 노멀 방향까지 같은 면만 고른다.
    match_normal: BoolProperty(
        name="Match Normal",
        description="면 모드 X·Y·Z 선택에서 기준 면과 노멀 방향도 같은 면만 선택",
        default=True,
    )
    extend: BoolProperty(name="Extend", description="기존 선택을 유지한 채 추가 선택", default=False)

    @classmethod
    def poll(cls, context):
        if context.mode == 'EDIT_MESH':
            return True
        return context.mode == 'OBJECT' and context.active_object is not None

    # 3D View 좌하단 Adjust Last Operation 패널: Distance는 +/- 방향 선택에서만,
    # Match Normal은 면 모드의 같은 값 선택에서만 보여 준다.
    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        layout.prop(self, "axis")
        layout.prop(self, "direction")
        if self.direction != 'SAME':
            layout.prop(self, "distance")
        layout.prop(self, "tolerance")
        if self.direction == 'SAME' and context.mode == 'EDIT_MESH' and context.tool_settings.mesh_select_mode[2]:
            layout.prop(self, "match_normal")
        layout.prop(self, "extend")

    def execute(self, context) -> Set[str]:
        if context.mode == 'EDIT_MESH':
            return self.execute_edit_mesh(context)
        active_object = context.active_object
        index = ALIGN_AXIS_INDICES[self.axis]
        # 부모가 있어도 화면에서 보이는 원점 위치로 비교하도록 월드 좌표를 쓴다.
        reference = active_object.matrix_world.translation[index]

        count = 0
        for obj in context.selectable_objects:
            matched = select_axis_matches(
                obj.matrix_world.translation[index], reference,
                self.direction, self.tolerance, self.distance,
            )
            if matched:
                obj.select_set(True)
                count += 1
            elif not self.extend:
                obj.select_set(False)

        # +/- 방향은 Distance로 기준 자신을 제외할 수 있어야 하므로 같은 값 선택에서만 기준을 강제 선택한다.
        if self.direction == 'SAME':
            active_object.select_set(True)
        direction_label = SELECT_DIRECTION_LABELS[self.direction]
        self.report({'INFO'}, f"{self.axis}축 피벗이 {direction_label} 오브젝트 {count}개를 선택했습니다.")
        return {'FINISHED'}

    # Edit 모드: 현재 선택 모드(점/선/면)의 요소 중심 좌표를 선택된 각 요소의 축 값과 비교해 방향 조건에 맞는 요소를 선택
    def execute_edit_mesh(self, context) -> Set[str]:
        vert_mode, edge_mode, face_mode = context.tool_settings.mesh_select_mode
        element_kind = 'FACE' if face_mode else 'EDGE' if edge_mode else 'VERT'
        index = ALIGN_AXIS_INDICES[self.axis]

        objects = getattr(context, "objects_in_mode_unique_data", None) or [context.edit_object]
        meshes = []
        for obj in objects:
            if obj is None or obj.type != 'MESH':
                continue
            bm = bmesh.from_edit_mesh(obj.data)
            meshes.append((obj, bm, [e for e in edit_elements(bm, element_kind) if not e.hide]))

        references = self.edit_references(meshes, index)
        if not references:
            self.report({'WARNING'}, "기준이 될 점, 선, 면을 선택하세요.")
            return {'CANCELLED'}
        # 면 모드 같은 값 선택: 축 값이 같아도 다른 방향을 보는 면(옆면 등)은 제외한다.
        use_normal = element_kind == 'FACE' and self.direction == 'SAME' and self.match_normal
        if use_normal:
            normal_references = self.edit_normal_references(meshes, index)

        count = 0
        for obj, bm, elements in meshes:
            matrix = obj.matrix_world
            if use_normal:
                matched = [
                    e for e in elements
                    if self.matches_value_and_normal(
                        (matrix @ edit_element_center(e))[index],
                        world_normal(matrix, e.normal),
                        normal_references, self.tolerance,
                    )
                ]
            else:
                matched = [
                    e for e in elements
                    if select_axis_matches_any(
                        (matrix @ edit_element_center(e))[index], references,
                        self.direction, self.tolerance, self.distance,
                    )
                ]
            if not self.extend:
                for sequence in (bm.verts, bm.edges, bm.faces):
                    for element in sequence:
                        element.select = False
            for element in matched:
                element.select_set(True)
            bm.select_flush_mode()
            bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
            count += len(matched)

        kind_label = {'VERT': "점", 'EDGE': "선", 'FACE': "면"}[element_kind]
        direction_label = SELECT_DIRECTION_LABELS[self.direction]
        self.report({'INFO'}, f"{self.axis}축 값이 {direction_label} {kind_label} {count}개를 선택했습니다.")
        return {'FINISHED'}

    @staticmethod
    def edit_references(meshes, index):
        # 선택된 요소마다 자신의 축 값을 기준으로 삼는다 (하나만 선택하면 이전과 같은 결과).
        return sorted(
            (obj.matrix_world @ edit_element_center(e))[index]
            for obj, _bm, elements in meshes
            for e in elements
            if e.select
        )

    @staticmethod
    def edit_normal_references(meshes, index):
        # 선택된 면마다 (축 값, 월드 노멀)을 기준으로 삼고 축 값 순으로 정렬해 둔다.
        references = sorted(
            (
                (obj.matrix_world @ e.calc_center_median())[index],
                world_normal(obj.matrix_world, e.normal),
            )
            for obj, _bm, elements in meshes
            for e in elements
            if e.select
        )
        return [value for value, _normal in references], [normal for _value, normal in references]

    @staticmethod
    def matches_value_and_normal(value, normal, normal_references, tolerance) -> bool:
        # 축 값이 허용 오차 안인 기준들 중 하나와 노멀 방향까지 같은지 판정한다.
        values, normals = normal_references
        if normal.length <= 1e-9:
            return False
        position = bisect.bisect_left(values, value - tolerance)
        while position < len(values) and values[position] <= value + tolerance:
            if normal.dot(normals[position]) >= SELECT_NORMAL_MATCH_COS:
                return True
            position += 1
        return False


def edit_element_normal(element) -> Vector:
    """요소의 로컬 노멀: 점·면은 자체 노멀, 선은 인접 면 노멀(없으면 양 끝 점 노멀)의 평균."""
    if isinstance(element, bmesh.types.BMEdge):
        normals = [face.normal for face in element.link_faces] or [vert.normal for vert in element.verts]
        return sum(normals, Vector()) / len(normals)
    return element.normal


def edit_element_neighbors(element):
    """요소와 맞닿은 같은 종류의 요소: 면은 변을 공유한 면, 선은 점을 공유한 선, 점은 선으로 이어진 점."""
    if isinstance(element, bmesh.types.BMFace):
        return (face for edge in element.edges for face in edge.link_faces if face is not element)
    if isinstance(element, bmesh.types.BMEdge):
        return (edge for vert in element.verts for edge in vert.link_edges if edge is not element)
    return (edge.other_vert(element) for edge in element.link_edges)


def connected_elements(seeds, candidates):
    """seeds에서 출발해 candidates 안의 요소만 거쳐 이어진 요소를 모두 모은다."""
    found = set(seeds)
    stack = list(found)
    while stack:
        for neighbor in edit_element_neighbors(stack.pop()):
            if neighbor in candidates and neighbor not in found:
                found.add(neighbor)
                stack.append(neighbor)
    return found


def world_normal(matrix: Matrix, normal: Vector) -> Vector:
    """
    로컬 노멀을 월드 방향으로 변환한다.

    비균등 스케일이 있어도 면에 수직인 방향을 유지하도록 역전치 행렬을 쓴다.
    길이가 0인 노멀은 그대로 0 벡터를 돌려준다.
    """
    result = matrix.to_3x3().inverted_safe().transposed() @ normal
    if result.length > 1e-9:
        result.normalize()
    return result


class OBJECT_OT_CatSelectSameNormal(Operator):
    """기준과 노멀 방향이 같은 면·선·점(Edit 모드) 또는 월드 회전이 같은 오브젝트(Object 모드)를 모두 선택합니다."""
    bl_idname = "object.cat_select_same_normal"
    bl_label = "Select Same Normal"
    bl_options = {'REGISTER', 'UNDO'}

    # 노멀(또는 회전) 사이 각도가 이 값 이하이면 같은 방향으로 본다.
    angle: FloatProperty(
        name="Angle",
        description="기준과 같은 방향으로 볼 최대 각도 차이",
        default=math.radians(1.0), min=0.0, max=math.pi,
        precision=2, subtype='ANGLE',
    )
    # 켜면 기준에서 같은 방향 요소끼리 맞닿아 이어진 영역만 선택한다 (Edit 모드 전용).
    connected: BoolProperty(
        name="Connected",
        description="기준 요소와 맞닿아 이어진 같은 방향 요소만 선택 (Edit 모드 전용)",
        default=True,
    )
    extend: BoolProperty(name="Extend", description="기존 선택을 유지한 채 추가 선택", default=False)

    @classmethod
    def poll(cls, context):
        if context.mode == 'EDIT_MESH':
            return True
        return context.mode == 'OBJECT' and context.active_object is not None

    # 3D View 좌하단 Adjust Last Operation 패널: Connected는 Edit 모드에서만 보여 준다.
    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        layout.prop(self, "angle")
        if context.mode == 'EDIT_MESH':
            layout.prop(self, "connected")
        layout.prop(self, "extend")

    def execute(self, context) -> Set[str]:
        if context.mode == 'EDIT_MESH':
            return self.execute_edit_mesh(context)
        active_object = context.active_object
        # 스케일을 제외한 월드 회전끼리 비교해 부모 회전까지 반영한다.
        reference = active_object.matrix_world.to_quaternion()

        count = 0
        for obj in context.selectable_objects:
            difference = reference.rotation_difference(obj.matrix_world.to_quaternion()).angle
            # 쿼터니언 각도는 0~2π 범위라 반대쪽으로 가까운 경우도 같은 회전으로 본다.
            if min(difference, 2 * math.pi - difference) <= self.angle:
                obj.select_set(True)
                count += 1
            elif not self.extend:
                obj.select_set(False)

        active_object.select_set(True)
        self.report({'INFO'}, f"월드 회전이 같은 오브젝트 {count}개를 선택했습니다.")
        return {'FINISHED'}

    # Edit 모드: 현재 선택 모드(점/선/면)의 월드 노멀을 기준 노멀과 각도로 비교해 같은 방향 요소를 선택
    def execute_edit_mesh(self, context) -> Set[str]:
        vert_mode, edge_mode, face_mode = context.tool_settings.mesh_select_mode
        element_kind = 'FACE' if face_mode else 'EDGE' if edge_mode else 'VERT'

        objects = getattr(context, "objects_in_mode_unique_data", None) or [context.edit_object]
        meshes = []
        for obj in objects:
            if obj is None or obj.type != 'MESH':
                continue
            bm = bmesh.from_edit_mesh(obj.data)
            meshes.append((obj, bm, [e for e in edit_elements(bm, element_kind) if not e.hide]))

        reference = self.edit_reference(context, meshes, element_kind)
        if reference is None:
            self.report({'WARNING'}, "노멀 방향의 기준이 될 점, 선, 면을 선택하세요.")
            return {'CANCELLED'}

        # 각도 비교를 내적 비교로 바꿔 요소마다 acos를 계산하지 않는다.
        min_dot = math.cos(self.angle)
        count = 0
        for obj, bm, elements in meshes:
            matrix = obj.matrix_world
            matched = []
            for e in elements:
                normal = world_normal(matrix, edit_element_normal(e))
                # 노멀이 없는(퇴화) 요소는 방향을 정할 수 없으므로 제외한다.
                if normal.length > 1e-9 and normal.dot(reference) >= min_dot - 1e-6:
                    matched.append(e)
            if self.connected:
                # 이미 선택된 같은 방향 요소(기준 포함)에서 출발해 맞닿은 같은 방향 요소로만 넓힌다.
                matched = connected_elements([e for e in matched if e.select], set(matched))
            if not self.extend:
                for sequence in (bm.verts, bm.edges, bm.faces):
                    for element in sequence:
                        element.select = False
            for element in matched:
                element.select_set(True)
            bm.select_flush_mode()
            bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
            count += len(matched)

        kind_label = {'VERT': "점", 'EDGE': "선", 'FACE': "면"}[element_kind]
        self.report({'INFO'}, f"노멀 방향이 같은 {kind_label} {count}개를 선택했습니다.")
        return {'FINISHED'}

    @staticmethod
    def edit_reference(context, meshes, element_kind):
        # 활성 요소(마지막으로 클릭한 요소)의 노멀을 우선 기준으로 삼고, 없으면 선택 요소 노멀의 평균을 쓴다.
        element_type = EDIT_ELEMENT_TYPES[element_kind]
        for obj, bm, _elements in meshes:
            if obj != context.edit_object:
                continue
            active = bm.select_history.active
            if isinstance(active, element_type) and active.select:
                normal = world_normal(obj.matrix_world, edit_element_normal(active))
                if normal.length > 1e-9:
                    return normal

        total = Vector()
        for obj, _bm, elements in meshes:
            for e in elements:
                if e.select:
                    total += world_normal(obj.matrix_world, edit_element_normal(e))
        if total.length <= 1e-9:
            return None
        return total.normalized()


def fibonacci_sphere_directions(count: int):
    """구 위에 고르게 퍼진 단위 방향 벡터 count개를 만든다."""
    golden_angle = math.pi * (3.0 - math.sqrt(5.0))
    directions = []
    for i in range(count):
        z = 1.0 - 2.0 * (i + 0.5) / count
        radius = math.sqrt(max(0.0, 1.0 - z * z))
        theta = golden_angle * i
        directions.append(Vector((math.cos(theta) * radius, math.sin(theta) * radius, z)))
    return directions


def build_world_bvh(context, edit_meshes, include_others: bool):
    """
    가림 판정용 월드 좌표 BVHTree를 만든다.

    Args:
        context: 현재 컨텍스트
        edit_meshes: (오브젝트, bmesh) 목록. 편집 중인 현재 형상을 그대로 쓴다.
        include_others: 보이는 다른 메쉬 오브젝트(모디파이어 적용 결과)도 가림체로 포함할지 여부
    """
    vertices = []
    polygons = []

    def add(matrix, coords, faces):
        offset = len(vertices)
        vertices.extend(matrix @ co for co in coords)
        polygons.extend([offset + index for index in face] for face in faces)

    # H로 숨긴 면도 실제 형상이므로 가림체에 포함한다.
    for obj, bm in edit_meshes:
        bm.verts.index_update()
        add(
            obj.matrix_world,
            [v.co for v in bm.verts],
            [[v.index for v in f.verts] for f in bm.faces],
        )

    if include_others:
        edit_objects = {obj for obj, _bm in edit_meshes}
        depsgraph = context.evaluated_depsgraph_get()
        for obj in context.visible_objects:
            if obj.type != 'MESH' or obj in edit_objects:
                continue
            evaluated = obj.evaluated_get(depsgraph)
            mesh = evaluated.to_mesh()
            try:
                add(
                    evaluated.matrix_world,
                    [v.co for v in mesh.vertices],
                    [list(p.vertices) for p in mesh.polygons],
                )
            finally:
                evaluated.to_mesh_clear()

    if not polygons:
        return None
    return BVHTree.FromPolygons(vertices, polygons)


def face_sample_points(matrix, face, resolution: int):
    """
    면 위에 고르게 퍼진 월드 좌표 검사 지점을 만든다.

    면 중심을 먼저 돌려주고, 이어서 면을 삼각형으로 나눠 각 삼각형을 resolution 격자로 쪼갠
    작은 삼각형들의 무게중심을 돌려준다. 모든 지점이 면 안쪽에 있다.
    """
    coords = [matrix @ v.co for v in face.verts]
    yield matrix @ face.calc_center_median()
    for a, b, c in tessellate_polygon([coords]):
        pa, pb, pc = coords[a], coords[b], coords[c]
        for i in range(resolution):
            for j in range(resolution - i):
                u = (i + 1.0 / 3.0) / resolution
                v = (j + 1.0 / 3.0) / resolution
                yield pa + (pb - pa) * u + (pc - pa) * v


class OBJECT_OT_CatSelectHiddenFaces(Operator):
    """어느 방향에서도 보이지 않는 은면(다른 면에 완전히 가려진 면)을 선택합니다. 삭제는 하지 않습니다."""
    bl_idname = "object.cat_select_hidden_faces"
    bl_label = "Select Hidden Faces"
    bl_options = {'REGISTER', 'UNDO'}

    # 면마다 바깥쪽 반구로 쏘는 광선 방향 수(구 전체 기준). 많을수록 정확하지만 느리다.
    samples: IntProperty(
        name="Samples",
        description="가림 판정에 쓰는 광선 방향 수 (구 전체 기준, 면마다 바깥쪽 절반만 사용)",
        default=64, min=8, soft_max=256, max=1024,
    )
    # 면 위 검사 지점 밀도: 삼각형마다 변을 이 수로 나눈 격자의 내부 지점을 쓴다.
    face_samples: IntProperty(
        name="Face Samples",
        description="면 위 검사 지점 밀도 (클수록 면의 좁은 일부만 보이는 경우도 잡지만 느려진다)",
        default=4, min=1, soft_max=8, max=16,
    )
    include_others: BoolProperty(
        name="Other Objects",
        description="보이는 다른 메쉬 오브젝트에 가려진 면도 은면으로 판정",
        default=True,
    )
    extend: BoolProperty(name="Extend", description="기존 선택을 유지한 채 추가 선택", default=False)

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH'

    def execute(self, context) -> Set[str]:
        objects = getattr(context, "objects_in_mode_unique_data", None) or [context.edit_object]
        edit_meshes = [
            (obj, bmesh.from_edit_mesh(obj.data))
            for obj in objects
            if obj is not None and obj.type == 'MESH'
        ]
        bvh = build_world_bvh(context, edit_meshes, self.include_others)
        if bvh is None:
            self.report({'WARNING'}, "검사할 면이 없습니다.")
            return {'CANCELLED'}

        directions = fibonacci_sphere_directions(self.samples)
        # 광선 시작점을 면에서 살짝 띄워 자기 면이나 맞닿은 면에 바로 맞는 것을 막는다.
        offset = 1e-4
        # 결과를 볼 수 있도록 면 선택 모드로 바꾼다.
        context.tool_settings.mesh_select_mode = (False, False, True)

        count = 0
        for obj, bm in edit_meshes:
            matrix = obj.matrix_world
            hidden = []
            for face in bm.faces:
                if face.hide:
                    continue
                normal = world_normal(matrix, face.normal)
                if normal.length <= 1e-9:
                    continue
                if self.face_is_hidden(bvh, matrix, face, normal, directions, offset, self.face_samples):
                    hidden.append(face)
            if not self.extend:
                for sequence in (bm.verts, bm.edges, bm.faces):
                    for element in sequence:
                        element.select = False
            for face in hidden:
                face.select_set(True)
            bm.select_flush_mode()
            bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)
            count += len(hidden)

        self.report({'INFO'}, f"보이지 않는 은면 {count}개를 선택했습니다. 확인 후 직접 삭제하세요.")
        return {'FINISHED'}

    @staticmethod
    def face_is_hidden(bvh, matrix, face, normal, directions, offset, resolution) -> bool:
        # 면 위에 고르게 깐 지점들에서 바깥쪽 반구로 쏜 광선이 하나라도 빠져나가면 보이는 면이다.
        # 일부만 드러난 길쭉한 면(지붕을 뚫고 나온 굴뚝 옆면 등)도 놓치지 않도록 면 전체를 표본으로 쓴다.
        outward = [d for d in directions if d.dot(normal) > 0.01]
        for point in face_sample_points(matrix, face, resolution):
            origin = point + normal * offset
            for direction in outward:
                if bvh.ray_cast(origin, direction)[0] is None:
                    return False
        return True


class VIEW3D_OT_CatSidebar(Operator):
    """사이드바를 토글하고, 열 때 CatTools 탭을 활성화합니다."""
    bl_idname = "view3d.cat_toggle_sidebar"
    bl_label = "Toggle Sidebar (CatTools)"

    @classmethod
    def poll(cls, context):
        return context.space_data is not None and context.space_data.type == 'VIEW_3D'

    def execute(self, context) -> Set[str]:
        # show_region_ui 대입은 컨텍스트 오버라이드 아래에서 닫기 방향이 적용되지
        # 않으므로, 영역 컨텍스트를 그대로 쓰는 region_toggle로 토글한다.
        bpy.ops.screen.region_toggle(region_type='UI')
        if context.space_data.show_region_ui:
            activate_cat_tab_in_open_sidebars()
        return {'FINISHED'}


@bpy.app.handlers.persistent
def _on_load_post(_dummy) -> None:
    # 사이드바가 이미 열린 상태로 저장된 파일에서도 CatTools가 먼저 보이게 한다.
    activate_cat_tab_in_open_sidebars()


addon_keymaps = []


def register_keymaps() -> None:
    keyconfig = bpy.context.window_manager.keyconfigs.addon
    if keyconfig is None:
        return
    keymap = keyconfig.keymaps.new(name="3D View", space_type='VIEW_3D')
    item = keymap.keymap_items.new(VIEW3D_OT_CatSidebar.bl_idname, 'N', 'PRESS')
    addon_keymaps.append((keymap, item))


def unregister_keymaps() -> None:
    for keymap, item in addon_keymaps:
        keymap.keymap_items.remove(item)
    addon_keymaps.clear()


classes = [
    OBJECT_PT_WoodyTool,
    VIEW3D_OT_CatSidebar,
    OBJECT_OT_CatAlign,
    OBJECT_OT_CatSelectSamePivot,
    OBJECT_OT_CatSelectSameNormal,
    OBJECT_OT_CatSelectHiddenFaces,
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
    SHADER_OP_Catoon,
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
    for name, factory in EDIT_TRANSFORM_PROPERTIES.items():
        setattr(bpy.types.Scene, name, factory())
    for handlers in EDIT_RESET_HANDLERS:
        if _reset_edit_transform_state not in handlers:
            handlers.append(_reset_edit_transform_state)
    register_keymaps()
    if _on_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_load_post)

def unregister():
    if _on_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load_post)
    if bpy.app.timers.is_registered(_activate_cat_tab_timer):
        bpy.app.timers.unregister(_activate_cat_tab_timer)
    unregister_keymaps()
    for handlers in EDIT_RESET_HANDLERS:
        if _reset_edit_transform_state in handlers:
            handlers.remove(_reset_edit_transform_state)
    for name in EDIT_TRANSFORM_PROPERTIES:
        if hasattr(bpy.types.Scene, name):
            delattr(bpy.types.Scene, name)
    for cls in classes:
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
