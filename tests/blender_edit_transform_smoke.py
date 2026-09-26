"""Blender에서 CatTools Edit 모드 선택 요소 Transform 동작을 검사합니다."""

from __future__ import annotations

import importlib
import importlib.util
import math
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
ADDON_PATH = ROOT / "__init__.py"
MODULE_NAME = "bl_ext.user_default.cat_tools"
TOLERANCE = 1e-5


def load_addon():
    if MODULE_NAME in bpy.context.preferences.addons:
        return importlib.import_module(MODULE_NAME), False

    spec = importlib.util.spec_from_file_location("cat_tools_edit_transform_smoke", ADDON_PATH)
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


def assert_vector(actual, expected, message: str) -> None:
    for a, e in zip(actual, expected):
        if not math.isclose(a, e, abs_tol=TOLERANCE):
            raise AssertionError(f"{message}: {tuple(actual)} != {tuple(expected)}")


def setup_plane():
    # 오브젝트 이동을 두어 월드 좌표 환산을 함께 검증한다.
    bpy.ops.mesh.primitive_plane_add(size=2.0, location=(10.0, 0.0, 0.0))
    obj = bpy.context.object
    bpy.ops.object.mode_set(mode="EDIT")
    bm = bmesh.from_edit_mesh(obj.data)
    bm.select_mode = {'FACE'}
    for face in bm.faces:
        face.select_set(True)
    bm.select_flush_mode()
    bmesh.update_edit_mesh(obj.data)
    return obj


def world_verts(obj):
    bm = bmesh.from_edit_mesh(obj.data)
    return [obj.matrix_world @ v.co for v in bm.verts]


def test_location_follows_selection() -> None:
    obj = setup_plane()
    scene = bpy.context.scene
    assert_vector(scene.cat_edit_location, (10.0, 0.0, 0.0), "면 중앙값 위치")
    scene.cat_edit_location = (10.0, 0.0, 3.0)
    for co in world_verts(obj):
        assert math.isclose(co.z, 3.0, abs_tol=TOLERANCE), "면 전체가 Z로 이동해야 합니다."
    assert_vector(obj.location, (10.0, 0.0, 0.0), "오브젝트 위치는 변하지 않아야 합니다.")

    # 한 정점만 선택하면 그 정점 위치를 보여준다.
    bm = bmesh.from_edit_mesh(obj.data)
    for vert in bm.verts:
        vert.select_set(False)
    bm.select_flush(False)
    bm.verts.ensure_lookup_table()
    bm.verts[0].select_set(True)
    expected = obj.matrix_world @ bm.verts[0].co
    assert_vector(scene.cat_edit_location, expected, "단일 정점 위치")
    remove_all_objects()


def test_rotation_and_scale_around_median() -> None:
    obj = setup_plane()
    scene = bpy.context.scene
    assert_vector(scene.cat_edit_rotation, (0.0, 0.0, 0.0), "초기 회전")
    assert_vector(scene.cat_edit_scale, (1.0, 1.0, 1.0), "초기 스케일")

    # 드래그처럼 같은 필드를 연속으로 설정해도 누적되지 않고 최종값만 반영돼야 한다.
    scene.cat_edit_rotation = (0.0, 0.0, math.radians(45.0))
    scene.cat_edit_rotation = (0.0, 0.0, math.radians(90.0))
    assert_vector(scene.cat_edit_rotation, (0.0, 0.0, math.radians(90.0)), "누적 회전값")
    corners = sorted((round(c.x, 4), round(c.y, 4)) for c in world_verts(obj))
    assert corners == [(9.0, -1.0), (9.0, 1.0), (11.0, -1.0), (11.0, 1.0)], corners

    scene.cat_edit_scale = (2.0, 1.0, 1.0)
    scene.cat_edit_scale = (3.0, 1.0, 1.0)
    xs = sorted(round(c.x, 4) for c in world_verts(obj))
    assert xs[0] == 7.0 and xs[-1] == 13.0, xs
    assert_vector(scene.cat_edit_location, (10.0, 0.0, 0.0), "회전/스케일 후 중앙값 유지")

    # 선택이 바뀌면 누적값이 초기화된다.
    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    bm.verts[0].select_set(False)
    assert_vector(scene.cat_edit_scale, (1.0, 1.0, 1.0), "선택 변경 후 스케일 초기화")
    remove_all_objects()


def main() -> None:
    addon, registered_here = load_addon()
    remove_all_objects()
    if registered_here:
        addon.register()
    try:
        test_location_follows_selection()
        test_rotation_and_scale_around_median()
    finally:
        remove_all_objects()
        if registered_here:
            addon.unregister()

    print("CatTools Edit Transform Blender 스모크 테스트 통과")


if __name__ == "__main__":
    main()
