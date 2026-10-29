"""Blender에서 CatTools Isolate Rotate(가상 회전으로 축에 맞춰 모델링 후 원래 자세로 복귀)를 검사합니다."""

from __future__ import annotations

import importlib
import importlib.util
import math
import tempfile
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

    spec = importlib.util.spec_from_file_location("cat_tools_isolate_smoke", ADDON_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("CatTools 모듈 로더를 생성할 수 없습니다.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.register()
    return module, True


def matrices_close(a: Matrix, b: Matrix, tolerance: float = 1e-5) -> bool:
    return all(abs(a[i][j] - b[i][j]) < tolerance for i in range(4) for j in range(4))


def make_arm():
    """A 포즈 팔: 로컬 X로 긴 막대를 Y축 기준 -40° 기울여 놓고, 몸통(부모)에 붙인다."""
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)
    body = bpy.data.objects.new("Body", None)
    bpy.context.collection.objects.link(body)
    body.location = (0.0, 0.0, 1.0)
    mesh = bpy.data.meshes.new("Arm")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Diagonal((2.0, 0.3, 0.3, 1.0)))
    bm.to_mesh(mesh)
    bm.free()
    arm = bpy.data.objects.new("Arm", mesh)
    bpy.context.collection.objects.link(arm)
    arm.parent = body
    arm.location = (1.0, 0.0, 0.5)
    arm.rotation_euler = (0.0, math.radians(40.0), 0.0)
    rig = bpy.data.objects.new("Rig", bpy.data.armatures.new("Rig"))
    bpy.context.collection.objects.link(rig)
    modifier = arm.modifiers.new("Armature", 'ARMATURE')
    modifier.object = rig
    hidden = arm.modifiers.new("ArmatureOff", 'ARMATURE')
    hidden.show_viewport = False
    bpy.context.view_layer.update()
    for obj in bpy.context.view_layer.objects:
        obj.select_set(False)
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    return arm


def arm_direction(arm) -> Vector:
    """팔의 긴 축(로컬 X)이 월드에서 가리키는 방향."""
    return (arm.matrix_world.to_3x3() @ Vector((1.0, 0.0, 0.0))).normalized()


def select_verts(obj, predicate, faces=False) -> None:
    """predicate가 참인 정점만 선택한다. faces가 참이면 면 선택도 정점 선택에 맞춰 올린다."""
    bm = bmesh.from_edit_mesh(obj.data)
    for element in (*bm.verts, *bm.edges, *bm.faces):
        element.select = False
    for vert in bm.verts:
        vert.select = predicate(vert.co)
    if faces:
        bm.select_flush(True)
    bmesh.update_edit_mesh(obj.data)


