"""Blender에서 CatTools Select Same Pivot 연산자의 실제 동작을 검사합니다."""

from __future__ import annotations

import importlib
import importlib.util
import math
from pathlib import Path

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector


ROOT = Path(__file__).resolve().parents[1]
ADDON_PATH = ROOT / "__init__.py"
MODULE_NAME = "bl_ext.user_default.cat_tools"


def load_addon():
    if MODULE_NAME in bpy.context.preferences.addons:
        return importlib.import_module(MODULE_NAME), False

    spec = importlib.util.spec_from_file_location("cat_tools_select_pivot_smoke", ADDON_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("CatTools 모듈 로더를 생성할 수 없습니다.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, True


def remove_all_objects() -> None:
    if bpy.context.object is not None and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def create_empty(name: str, location):
    obj = bpy.data.objects.new(name, None)
    obj.location = location
    bpy.context.collection.objects.link(obj)
    return obj


def selected_names() -> set[str]:
    return {obj.name for obj in bpy.context.selected_objects}


def setup_grid():
    # 2x2 면 그리드를 X로 10만큼 옮겨 월드 좌표 환산을 함께 검증한다.
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=2, y_subdivisions=2, size=2.0, location=(10.0, 0.0, 0.0))
    obj = bpy.context.object
    bpy.ops.object.mode_set(mode="EDIT")
    bm = bmesh.from_edit_mesh(obj.data)
    for element in (*bm.verts, *bm.edges, *bm.faces):
        element.select = False
    return obj, bm


def check_edit_mesh_faces() -> None:
    obj, bm = setup_grid()
    bpy.context.tool_settings.mesh_select_mode = (False, False, True)
    # 왼쪽 아래 면 하나를 활성 선택
    face = min(bm.faces, key=lambda f: tuple(f.calc_center_median()))
    face.select_set(True)
    bm.select_history.add(face)
    bmesh.update_edit_mesh(obj.data)

    assert bpy.ops.object.cat_select_same_pivot(axis="Y") == {"FINISHED"}
    selected = [f for f in bm.faces if f.select]
    assert len(selected) == 2, f"Y가 같은 면 2개가 선택돼야 합니다: {len(selected)}"
    assert all(abs(f.calc_center_median().y - face.calc_center_median().y) < 1e-6 for f in selected)

    # 모든 면은 Z가 같다.
    assert bpy.ops.object.cat_select_same_pivot(axis="Z") == {"FINISHED"}
    assert all(f.select for f in bm.faces), "Z가 같은 모든 면이 선택돼야 합니다."
    remove_all_objects()


def check_edit_mesh_multiple_faces() -> None:
    # 3x3 면 그리드에서 여러 면을 선택하면 각 면의 축 값이 모두 기준이 된다.
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=3, y_subdivisions=3, size=3.0, location=(10.0, 0.0, 0.0))
    obj = bpy.context.object
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.context.tool_settings.mesh_select_mode = (False, False, True)
    bm = bmesh.from_edit_mesh(obj.data)
    assert len(bm.faces) == 9, len(bm.faces)

    def cell(face):
        center = face.calc_center_median()
        return round(center.x + 1.0), round(center.y + 1.0)

    def select_cells(*cells):
        for element in (*bm.verts, *bm.edges, *bm.faces):
            element.select = False
        bm.select_history.clear()
        for face in bm.faces:
            if cell(face) in cells:
                face.select_set(True)
                bm.select_history.add(face)
        bmesh.update_edit_mesh(obj.data)

    def selected_cells():
        return {cell(f) for f in bm.faces if f.select}

    # 왼쪽 아래(0,0)와 오른쪽 위(2,2): Y는 아래·위 두 줄 6면, 가운데 줄은 제외
    select_cells((0, 0), (2, 2))
    assert bpy.ops.object.cat_select_same_pivot(axis="Y") == {"FINISHED"}
    assert selected_cells() == {(x, y) for x in range(3) for y in (0, 2)}, selected_cells()

    select_cells((0, 0), (2, 2))
    assert bpy.ops.object.cat_select_same_pivot(axis="X") == {"FINISHED"}
    assert selected_cells() == {(x, y) for x in (0, 2) for y in range(3)}, selected_cells()

    # +X는 기준들 각각의 결과를 합친다: 열 1과 열 2 기준 → 열 1·2
    select_cells((1, 0), (2, 2))
    assert bpy.ops.object.cat_select_same_pivot(axis="X", direction="POSITIVE") == {"FINISHED"}
    assert selected_cells() == {(x, y) for x in (1, 2) for y in range(3)}, selected_cells()
    # -X는 열 0·1·2 모두 (열 2 기준의 음 방향이 전체를 덮는다)
    select_cells((1, 0), (2, 2))
    assert bpy.ops.object.cat_select_same_pivot(axis="X", direction="NEGATIVE") == {"FINISHED"}
    assert len(selected_cells()) == 9, selected_cells()
    remove_all_objects()


