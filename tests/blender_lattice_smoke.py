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


def check_guides() -> None:
    obj = create_tall_box("GuideTarget")
    rest = evaluated_world_verts(obj)
    assert bpy.ops.wm.add_lattice(resolution_mode="AXIS", resolution_z=2, add_guides=True) == {"FINISHED"}
    lattice = bpy.data.objects["GuideTarget_Lattice"]
    rig = bpy.data.objects["GuideTarget_LatticeGuide"]
    assert rig.type == "ARMATURE"
    assert bpy.context.view_layer.objects.active is rig, "가이드 아마추어가 활성화되지 않았습니다."
    assert bpy.context.object.mode == "OBJECT"

    # Auto 축은 가장 긴 Z축이고, Z 해상도 2 → 단면 4개 → 본 4개의 체인
    bones = rig.data.bones
    assert [bone.name for bone in bones] == [f"Guide.{index:03d}" for index in range(4)], [b.name for b in bones]
    for index in range(1, 4):
        assert bones[index].parent == bones[index - 1], "가이드 본이 체인으로 이어지지 않았습니다."
        assert not bones[index].use_connect, "가이드 본이 붙어 있으면 개별 이동이 안 됩니다."
    heads = [rig.matrix_world @ bone.head_local for bone in bones]
    assert all(heads[i].z < heads[i + 1].z for i in range(3)), heads

    # 단면마다 래티스 점 4개(2x2)가 해당 본 그룹에 묶인다.
    data = lattice.data
    assert (data.points_u, data.points_v, data.points_w) == (2, 2, 4)
    for index, bone in enumerate(bones):
        group = lattice.vertex_groups[bone.name]
        members = []
        for point_index, point in enumerate(data.points):
            if any(g.group == group.index and g.weight == 1.0 for g in point.groups):
                members.append(point_index)
        assert len(members) == 4, f"{bone.name} 단면 점 수가 다릅니다: {members}"
        assert all(point_index // 4 == index for point_index in members), members
    assert lattice.modifiers["Guides"].object is rig

    # 포즈를 주지 않으면 형상이 그대로다.
    assert max((a - b).length for a, b in zip(rest, evaluated_world_verts(obj))) < 1e-4

    # 첫 본(뿌리)을 옮기면 체인 전체가 따라와 형상이 통째로 이동한다.
    root = rig.pose.bones["Guide.000"]
    root.location = (0.0, 0.0, 0.5)
    bpy.context.view_layer.update()
    moved = evaluated_world_verts(obj)
    offsets = [b - a for a, b in zip(rest, moved)]
    assert all((offset - offsets[0]).length < 1e-3 for offset in offsets), "뿌리 이동이 형상을 통째로 옮기지 않았습니다."
    assert abs(offsets[0].length - 0.5) < 1e-3, offsets[0]
    root.location = (0.0, 0.0, 0.0)

    # 맨 위 본만 키우면 위쪽은 넓어지고 맨 아래는 거의 그대로다.
    top = rig.pose.bones["Guide.003"]
    top.scale = (2.0, 1.0, 2.0)
    bpy.context.view_layer.update()
    scaled = evaluated_world_verts(obj)
    # 본 축 위의 점은 스케일·비틀기로 움직이지 않으므로 축에서 가장 먼 위·아래 모서리 정점을 쓴다.
    top_index = max(range(len(rest)), key=lambda i: (round(rest[i].z, 4), abs(rest[i].x - 2.0) + abs(rest[i].y)))
    bottom_index = min(range(len(rest)), key=lambda i: (round(rest[i].z, 4), -(abs(rest[i].x - 2.0) + abs(rest[i].y))))
    assert (scaled[top_index] - rest[top_index]).length > 0.1, "맨 위 가이드 스케일이 반영되지 않았습니다."
    assert (scaled[bottom_index] - rest[bottom_index]).length < 0.05, "맨 아래가 함께 변형되었습니다."
    top.scale = (1.0, 1.0, 1.0)

    # 맨 아래 본을 줄여도 스케일은 위 단면으로 전달되지 않는다.
    root.scale = (0.5, 1.0, 0.5)
    bpy.context.view_layer.update()
    tapered = evaluated_world_verts(obj)
    assert (tapered[bottom_index] - rest[bottom_index]).length > 0.1, "맨 아래 가이드 스케일이 반영되지 않았습니다."
    assert (tapered[top_index] - rest[top_index]).length < 0.05, "아래 가이드 스케일이 위로 전달되었습니다."
    root.scale = (1.0, 1.0, 1.0)

    # 가운데 본을 비틀면 그 위쪽 단면이 회전한다 (FK).
    middle = rig.pose.bones["Guide.001"]
    middle.rotation_quaternion = Quaternion((0.0, 1.0, 0.0), math.radians(45.0))
    bpy.context.view_layer.update()
    twisted = evaluated_world_verts(obj)
    assert (twisted[top_index] - rest[top_index]).length > 0.1, "가운데 가이드 회전이 위쪽에 전달되지 않았습니다."
    remove_all_objects()

    # 축을 직접 고르면 그 축으로 단면을 나눈다.
    create_tall_box("GuideAxisX")
    assert bpy.ops.wm.add_lattice(lattice_resolution=1, add_guides=True, guide_axis="X") == {"FINISHED"}
    rig = bpy.data.objects["GuideAxisX_LatticeGuide"]
    assert len(rig.data.bones) == 3
    heads = [rig.matrix_world @ bone.head_local for bone in rig.data.bones]
    assert all(abs(head.z - heads[0].z) < 1e-4 for head in heads) and heads[0].x < heads[2].x, heads
    remove_all_objects()


def main() -> None:
    addon, registered_here = load_addon()
    remove_all_objects()
    try:
        obj = create_offset_box("LatticeTarget")
        before = [obj.matrix_world @ v.co for v in obj.data.vertices]

        assert bpy.ops.wm.add_lattice(add_guides=False) == {"FINISHED"}
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

        # 기본값으로 실행하면 가이드가 함께 만들어지고, 가이드가 선택된 상태에서도 poll이 통과한다.
        create_tall_box("GuideDefault")
        assert bpy.ops.wm.add_lattice() == {"FINISHED"}
        assert "GuideDefault_LatticeGuide" in bpy.data.objects, "Guides 기본값이 꺼져 있습니다."
        assert bpy.ops.wm.add_lattice.poll(), "가이드 생성 후 poll이 실패해 Adjust Last Operation 패널이 숨겨집니다."

        remove_all_objects()
        check_guides()

        print("CatTools Lattice smoke test passed")
    finally:
        remove_all_objects()
        if registered_here:
            addon.unregister()


main()