def check_align(module) -> None:
    """Align: 선택한 고리·선·면(또는 형상 전체)의 방향을 고른 축에 맞추는 가상 회전을 정한다."""
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj)
    mesh = bpy.data.meshes.new("Limb")
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=12, radius1=0.25, radius2=0.25, depth=2.0)
    bm.to_mesh(mesh)
    bm.free()
    limb = bpy.data.objects.new("Limb", mesh)
    bpy.context.collection.objects.link(limb)
    # 임의 방향으로 기울어진 팔(긴 축 = 로컬 Z)
    limb.rotation_euler = (math.radians(20.0), math.radians(50.0), math.radians(30.0))
    limb.location = (2.0, 1.0, 1.5)
    bpy.context.view_layer.update()
    limb.select_set(True)
    bpy.context.view_layer.objects.active = limb
    scene = bpy.context.scene
    basis = limb.matrix_basis.copy()

    def long_axis() -> Vector:
        bpy.context.view_layer.update()
        return limb.matrix_world.col[2].xyz.normalized()

    def aligned(axis: Vector) -> bool:
        return abs(abs(long_axis().dot(axis)) - 1.0) < 1e-4

    assert bpy.ops.view3d.cat_isolate_rotate() == {"FINISHED"}
    assert module.VIEW3D_OT_CatIsolateAlign.poll(bpy.context)
    bpy.ops.object.mode_set(mode="EDIT")

    # 1) 둘레 고리(위쪽 정점 12개, 면 선택 없음) → 고리 평면의 노멀 = 팔 길이 방향을 X에 맞춘다.
    select_verts(limb, lambda co: co.z > 0.99)
    assert bpy.ops.view3d.cat_isolate_align(axis="X") == {"FINISHED"}
    assert aligned(Vector((1.0, 0.0, 0.0))), tuple(long_axis())
    first = tuple(scene.cat_isolate_rotation)
    # 같은 버튼을 다시 눌러도(이미 돌아간 상태에서) 결과가 같다 — 진입 전 자세 기준으로 계산한다.
    assert bpy.ops.view3d.cat_isolate_align(axis="X") == {"FINISHED"}
    assert all(abs(a - b) < 1e-5 for a, b in zip(first, scene.cat_isolate_rotation))

    # 2) 길이 방향의 두 정점(한 옆선) → 선 방향을 Z에 맞춘다.
    bm = bmesh.from_edit_mesh(limb.data)
    side = min((v for v in bm.verts if abs(v.co.z) > 0.99), key=lambda v: (v.co - Vector((0.25, 0.0, 0.0))).xy.length)
    target_xy = side.co.xy.copy()
    select_verts(limb, lambda co: (co.xy - target_xy).length < 1e-5)
    assert bpy.ops.view3d.cat_isolate_align(axis="Z") == {"FINISHED"}
    assert aligned(Vector((0.0, 0.0, 1.0))), tuple(long_axis())

    # 3) 끝 뚜껑 면 → 면 노멀을 Y에 맞춘다.
    select_verts(limb, lambda co: co.z < -0.99, faces=True)
    assert sum(1 for f in bmesh.from_edit_mesh(limb.data).faces if f.select) == 1
    assert bpy.ops.view3d.cat_isolate_align(axis="Y") == {"FINISHED"}
    assert aligned(Vector((0.0, 1.0, 0.0))), tuple(long_axis())

    # 4) 아무것도 선택하지 않으면 회전값을 바꾸지 않는다.
    before = tuple(scene.cat_isolate_rotation)
    select_verts(limb, lambda co: False)
    assert bpy.ops.view3d.cat_isolate_align(axis="X") == {"CANCELLED"}
    assert tuple(scene.cat_isolate_rotation) == before

    # 5) Object 모드에서는 형상 전체의 가장 긴 축을 맞춘다.
    bpy.ops.object.mode_set(mode="OBJECT")
    assert bpy.ops.view3d.cat_isolate_align(axis="X") == {"FINISHED"}
    assert aligned(Vector((1.0, 0.0, 0.0))), tuple(long_axis())

    assert bpy.ops.view3d.cat_isolate_exit() == {"FINISHED"}
    bpy.context.view_layer.update()
    assert matrices_close(limb.matrix_basis, basis)
    assert not module.VIEW3D_OT_CatIsolateAlign.poll(bpy.context)