def check_edit_mesh_face_normal_filter() -> None:
    # 큐브 A·C의 아랫면(-Z, z=-1)과 한 단 내려간 큐브 B의 옆면 중심(z=-1)은 Z 값이 같다.
    bm_source = bmesh.new()
    for center in ((0.0, 0.0, 0.0), (3.0, 0.0, -1.0), (6.0, 0.0, 0.0)):
        bmesh.ops.create_cube(bm_source, size=2.0, matrix=Matrix.Translation(center))
    mesh = bpy.data.meshes.new("Steps")
    bm_source.to_mesh(mesh)
    bm_source.free()
    obj = bpy.data.objects.new("Steps", mesh)
    bpy.context.collection.objects.link(obj)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.context.tool_settings.mesh_select_mode = (False, False, True)
    bm = bmesh.from_edit_mesh(obj.data)

    def select_bottom_of_a():
        for element in (*bm.verts, *bm.edges, *bm.faces):
            element.select = False
        bm.select_history.clear()
        bottom = next(
            f for f in bm.faces
            if f.normal.z < -0.99 and abs(f.calc_center_median().x) < 1e-6
        )
        bottom.select_set(True)
        bm.select_history.add(bottom)
        bmesh.update_edit_mesh(obj.data)

    # 기본(Match Normal): -Z를 보는 A·C 아랫면 2개만, B의 옆면은 제외
    select_bottom_of_a()
    assert bpy.ops.object.cat_select_same_pivot(axis="Z") == {"FINISHED"}
    selected = [f for f in bm.faces if f.select]
    assert len(selected) == 2, f"-Z를 보는 아랫면 2개만 선택돼야 합니다: {len(selected)}"
    assert all(f.normal.z < -0.99 for f in selected)

    # Match Normal을 끄면 Z 값만 비교해 B의 옆면 4개도 포함된다.
    select_bottom_of_a()
    assert bpy.ops.object.cat_select_same_pivot(axis="Z", match_normal=False) == {"FINISHED"}
    assert sum(f.select for f in bm.faces) == 6
    remove_all_objects()


