"""Blender에서 CatTools 미러 연산자의 실제 동작을 검사합니다."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
ADDON_PATH = ROOT / "__init__.py"
AXES = {
    "x": 0,
    "y": 1,
    "z": 2,
}


def load_addon():
    spec = importlib.util.spec_from_file_location("cat_tools_blender_smoke", ADDON_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("CatTools 모듈 로더를 생성할 수 없습니다.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def remove_all_objects() -> None:
    if bpy.context.object is not None and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def create_axis_object(axis_index: int, values: list[float]):
    mesh = bpy.data.meshes.new("CatToolsMirrorSmokeMesh")
    coordinates = []
    for value in values:
        coordinate = [0.0, 0.0, 0.0]
        coordinate[axis_index] = value
        coordinates.append(tuple(coordinate))
    mesh.from_pydata(coordinates, [], [])
    mesh.update()

    obj = bpy.data.objects.new("CatToolsMirrorSmokeObject", mesh)
    bpy.context.collection.objects.link(obj)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    return obj


def axis_values(obj, axis_index: int) -> list[float]:
    return sorted(round(vertex.co[axis_index], 6) for vertex in obj.data.vertices)


def assert_mirror(obj, axis_index: int) -> None:
    mirrors = [modifier for modifier in obj.modifiers if modifier.type == "MIRROR"]
    assert len(mirrors) == 1, f"Mirror 개수가 1이 아닙니다: {len(mirrors)}"
    expected_axes = [False, False, False]
    expected_axes[axis_index] = True
    assert list(mirrors[0].use_axis) == expected_axes, (
        f"Mirror 축이 다릅니다: {list(mirrors[0].use_axis)}"
    )


def run_operator(axis: str, values: list[float]) -> tuple[list[float], object]:
    axis_index = AXES[axis]
    obj = create_axis_object(axis_index, values)
    operator = getattr(bpy.ops.wm, f"add_mirror_{axis}_modifier")
    result = operator()
    assert result == {"FINISHED"}, f"{axis.upper()} Mirror 실행 실패: {result}"
    assert_mirror(obj, axis_index)
    return axis_values(obj, axis_index), obj


def remove_object(obj) -> None:
    mesh = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.meshes.remove(mesh)


def main() -> None:
    addon = load_addon()
    remove_all_objects()
    addon.register()
    try:
        for axis in AXES:
            mixed_values, mixed_obj = run_operator(axis, [-1.0, -0.005, 0.005, 1.0])
            assert mixed_values == [0.0, 0.005, 1.0], (
                f"{axis.upper()} 혼합 좌표 결과가 다릅니다: {mixed_values}"
            )
            remove_object(mixed_obj)

            preserved_values, preserved_obj = run_operator(axis, [0.0, 0.005, 1.0])
            assert preserved_values == [0.0, 0.005, 1.0], (
                f"{axis.upper()} 보존 좌표가 변경되었습니다: {preserved_values}"
            )
            remove_object(preserved_obj)
    finally:
        remove_all_objects()
        addon.unregister()

    print("CatTools X/Y/Z Mirror Blender 스모크 테스트 통과")


if __name__ == "__main__":
    main()