def main() -> None:
    module, registered_here = load_addon()
    try:
        arm = make_arm()
        scene = bpy.context.scene
        basis = arm.matrix_basis.copy()
        world = arm.matrix_world.copy()
        assert module.VIEW3D_OT_CatIsolateRotate.poll(bpy.context)
        assert not module.VIEW3D_OT_CatIsolateExit.poll(bpy.context)

        # 1) 진입: 자세는 그대로, Armature 모디파이어(켜져 있던 것만) 표시를 잠시 끈다.
        assert bpy.ops.view3d.cat_isolate_rotate() == {"FINISHED"}
        assert module.isolate_active(scene) and module.isolated_objects(scene) == [arm]
        assert not module.VIEW3D_OT_CatIsolateRotate.poll(bpy.context)
        assert matrices_close(arm.matrix_world, world)
        assert not arm.modifiers["Armature"].show_viewport
        assert list(arm[module.ISOLATE_MODIFIERS_PROP]) == ["Armature"]

        # 2) 가상 회전: 팔이 기울어진 만큼(+40°) 반대로 돌리면 팔이 월드 X축과 나란해진다.
        pivot = Vector(scene[module.ISOLATE_PIVOT_PROP])
        scene.cat_isolate_rotation = (0.0, math.radians(-40.0), 0.0)
        bpy.context.view_layer.update()
        assert (arm_direction(arm) - Vector((1.0, 0.0, 0.0))).length < 1e-5, tuple(arm_direction(arm))
        # 기준점(바운딩 박스 중심)은 돌려도 제자리에 있다.
        center = sum((arm.matrix_world @ Vector(c) for c in arm.bound_box), Vector()) / 8.0
        assert (center - pivot).length < 1e-5, (center, pivot)

        # 3) Isolate 중 Edit 모드에서 월드 X축(= 팔 방향)으로 끝 정점들을 0.5 늘린다.
        bpy.ops.object.mode_set(mode="EDIT")
        bm = bmesh.from_edit_mesh(arm.data)
        inverse = arm.matrix_world.inverted().to_3x3()
        tip = [vert for vert in bm.verts if vert.co.x > 0.9]
        assert len(tip) == 4
        for vert in tip:
            vert.co += inverse @ Vector((0.5, 0.0, 0.0))
        bmesh.update_edit_mesh(arm.data)
        # Edit 모드에서도 회전값을 바꿀 수 있다.
        scene.cat_isolate_rotation = (0.0, math.radians(-40.0), math.radians(10.0))
        scene.cat_isolate_rotation = (0.0, math.radians(-40.0), 0.0)

        # 4) 해제: 원래 matrix_basis로 정확히 돌아가고, 편집은 원래 자세의 팔 방향(로컬 X) 연장으로 남는다.
        assert bpy.ops.view3d.cat_isolate_exit() == {"FINISHED"}
        bpy.ops.object.mode_set(mode="OBJECT")
        bpy.context.view_layer.update()
        assert matrices_close(arm.matrix_basis, basis) and matrices_close(arm.matrix_world, world)
        assert not module.isolate_active(scene) and module.isolated_objects(scene) == []
        assert tuple(scene.cat_isolate_rotation) == (0.0, 0.0, 0.0)
        assert arm.modifiers["Armature"].show_viewport and not arm.modifiers["ArmatureOff"].show_viewport
        assert all(key not in arm for key in (
            module.ISOLATE_WORLD_PROP, module.ISOLATE_BASIS_PROP, module.ISOLATE_MODIFIERS_PROP))
        xs = sorted({round(vert.co.x, 5) for vert in arm.data.vertices})
        assert xs == [-1.0, 1.5], xs
        assert all(abs(vert.co.y) <= 0.15 + 1e-6 and abs(vert.co.z) <= 0.15 + 1e-6 for vert in arm.data.vertices)

        # 5) Isolate 중 저장·다시 열기를 해도 해제하면 원래 자세로 돌아간다.
        assert bpy.ops.view3d.cat_isolate_rotate() == {"FINISHED"}
        scene.cat_isolate_rotation = (math.radians(15.0), math.radians(-40.0), 0.0)
        path = Path(tempfile.mkdtemp()) / "isolate.blend"
        bpy.ops.wm.save_as_mainfile(filepath=str(path))
        bpy.ops.wm.open_mainfile(filepath=str(path))
        scene = bpy.context.scene
        arm = bpy.data.objects["Arm"]
        assert module.isolate_active(scene)
        assert abs(scene.cat_isolate_rotation[0] - math.radians(15.0)) < 1e-6
        assert not matrices_close(arm.matrix_world, world)
        assert bpy.ops.view3d.cat_isolate_exit() == {"FINISHED"}
        bpy.context.view_layer.update()
        assert matrices_close(arm.matrix_basis, basis) and matrices_close(arm.matrix_world, world)
        assert arm.modifiers["Armature"].show_viewport

        check_align(module)
        print("CatTools isolate rotate smoke: OK")
    finally:
        if registered_here:
            module.unregister()


main()