def check_edit_mesh_verts() -> None:
    obj, bm = setup_grid()
    bpy.context.tool_settings.mesh_select_mode = (True, False, False)
    vert = min(bm.verts, key=lambda v: tuple(v.co))
    vert.select_set(True)
    bm.select_history.add(vert)
    bmesh.update_edit_mesh(obj.data)

    assert bpy.ops.object.cat_select_same_pivot(axis="X") == {"FINISHED"}
    selected = [v for v in bm.verts if v.select]
    assert len(selected) == 3, f"X가 같은 점 3개가 선택돼야 합니다: {len(selected)}"

    # 가운데 점을 기준으로 +X는 가운데·오른쪽 열(6개), -X는 가운데·왼쪽 열(6개)
    for v in bm.verts:
        v.select = False
    center = min(bm.verts, key=lambda v: v.co.length)
    center.select_set(True)
    bm.select_history.clear()
    bm.select_history.add(center)
    bmesh.update_edit_mesh(obj.data)

    assert bpy.ops.object.cat_select_same_pivot(axis="X", direction="POSITIVE") == {"FINISHED"}
    selected = [v for v in bm.verts if v.select]
    assert len(selected) == 6, f"+X 방향 점 6개가 선택돼야 합니다: {len(selected)}"
    assert all(v.co.x >= -1e-6 for v in selected)

    # 선택된 점이 모두 기준이 되므로 가운데 점만 다시 선택하고 -X를 검사한다.
    for v in bm.verts:
        v.select = False
    center.select_set(True)
    bm.select_history.clear()
    bm.select_history.add(center)
    bmesh.update_edit_mesh(obj.data)
    assert bpy.ops.object.cat_select_same_pivot(axis="X", direction="NEGATIVE") == {"FINISHED"}
    selected = [v for v in bm.verts if v.select]
    assert len(selected) == 6, f"-X 방향 점 6개가 선택돼야 합니다: {len(selected)}"
    assert all(v.co.x <= 1e-6 for v in selected)

    # Distance를 주면 기준 열(가운데)을 제외하고 오른쪽 열 3개만 선택된다.
    for v in bm.verts:
        v.select = False
    center.select_set(True)
    bm.select_history.clear()
    bm.select_history.add(center)
    bmesh.update_edit_mesh(obj.data)
    assert bpy.ops.object.cat_select_same_pivot(axis="X", direction="POSITIVE", distance=0.5) == {"FINISHED"}
    selected = [v for v in bm.verts if v.select]
    assert len(selected) == 3, f"+X Distance 0.5 점 3개가 선택돼야 합니다: {len(selected)}"
    assert not center.select, "Distance가 있으면 기준 점은 제외돼야 합니다."
    remove_all_objects()


