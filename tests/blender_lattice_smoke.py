"""Blender에서 CatTools Lattice가 실제 형상 크기·중심에 맞고 축별 해상도를 쓰는지 검사합니다."""

from __future__ import annotations

import importlib
import importlib.util
import math
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix, Quaternion, Vector


ROOT = Path(__file__).resolve().parents[1]
ADDON_PATH = ROOT / "__init__.py"
MODULE_NAME = "bl_ext.user_default.cat_tools"
EPSILON = 1e-4


def load_addon():
    if MODULE_NAME in bpy.context.preferences.addons:
        return importlib.import_module(MODULE_NAME), False

    spec = importlib.util.spec_from_file_location("cat_tools_lattice_smoke", ADDON_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("CatTools 모듈 로더를 생성할 수 없습니다.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.register()
    return module, True


def remove_all_objects() -> None:
    if bpy.context.object is not None and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def create_offset_box(name: str):
    """오리진(0,0,0)에서 멀리 떨어진 곳에 형상이 있는 2x4x1 상자를 회전·스케일된 오브젝트로 만든다."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((3.0, 1.0, 0.5)) @ Matrix.Diagonal((2.0, 4.0, 1.0, 1.0)))
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    obj.location = (1.0, -2.0, 0.5)
    obj.rotation_euler = (0.0, 0.0, math.radians(30.0))
    obj.scale = (1.0, 0.5, 2.0)
    bpy.context.collection.objects.link(obj)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    return obj


def evaluated_world_verts(obj):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    return [evaluated.matrix_world @ v.co for v in evaluated.data.vertices]


def create_tall_box(name: str):
    """X 1 · Y 1 · Z 4 크기의 세로로 긴 상자를 오리진에서 떨어진 곳에 만든다."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((2.0, 0.0, 2.0)) @ Matrix.Diagonal((1.0, 1.0, 4.0, 1.0)))
    # 높이 방향으로 잘게 나눠 래티스 변형이 정점에 드러나게 한다.
    bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=7, use_grid_fill=True)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    return obj


def check_handles(addon) -> None:
    """선택 핸들: 클릭 연산자가 점·단면을 고르고 Edit 모드로 들어가는지 검사한다. 실제 클릭·G·R·S는 GUI 검사에서 확인한다."""
    obj = create_tall_box("HandleTarget")
    obj.rotation_euler = (0.0, 0.0, math.radians(30.0))
    bpy.context.view_layer.update()
    assert bpy.ops.wm.add_lattice(resolution_mode="AXIS", resolution_z=2) == {"FINISHED"}
    lattice = bpy.data.objects["HandleTarget_Lattice"]
    assert lattice.get(addon.LATTICE_GIZMO_PROP) is True, "Handles 기본값이 꺼져 있습니다."
    assert not any(o.type == "ARMATURE" for o in bpy.data.objects), "Armature 가이드를 만들지 않아야 합니다."
    assert addon.VIEW3D_GGT_CatLatticeHandles.poll(bpy.context), "래티스를 선택했는데 핸들이 뜨지 않습니다."
    points = lattice.data.points

    # X·Y·Z 각 축 단면이 모두 있다 (2 x 2 x 4 점).
    for axis, count in enumerate((2, 2, 4)):
        for slice_index in range(count):
            assert len(addon.lattice_slice_indices(lattice, axis, slice_index)) == len(points) // count

    # 단면 핸들은 래티스 바깥 레일에 있어 점 핸들과 겹치지 않는다.
    inverse = lattice.matrix_world.inverted()
    for axis in range(3):
        local = inverse @ addon.lattice_slice_handle_position(lattice, axis, 0)
        side = (axis + 1) % 3
        assert local[side] < -0.5, f"{'XYZ'[axis]} 단면 핸들이 래티스 안쪽에 있습니다: {tuple(local)}"

    # 점 핸들 클릭: Object 모드에서 래티스 Edit 모드로 들어가 그 점만 선택한다.
    assert bpy.ops.lattice.cat_select_handle(kind="POINT", index=5) == {"FINISHED"}
    assert bpy.context.mode == "EDIT_LATTICE"
    assert addon.VIEW3D_GGT_CatLatticeHandles.poll(bpy.context), "Edit 모드에서 핸들이 사라졌습니다."
    points = lattice.data.points
    assert [i for i, p in enumerate(points) if p.select] == [5]

    # 단면 핸들 클릭: 그 단면 점만 선택한다.
    assert bpy.ops.lattice.cat_select_handle(kind="SLICE", axis=2, index=3) == {"FINISHED"}
    expected = set(addon.lattice_slice_indices(lattice, 2, 3))
    assert {i for i, p in enumerate(points) if p.select} == expected

    # Shift+클릭(extend): 추가하고, 이미 선택된 대상이면 뺀다.
    assert bpy.ops.lattice.cat_select_handle(kind="POINT", index=0, extend=True) == {"FINISHED"}
    assert {i for i, p in enumerate(points) if p.select} == expected | {0}
    assert bpy.ops.lattice.cat_select_handle(kind="SLICE", axis=2, index=3, extend=True) == {"FINISHED"}
    assert {i for i, p in enumerate(points) if p.select} == {0}

    # 선택한 점은 Blender 기본 변형(축 고정)으로 움직인다.
    before = [p.co_deform.copy() for p in points]
    bpy.ops.transform.translate(value=(0.0, 0.0, 0.4), constraint_axis=(False, False, True))
    moved = [i for i, p in enumerate(points) if (p.co_deform - before[i]).length > 1e-6]
    assert moved == [0], moved
    bpy.ops.object.mode_set(mode="OBJECT")
    remove_all_objects()

    # Handles를 끄면 핸들이 뜨지 않는다.
    create_tall_box("NoHandles")
    assert bpy.ops.wm.add_lattice(handles=False) == {"FINISHED"}
    assert not addon.VIEW3D_GGT_CatLatticeHandles.poll(bpy.context)
    remove_all_objects()


def main() -> None:
    addon, registered_here = load_addon()
    remove_all_objects()
    try:
        obj = create_offset_box("LatticeTarget")
        before = [obj.matrix_world @ v.co for v in obj.data.vertices]

        assert bpy.ops.wm.add_lattice() == {"FINISHED"}
        lattice = bpy.data.objects["LatticeTarget_Lattice"]
        assert obj.modifiers["Lattice"].object is lattice, "Lattice 모디파이어가 연결되지 않았습니다."
        assert bpy.context.view_layer.objects.active is lattice, "만든 래티스가 활성화되지 않았습니다."
        # 실행 후 상태(래티스만 선택)에서도 poll이 통과해야 Adjust Last Operation 패널이 뜬다.
        assert bpy.ops.wm.add_lattice.poll(), "실행 후 poll이 실패해 Adjust Last Operation 패널이 숨겨집니다."

        # 래티스 중심은 오리진이 아니라 형상 중심이고, 크기는 실제 형상 크기 + Margin이다.
        geometry_center = sum(before, Vector()) / len(before)
        assert (lattice.matrix_world.translation - geometry_center).length < EPSILON, (
            f"래티스 중심이 형상 중심과 다릅니다: {lattice.matrix_world.translation} != {geometry_center}"
        )
        _loc, rotation, scale = lattice.matrix_world.decompose()
        expected = Vector((2.0 * 1.0 + 0.1, 4.0 * 0.5 + 0.1, 1.0 * 2.0 + 0.1))
        assert (scale - expected).length < EPSILON, f"래티스 크기가 다릅니다: {scale} != {expected}"
        assert rotation.rotation_difference(obj.matrix_world.to_quaternion()).angle < EPSILON, "래티스가 오브젝트 회전을 따르지 않습니다."

        # 모든 정점이 래티스 안에 있고, 변형 전 래티스는 형상을 바꾸지 않는다.
        inverse = lattice.matrix_world.inverted()
        for co in before:
            local = inverse @ co
            assert all(abs(local[axis]) <= 0.5 + EPSILON for axis in range(3)), f"정점이 래티스 밖에 있습니다: {local}"
        after = evaluated_world_verts(obj)
        assert all((a - b).length < 1e-3 for a, b in zip(before, after)), "변형 전 래티스가 형상을 바꿨습니다."
        assert (lattice.data.points_u, lattice.data.points_v, lattice.data.points_w) == (2, 2, 2)
        remove_all_objects()

        # Uniform 해상도
        obj = create_offset_box("LatticeUniform")
        assert bpy.ops.wm.add_lattice(lattice_resolution=2) == {"FINISHED"}
        data = bpy.data.objects["LatticeUniform_Lattice"].data
        assert (data.points_u, data.points_v, data.points_w) == (4, 4, 4)
        # 해상도를 올려도 래티스 점은 -0.5~0.5 범위(= 형상 + Margin 크기)를 유지해야 한다.
        extent = max(abs(c) for point in data.points for c in point.co)
        assert abs(extent - 0.5) < EPSILON, f"래티스 점이 형상 밖으로 벗어났습니다: {extent}"
        remove_all_objects()

        # 축별 해상도: Per Axis에서는 X·Y·Z를 각각 나눈다.
        obj = create_offset_box("LatticeAxis")
        assert bpy.ops.wm.add_lattice(
            resolution_mode="AXIS", lattice_resolution=5, resolution_x=1, resolution_y=3, resolution_z=0
        ) == {"FINISHED"}
        data = bpy.data.objects["LatticeAxis_Lattice"].data
        assert (data.points_u, data.points_v, data.points_w) == (3, 5, 2), (data.points_u, data.points_v, data.points_w)
        remove_all_objects()

        # 여러 오브젝트를 선택하면 오브젝트마다 래티스를 만든다. Empty는 건너뛴다.
        first = create_offset_box("LatticeMultiA")
        second = create_offset_box("LatticeMultiB")
        empty = bpy.data.objects.new("LatticeEmpty", None)
        bpy.context.collection.objects.link(empty)
        for target in (first, second, empty):
            target.select_set(True)
        assert bpy.ops.wm.add_lattice() == {"FINISHED"}
        assert "LatticeMultiA_Lattice" in bpy.data.objects and "LatticeMultiB_Lattice" in bpy.data.objects
        assert "LatticeEmpty_Lattice" not in bpy.data.objects
        remove_all_objects()

        # 메쉬가 없으면 아무것도 만들지 않고 취소된다.
        empty = bpy.data.objects.new("OnlyEmpty", None)
        bpy.context.collection.objects.link(empty)
        bpy.ops.object.select_all(action="DESELECT")
        empty.select_set(True)
        bpy.context.view_layer.objects.active = empty
        assert bpy.ops.wm.add_lattice() == {"CANCELLED"}, "Empty만 선택했는데 Lattice가 실행되었습니다."
        assert "OnlyEmpty_Lattice" not in bpy.data.objects

        remove_all_objects()
        check_handles(addon)

        print("CatTools Lattice smoke test passed")
    finally:
        remove_all_objects()
        if registered_here:
            addon.unregister()


main()
