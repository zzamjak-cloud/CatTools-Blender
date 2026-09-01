"""Blender에서 CatTools Align 연산자의 실제 동작을 검사합니다."""

from __future__ import annotations

import importlib
import importlib.util
import math
from pathlib import Path

import bpy
from mathutils import Quaternion


ROOT = Path(__file__).resolve().parents[1]
ADDON_PATH = ROOT / "__init__.py"
MODULE_NAME = "bl_ext.user_default.cat_tools"
TOLERANCE = 1e-5


def load_addon():
    if MODULE_NAME in bpy.context.preferences.addons:
        return importlib.import_module(MODULE_NAME), False

    spec = importlib.util.spec_from_file_location("cat_tools_align_smoke", ADDON_PATH)
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


def create_object(name: str):
    mesh = bpy.data.meshes.new(f"{name}Mesh")
    mesh.from_pydata([(0.0, 0.0, 0.0)], [], [])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def select(target, active) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    for obj in (target, active):
        obj.select_set(True)
    bpy.context.view_layer.objects.active = active


def assert_close(actual, expected, message: str) -> None:
    for index, (left, right) in enumerate(zip(actual, expected)):
        assert abs(left - right) < TOLERANCE, (
            f"{message} [{index}]: {left} != {right} (전체 {list(actual)})"
        )


def run_align(mode: str, axis: str) -> None:
    result = bpy.ops.object.cat_align(mode=mode, axis=axis)
    assert result == {"FINISHED"}, f"{mode}/{axis} Align 실행 실패: {result}"


def test_single_axis_only_changes_that_axis() -> None:
    """축 버튼은 해당 축만 바꾸고 나머지 두 축은 보존해야 한다."""
    for mode, property_name, active_values, target_values in (
        ("LOCATION", "location", (1.0, 2.0, 3.0), (7.0, 8.0, 9.0)),
        ("ROTATION", "rotation_euler", (0.1, 0.2, 0.3), (0.7, 0.8, 0.9)),
        ("SCALE", "scale", (1.5, 2.5, 3.5), (7.5, 8.5, 9.5)),
    ):
        for axis, axis_index in (("X", 0), ("Y", 1), ("Z", 2)):
            active = create_object("CatToolsAlignActive")
            target = create_object("CatToolsAlignTarget")
            setattr(active, property_name, active_values)
            setattr(target, property_name, target_values)
            select(target, active)

            run_align(mode, axis)

            expected = list(target_values)
            expected[axis_index] = active_values[axis_index]
            assert_close(
                getattr(target, property_name),
                expected,
                f"{mode}/{axis} 결과가 다릅니다",
            )
            assert_close(
                getattr(active, property_name),
                active_values,
                f"{mode}/{axis} 활성 오브젝트가 변경되었습니다",
            )
            remove_all_objects()


def test_all_axes() -> None:
    """All 버튼은 세 축을 모두 활성 오브젝트 값으로 맞춰야 한다."""
    active = create_object("CatToolsAlignActive")
    target = create_object("CatToolsAlignTarget")
    active.location = (1.0, 2.0, 3.0)
    active.scale = (1.5, 2.5, 3.5)
    active.rotation_euler = (0.1, 0.2, 0.3)
    target.location = (7.0, 8.0, 9.0)
    target.scale = (7.5, 8.5, 9.5)
    target.rotation_euler = (0.7, 0.8, 0.9)
    select(target, active)

    for mode, property_name in (
        ("LOCATION", "location"),
        ("ROTATION", "rotation_euler"),
        ("SCALE", "scale"),
    ):
        run_align(mode, "ALL")
        assert_close(
            getattr(target, property_name),
            getattr(active, property_name),
            f"{mode}/ALL 결과가 다릅니다",
        )

    remove_all_objects()


def test_quaternion_rotation_mode() -> None:
    """rotation_mode가 QUATERNION이어도 회전 정렬이 조용히 무시되지 않아야 한다."""
    active = create_object("CatToolsAlignActive")
    target = create_object("CatToolsAlignTarget")
    active.rotation_euler = (0.0, 0.0, math.radians(90.0))
    target.rotation_mode = "QUATERNION"
    target.rotation_quaternion = Quaternion((1.0, 0.0, 0.0), 0.0)
    select(target, active)

    run_align("ROTATION", "ALL")

    assert_close(
        target.rotation_quaternion.to_euler("XYZ"),
        (0.0, 0.0, math.radians(90.0)),
        "QUATERNION 모드 회전 정렬 결과가 다릅니다",
    )
    remove_all_objects()


def test_poll_requires_two_objects() -> None:
    """활성 오브젝트 하나만 선택된 상태에서는 실행할 수 없어야 한다."""
    active = create_object("CatToolsAlignActive")
    bpy.ops.object.select_all(action="DESELECT")
    active.select_set(True)
    bpy.context.view_layer.objects.active = active

    assert not bpy.ops.object.cat_align.poll(), (
        "오브젝트가 하나만 선택된 상태에서 Align이 활성화되어 있습니다."
    )
    remove_all_objects()


def main() -> None:
    addon, registered_here = load_addon()
    remove_all_objects()
    if registered_here:
        addon.register()
    try:
        test_single_axis_only_changes_that_axis()
        test_all_axes()
        test_quaternion_rotation_mode()
        test_poll_requires_two_objects()
    finally:
        remove_all_objects()
        if registered_here:
            addon.unregister()

    print("CatTools Align Blender 스모크 테스트 통과")


if __name__ == "__main__":
    main()