def check_edit_mesh_normals() -> None:
    # 같은 방향으로 회전된 큐브 두 개를 한 메쉬에 만들고, 오브젝트에도 회전·비균등 스케일을 준다.
    rotation = Euler((0.3, 0.5, 0.7)).to_matrix().to_4x4()
    bm_source = bmesh.new()
    for offset in (Vector((-2.0, 0.0, 0.0)), Vector((2.0, 0.0, 0.0))):
        bmesh.ops.create_cube(bm_source, size=1.0, matrix=Matrix.Translation(offset) @ rotation)
    mesh = bpy.data.meshes.new("NormalCubes")
    bm_source.to_mesh(mesh)
    bm_source.free()
    obj = bpy.data.objects.new("NormalCubes", mesh)
    obj.rotation_euler = (0.2, 0.0, 1.1)
    obj.scale = (1.0, 2.0, 0.5)
    bpy.context.collection.objects.link(obj)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.context.tool_settings.mesh_select_mode = (False, False, True)

    bm = bmesh.from_edit_mesh(obj.data)
    for element in (*bm.verts, *bm.edges, *bm.faces):
        element.select = False
    bm.faces.ensure_lookup_table()
    face = bm.faces[0]
    face.select_set(True)
    bm.select_history.add(face)
    bmesh.update_edit_mesh(obj.data)

    # 기본(Connected)은 떨어져 있는 다른 큐브의 같은 방향 면을 고르지 않는다.
    assert bpy.ops.object.cat_select_same_normal() == {"FINISHED"}
    selected = [f for f in bm.faces if f.select]
    assert selected == [face], f"Connected면 기준 면 1개만 선택돼야 합니다: {len(selected)}"

    assert bpy.ops.object.cat_select_same_normal(connected=False) == {"FINISHED"}
    selected = [f for f in bm.faces if f.select]
    assert len(selected) == 2, f"노멀이 같은 면 2개가 선택돼야 합니다: {len(selected)}"
    assert all(f.normal.angle(face.normal) < 1e-4 for f in selected)

    # Extend로 반대쪽 면 기준을 더하면 4개, 각도를 179도로 주면 정반대(평행) 면만 빠진다.
    # 비균등 스케일 때문에 월드 공간의 이웃 면은 정확히 90도가 아니다.
    opposite = next(f for f in bm.faces if f.normal.dot(face.normal) < -0.99)
    bm.select_history.clear()
    opposite.select_set(True)
    bm.select_history.add(opposite)
    assert bpy.ops.object.cat_select_same_normal(connected=False, extend=True) == {"FINISHED"}
    assert sum(f.select for f in bm.faces) == 4

    for f in bm.faces:
        f.select = False
    face.select_set(True)
    bm.select_history.clear()
    bm.select_history.add(face)
    assert bpy.ops.object.cat_select_same_normal(angle=math.radians(179.0), connected=False) == {"FINISHED"}
    assert sum(f.select for f in bm.faces) == 10, "반대쪽 면을 뺀 10개가 선택돼야 합니다."
    # Connected면 기준 큐브 안에서 반대쪽 면을 뺀 5개만 이어진다.
    # 선택된 같은 방향 면이 모두 출발점이 되므로 기준 면만 남기고 다시 실행한다.
    for f in bm.faces:
        f.select = False
    face.select_set(True)
    bm.select_history.clear()
    bm.select_history.add(face)
    assert bpy.ops.object.cat_select_same_normal(angle=math.radians(179.0)) == {"FINISHED"}
    assert sum(f.select for f in bm.faces) == 5, "기준 큐브의 5개 면만 선택돼야 합니다."

    # 기준이 없으면 취소된다.
    for f in bm.faces:
        f.select = False
    bm.select_history.clear()
    bmesh.update_edit_mesh(obj.data)
    assert bpy.ops.object.cat_select_same_normal() == {"CANCELLED"}
    remove_all_objects()

    # 맞닿은 같은 방향 면은 Connected에서도 모두 이어져 선택된다 (2x2 평면 그리드).
    obj, bm = setup_grid()
    bpy.context.tool_settings.mesh_select_mode = (False, False, True)
    bm.faces.ensure_lookup_table()
    bm.faces[0].select_set(True)
    bm.select_history.add(bm.faces[0])
    bmesh.update_edit_mesh(obj.data)
    assert bpy.ops.object.cat_select_same_normal() == {"FINISHED"}
    assert all(f.select for f in bm.faces), "맞닿은 같은 방향 면 4개가 모두 선택돼야 합니다."

    # 점 모드: 이어진 같은 방향 점 9개 선택
    bpy.context.tool_settings.mesh_select_mode = (True, False, False)
    for element in (*bm.verts, *bm.edges, *bm.faces):
        element.select = False
    bm.verts.ensure_lookup_table()
    bm.select_history.clear()
    bm.verts[0].select_set(True)
    bm.select_history.add(bm.verts[0])
    bmesh.update_edit_mesh(obj.data)
    assert bpy.ops.object.cat_select_same_normal() == {"FINISHED"}
    assert all(v.select for v in bm.verts), "맞닿은 같은 방향 점 9개가 모두 선택돼야 합니다."
    remove_all_objects()


