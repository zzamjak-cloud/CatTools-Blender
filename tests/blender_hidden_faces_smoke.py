"""Blender에서 CatTools Select Hidden Faces 연산자의 실제 동작을 검사합니다."""

from __future__ import annotations

import importlib
import importlib.util
import time
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix, Vector


ROOT = Path(__file__).resolve().parents[1]
ADDON_PATH = ROOT / "__init__.py"
MODULE_NAME = "bl_ext.user_default.cat_tools"


def load_addon():
    if MODULE_NAME in bpy.context.preferences.addons:
        return importlib.import_module(MODULE_NAME), False

    spec = importlib.util.spec_from_file_location("cat_tools_hidden_faces_smoke", ADDON_PATH)
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


def create_cubes_object(name: str, cubes, location=(0.0, 0.0, 0.0)):
    """(중심, 크기) 목록의 큐브들을 한 메쉬로 만든 오브젝트를 만든다."""
    bm = bmesh.new()
    for center, size in cubes:
        bmesh.ops.create_cube(bm, size=size, matrix=Matrix.Translation(Vector(center)))
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    obj.location = location
    bpy.context.collection.objects.link(obj)
    return obj


def enter_edit(obj):
    if bpy.context.object is not None and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    return bmesh.from_edit_mesh(obj.data)


def selected_centers(bm):
    return [f.calc_center_median() for f in bm.faces if f.select]


def check_touching_blocks() -> None:
    # 크기 2 큐브 두 개가 X=1에서 맞닿아 있어, 맞닿은 면 2개만 은면이다.
    obj = create_cubes_object("Blocks", [((0.0, 0.0, 0.0), 2.0), ((2.0, 0.0, 0.0), 2.0)], location=(5.0, 0.0, 0.0))
    bm = enter_edit(obj)
    assert bpy.ops.object.cat_select_hidden_faces() == {"FINISHED"}
    centers = selected_centers(bm)
    assert len(centers) == 2, f"맞닿은 면 2개가 선택돼야 합니다: {len(centers)}"
    assert all(abs(c.x - 1.0) < 1e-6 for c in centers), centers
    remove_all_objects()


def check_enclosed_cube() -> None:
    # 큰 큐브 안에 갇힌 작은 큐브의 6개 면은 모두 은면이고, 큰 큐브 바깥 면은 보인다.
    obj = create_cubes_object("Nested", [((0.0, 0.0, 0.0), 4.0), ((0.0, 0.0, 0.0), 1.0)])
    bm = enter_edit(obj)
    assert bpy.ops.object.cat_select_hidden_faces() == {"FINISHED"}
    centers = selected_centers(bm)
    assert len(centers) == 6, f"안쪽 큐브 면 6개가 선택돼야 합니다: {len(centers)}"
    assert all(c.length < 0.6 for c in centers), centers
    remove_all_objects()


def check_other_objects_and_partial() -> None:
    # 2x1 직육면체 위에 큐브 오브젝트를 반만 걸쳐 올리면 윗면은 일부만 가려져 은면이 아니다.
    base = create_cubes_object("Base", [((0.0, 0.0, 0.0), 2.0)])
    cover = create_cubes_object("Cover", [((0.0, 0.0, 0.0), 2.0)], location=(0.0, 0.0, 2.0))
    bm = enter_edit(base)
    # 다른 오브젝트가 윗면을 정확히 덮으면 은면으로 선택된다.
    assert bpy.ops.object.cat_select_hidden_faces() == {"FINISHED"}
    centers = selected_centers(bm)
    assert len(centers) == 1 and abs(centers[0].z - 1.0) < 1e-6, centers
    # Other Objects를 끄면 자기 형상만 보므로 은면이 없다.
    assert bpy.ops.object.cat_select_hidden_faces(include_others=False) == {"FINISHED"}
    assert not selected_centers(bm)

    # 덮개를 반만 걸치면 윗면 일부가 보이므로 선택되지 않는다.
    bpy.ops.object.mode_set(mode="OBJECT")
    cover.location.x = 1.0
    bm = enter_edit(base)
    assert bpy.ops.object.cat_select_hidden_faces() == {"FINISHED"}
    assert not selected_centers(bm), "일부라도 보이는 면은 선택되지 않아야 합니다."
    remove_all_objects()


