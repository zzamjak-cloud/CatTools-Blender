"""Blender에서 CatTools Select Same Pivot 연산자의 실제 동작을 검사합니다."""

from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path

import bmesh
import bpy


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
        remove_all_objects()
        check_edit_mesh_faces()
        check_edit_mesh_verts()
    finally:
        remove_all_objects()
        if registered_here:
            addon.unregister()

    print("CatTools Select Same Pivot Blender 스모크 테스트 통과")


if __name__ == "__main__":
    main()