def check_multiple_normals() -> None:
    # 떨어진 큐브 두 개에서 윗면과 옆면을 함께 선택하면 두 방향 모두를 기준으로 삼는다.
    bm_source = bmesh.new()
    for offset in (Vector((-2.0, 0.0, 0.0)), Vector((2.0, 0.0, 0.0))):
        bmesh.ops.create_cube(bm_source, size=1.0, matrix=Matrix.Translation(offset))
    mesh = bpy.data.meshes.new("MultiNormal")
    bm_source.to_mesh(mesh)
    bm_source.free()
    obj = bpy.data.objects.new("MultiNormal", mesh)
    bpy.context.collection.objects.link(obj)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.context.tool_settings.mesh_select_mode = (False, False, True)

    bm = bmesh.from_edit_mesh(obj.data)
    for element in (*bm.verts, *bm.edges, *bm.faces):
        element.select = False
    left = [f for f in bm.faces if f.calc_center_median().x < 0.0]
    top = next(f for f in left if f.normal.z > 0.99)
    side = next(f for f in left if f.normal.y > 0.99)
    top.select_set(True)
    side.select_set(True)
    bm.select_history.clear()
    bm.select_history.add(side)
    bmesh.update_edit_mesh(obj.data)

    assert bpy.ops.object.cat_select_same_normal(connected=False) == {"FINISHED"}
    selected = [f for f in bm.faces if f.select]
    assert len(selected) == 4, f"두 방향(+Z, +Y)의 면 4개가 선택돼야 합니다: {len(selected)}"
    assert all(f.normal.z > 0.99 or f.normal.y > 0.99 for f in selected)

    # Connected면 서로 맞닿은 윗면·옆면이라도 각자 방향으로만 넓혀 기준 큐브의 두 면만 남는다.
    for f in bm.faces:
        f.select = False
    top.select_set(True)
    side.select_set(True)
    bmesh.update_edit_mesh(obj.data)
    assert bpy.ops.object.cat_select_same_normal() == {"FINISHED"}
    assert {f for f in bm.faces if f.select} == {top, side}
    remove_all_objects()

    # Object 모드: 30도 오브젝트와 45도 오브젝트를 함께 선택하면 두 회전 모두 기준이 된다.
    a = create_empty("MultiA", (0.0, 0.0, 0.0))
    b = create_empty("MultiB", (3.0, 0.0, 0.0))
    c = create_empty("MultiC", (6.0, 0.0, 0.0))
    d = create_empty("MultiD", (9.0, 0.0, 0.0))
    a.rotation_euler = (0.0, 0.0, math.radians(30.0))
    b.rotation_euler = (0.0, 0.0, math.radians(30.0))
    c.rotation_euler = (0.0, 0.0, math.radians(45.0))
    d.rotation_euler = (0.0, 0.0, math.radians(45.0))
    bpy.context.view_layer.update()
    bpy.ops.object.select_all(action="DESELECT")
    a.select_set(True)
    c.select_set(True)
    bpy.context.view_layer.objects.active = a
    assert bpy.ops.object.cat_select_same_normal() == {"FINISHED"}
    assert selected_names() == {"MultiA", "MultiB", "MultiC", "MultiD"}, selected_names()
    remove_all_objects()


def check_object_rotation() -> None:
    a = create_empty("RotA", (0.0, 0.0, 0.0))
    b = create_empty("RotB", (3.0, 0.0, 0.0))
    c = create_empty("RotC", (6.0, 0.0, 0.0))
    a.rotation_euler = (0.0, 0.0, math.radians(30.0))
    b.rotation_euler = (0.0, 0.0, math.radians(30.0))
    b.scale = (2.0, 1.0, 1.0)  # 스케일은 회전 비교에 영향을 주지 않는다.
    c.rotation_euler = (0.0, 0.0, math.radians(45.0))
    bpy.context.view_layer.update()
    bpy.ops.object.select_all(action="DESELECT")
    a.select_set(True)
    bpy.context.view_layer.objects.active = a
    assert bpy.ops.object.cat_select_same_normal() == {"FINISHED"}
    assert selected_names() == {"RotA", "RotB"}, selected_names()
    assert bpy.ops.object.cat_select_same_normal(angle=math.radians(20.0)) == {"FINISHED"}
    assert selected_names() == {"RotA", "RotB", "RotC"}, selected_names()
    remove_all_objects()