def check_partially_buried_column() -> None:
    # 굴뚝처럼 몸체를 뚫고 올라와 위끝이 캡에 묻힌 기둥: 옆면 중심(z=0.45)과 양 끝 근처는 가려져도
    # 몸체 윗면(z=1)과 캡 아랫면(z=1.3) 사이 구간이 보이므로 옆면은 은면이 아니다.
    bm_source = bmesh.new()
    bmesh.ops.create_cube(bm_source, size=2.0)
    column = Matrix.Translation((0.0, 0.0, 0.45)) @ Matrix.Diagonal((0.5, 0.5, 1.9, 1.0))
    bmesh.ops.create_cube(bm_source, size=1.0, matrix=column)
    cap = Matrix.Translation((0.0, 0.0, 1.45)) @ Matrix.Diagonal((1.0, 1.0, 0.3, 1.0))
    bmesh.ops.create_cube(bm_source, size=1.0, matrix=cap)
    mesh = bpy.data.meshes.new("Chimney")
    bm_source.to_mesh(mesh)
    bm_source.free()
    obj = bpy.data.objects.new("Chimney", mesh)
    bpy.context.collection.objects.link(obj)

    bm = enter_edit(obj)
    assert bpy.ops.object.cat_select_hidden_faces() == {"FINISHED"}
    column_sides = [
        f for f in bm.faces
        if abs(f.normal.z) < 1e-6 and abs(f.calc_center_median().z - 0.45) < 1e-6
    ]
    assert len(column_sides) == 4, len(column_sides)
    assert not any(f.select for f in column_sides), "일부가 드러난 기둥 옆면은 선택되지 않아야 합니다."
    remove_all_objects()


def check_non_planar_quads() -> None:
    # 꼭짓점 높이가 ±0.002씩 엇갈린 살짝 꼬인 사각형은 면 위 검사 지점이 BVH 삼각형 아래에 놓여
    # 광선이 자기 면에 맞는다. 자기 면은 가림체가 아니므로 홀로 놓인 꼬인 면은 은면이 아니다.
    # 꼭짓점 시작 순서(대각선 방향)와 노멀 방향을 모두 바꿔 가며 검사한다.
    bm_source = bmesh.new()
    corners = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    warp = 0.002
    for slot, (rotation, reverse) in enumerate([(0, False), (0, True), (1, False), (1, True)]):
        coords = [(x + slot * 2.0, y, warp if index % 2 == 0 else -warp) for index, (x, y) in enumerate(corners)]
        coords = coords[rotation:] + coords[:rotation]
        if reverse:
            coords.reverse()
        bm_source.faces.new([bm_source.verts.new(co) for co in coords])
    mesh = bpy.data.meshes.new("Warped")
    bm_source.to_mesh(mesh)
    bm_source.free()
    obj = bpy.data.objects.new("Warped", mesh)
    bpy.context.collection.objects.link(obj)

    bm = enter_edit(obj)
    assert bpy.ops.object.cat_select_hidden_faces() == {"FINISHED"}
    assert not selected_centers(bm), f"홀로 놓인 꼬인 면은 선택되지 않아야 합니다: {selected_centers(bm)}"
    remove_all_objects()


def check_performance() -> None:
    # 블록 10x10x2 격자(맞닿은 면 다수)도 실용적인 시간 안에 끝나야 한다.
    cubes = [((x * 1.0, y * 1.0, z * 1.0), 1.0) for x in range(10) for y in range(10) for z in range(2)]
    obj = create_cubes_object("Grid", cubes)
    bm = enter_edit(obj)
    started = time.perf_counter()
    assert bpy.ops.object.cat_select_hidden_faces() == {"FINISHED"}
    elapsed = time.perf_counter() - started
    selected = sum(f.select for f in bm.faces)
    # 맞닿은 면 쌍: X 9*10*2 + Y 10*9*2 + Z 10*10*1 = 460쌍 → 920면
    assert selected == 920, f"맞닿은 면 920개가 선택돼야 합니다: {selected}"
    print(f"블록 200개({len(bm.faces)}면) 은면 판정: {elapsed:.2f}초")
    remove_all_objects()


def main() -> None:
    addon, registered_here = load_addon()
    remove_all_objects()
    if registered_here:
        addon.register()
    try:
        check_touching_blocks()
        check_enclosed_cube()
        check_other_objects_and_partial()
        check_partially_buried_column()
        check_non_planar_quads()
        check_performance()
    finally:
        remove_all_objects()
        if registered_here:
            addon.unregister()

    print("CatTools Select Hidden Faces Blender 스모크 테스트 통과")


if __name__ == "__main__":
    main()
