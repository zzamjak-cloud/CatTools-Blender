"""Blender에서 CatTools Circle Array의 방향 맞추기와 회전 옵션을 검사합니다."""

from __future__ import annotations

import importlib
import importlib.util
import math
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
ADDON_PATH = ROOT / "__init__.py"
MODULE_NAME = "bl_ext.user_default.cat_tools"
EPSILON = 1e-4


def load_addon():
    if MODULE_NAME in bpy.context.preferences.addons:
        return importlib.import_module(MODULE_NAME), False

    spec = importlib.util.spec_from_file_location("cat_tools_circle_array_smoke", ADDON_PATH)
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


def run_circle_array(**options):
    """원본 큐브 하나로 Circle Array를 실행하고 (원본, 복제본 목록)을 돌려준다."""
    remove_all_objects()
    bpy.ops.mesh.primitive_cube_add(size=1.0)
    origin = bpy.context.object
    origin.name = "CatToolsCircleOrigin"
    result = bpy.ops.object.circle_array(segment=4, radius=2, **options)
    assert result == {"FINISHED"}, f"Circle Array 실행 실패: {result}"
    copies = [obj for obj in bpy.context.scene.objects if obj is not origin]
    assert len(copies) == 4, f"복제본 수가 다릅니다: {len(copies)}"
    for copy in copies:
        assert copy.data is origin.data, "복제본이 원본 메쉬 데이터를 공유하지 않습니다."
        assert abs(copy.location.length - 2.0) < EPSILON, f"반지름이 다릅니다: {copy.location.length}"
    return origin, copies


def local_axis(obj, axis: Vector) -> Vector:
    return (obj.matrix_world.to_3x3() @ axis).normalized()


def main() -> None:
    addon, registered_here = load_addon()
    try:
        # 기본값(None)은 원본 회전을 그대로 유지한다.
        _origin, copies = run_circle_array()
        for copy in copies:
            assert copy.matrix_world.to_euler().to_quaternion().angle < EPSILON, "기본값에서 복제본이 회전되었습니다."

        # Center: 로컬 -Y가 원 중앙을 향하고 위쪽(Z)은 유지된다.
        _origin, copies = run_circle_array(orientation="CENTER")
        for copy in copies:
            to_center = (-copy.location).normalized()
            front = local_axis(copy, Vector((0.0, -1.0, 0.0)))
            assert (front - to_center).length < EPSILON, f"{copy.name}의 -Y가 중앙을 보지 않습니다: {front}"
            assert (local_axis(copy, Vector((0.0, 0.0, 1.0))) - Vector((0.0, 0.0, 1.0))).length < EPSILON

        # Outward + Front Axis X: 로컬 +X가 바깥을 향한다.
        _origin, copies = run_circle_array(orientation="OUTWARD", front_axis="X")
        for copy in copies:
            outward = copy.location.normalized()
            front = local_axis(copy, Vector((1.0, 0.0, 0.0)))
            assert (front - outward).length < EPSILON, f"{copy.name}의 +X가 바깥을 보지 않습니다: {front}"

        # Center + 추가 회전: 로컬 Z로 90도 더 돌리면 -Y 대신 로컬 -X가 중앙을 향한다.
        _origin, copies = run_circle_array(orientation="CENTER", rotation=(0.0, 0.0, math.radians(90.0)))
        for copy in copies:
            to_center = (-copy.location).normalized()
            front = local_axis(copy, Vector((-1.0, 0.0, 0.0)))
            assert (front - to_center).length < EPSILON, f"{copy.name}의 추가 회전이 맞지 않습니다: {front}"

        # None + 추가 회전: 모든 복제본에 같은 회전값이 들어간다.
        _origin, copies = run_circle_array(rotation=(math.radians(30.0), 0.0, 0.0))
        for copy in copies:
            euler = copy.matrix_world.to_euler()
            assert abs(euler.x - math.radians(30.0)) < EPSILON and abs(euler.z) < EPSILON, f"회전값이 다릅니다: {euler}"

        # Quaternion 회전 모드 원본도 행렬로 같은 방향을 얻는다.
        remove_all_objects()
        bpy.ops.mesh.primitive_cube_add(size=1.0)
        origin = bpy.context.object
        origin.rotation_mode = "QUATERNION"
        assert bpy.ops.object.circle_array(segment=3, radius=1, orientation="CENTER") == {"FINISHED"}
        for copy in (obj for obj in bpy.context.scene.objects if obj is not origin):
            front = local_axis(copy, Vector((0.0, -1.0, 0.0)))
            assert (front - (-copy.location).normalized()).length < EPSILON, "Quaternion 모드에서 방향이 다릅니다."

        print("CatTools Circle Array smoke test passed")
    finally:
        remove_all_objects()
        if registered_here:
            addon.unregister()


main()