def main() -> None:
    addon, registered_here = load_addon()
    remove_all_objects()
    if registered_here:
        addon.register()
    try:
        # 바닥 타일 3개(Z=0)와 높이가 다른 오브젝트 1개
        tile_a = create_empty("TileA", (0.0, 0.0, 0.0))
        create_empty("TileB", (2.0, 0.0, 0.00001))
        create_empty("TileC", (4.0, 3.0, 0.0))
        create_empty("Table", (0.0, 3.0, 1.0))
        bpy.context.view_layer.update()

        bpy.ops.object.select_all(action="DESELECT")
        tile_a.select_set(True)
        bpy.context.view_layer.objects.active = tile_a

        assert bpy.ops.object.cat_select_same_pivot(axis="Z") == {"FINISHED"}
        assert selected_names() == {"TileA", "TileB", "TileC"}, selected_names()

        assert bpy.ops.object.cat_select_same_pivot(axis="X") == {"FINISHED"}
        assert selected_names() == {"TileA", "Table"}, selected_names()

        assert bpy.ops.object.cat_select_same_pivot(axis="Y", extend=True) == {"FINISHED"}
        assert selected_names() == {"TileA", "TileB", "Table"}, selected_names()

        # 방향 선택: TileB(X=2) 기준 +X는 TileB·TileC, -X는 TileA·TileB·Table
        tile_b = bpy.data.objects["TileB"]
        bpy.ops.object.select_all(action="DESELECT")
        tile_b.select_set(True)
        bpy.context.view_layer.objects.active = tile_b
        assert bpy.ops.object.cat_select_same_pivot(axis="X", direction="POSITIVE") == {"FINISHED"}
        assert selected_names() == {"TileB", "TileC"}, selected_names()
        assert bpy.ops.object.cat_select_same_pivot(axis="X", direction="NEGATIVE") == {"FINISHED"}
        assert selected_names() == {"TileA", "TileB", "Table"}, selected_names()
        # Z 방향은 허용 오차 안의 TileB(0.00001)를 기준과 같은 높이로 본다.
        assert bpy.ops.object.cat_select_same_pivot(axis="Z", direction="POSITIVE") == {"FINISHED"}
        assert selected_names() == {"TileA", "TileB", "TileC", "Table"}, selected_names()
        bpy.context.view_layer.objects.active = bpy.data.objects["Table"]
        assert bpy.ops.object.cat_select_same_pivot(axis="Z", direction="NEGATIVE") == {"FINISHED"}
        assert selected_names() == {"TileA", "TileB", "TileC", "Table"}, selected_names()
        assert bpy.ops.object.cat_select_same_pivot(axis="Z", direction="POSITIVE") == {"FINISHED"}
        assert selected_names() == {"Table"}, selected_names()

        # Distance: TileA(X=0) 기준 1 이상 떨어진 +X는 자신을 뺀 TileB·TileC, 3 이상이면 TileC만
        tile_a = bpy.data.objects["TileA"]
        bpy.context.view_layer.objects.active = tile_a
        assert bpy.ops.object.cat_select_same_pivot(axis="X", direction="POSITIVE", distance=1.0) == {"FINISHED"}
        assert selected_names() == {"TileB", "TileC"}, selected_names()
        assert bpy.ops.object.cat_select_same_pivot(axis="X", direction="POSITIVE", distance=3.0) == {"FINISHED"}
        assert selected_names() == {"TileC"}, selected_names()
        # 경계 거리(2)에 정확히 있는 TileB는 포함된다.
        assert bpy.ops.object.cat_select_same_pivot(axis="X", direction="POSITIVE", distance=2.0) == {"FINISHED"}
        assert selected_names() == {"TileB", "TileC"}, selected_names()
        # TileC(X=4) 기준 -X로 3 이상이면 TileA·Table만
        bpy.context.view_layer.objects.active = bpy.data.objects["TileC"]
        assert bpy.ops.object.cat_select_same_pivot(axis="X", direction="NEGATIVE", distance=3.0) == {"FINISHED"}
        assert selected_names() == {"TileA", "Table"}, selected_names()
        remove_all_objects()
        check_edit_mesh_faces()
        check_edit_mesh_multiple_faces()
        check_edit_mesh_face_normal_filter()
        check_edit_mesh_verts()
        check_edit_mesh_normals()
        check_object_rotation()
        check_multiple_normals()
    finally:
        remove_all_objects()
        if registered_here:
            addon.unregister()

    print("CatTools Select Same Pivot/Normal Blender 스모크 테스트 통과")


if __name__ == "__main__":
    main()
