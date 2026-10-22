"""Blender에서 CatTools Modifier Apply(선택 오브젝트 모디파이어 적용)를 검사합니다."""

from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
ADDON_PATH = ROOT / "__init__.py"
MODULE_NAME = "bl_ext.user_default.cat_tools"


def load_addon():
    if MODULE_NAME in bpy.context.preferences.addons:
        return importlib.import_module(MODULE_NAME), False

    spec = importlib.util.spec_from_file_location("cat_tools_apply_modifiers_smoke", ADDON_PATH)
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


def create_cube(name: str):
    bpy.ops.mesh.primitive_cube_add(size=2.0)
    obj = bpy.context.object
    obj.name = name
    return obj


def select_only(*objects) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0] if objects else None


def main() -> None:
    addon, registered_here = load_addon()
    remove_all_objects()
    try:
        plain = create_cube("CatToolsApplyPlain")
        mirrored = create_cube("CatToolsApplyMirror")
        mirrored.location.x = 3.0
        mirror = mirrored.modifiers.new("Mirror", "MIRROR")
        mirror.use_axis = (True, False, False)
        mirror.use_mirror_merge = False
        bevel_target = create_cube("CatToolsApplyArray")
        bevel_target.location.y = 5.0
        array = bevel_target.modifiers.new("Array", "ARRAY")
        array.count = 3

        # 모디파이어가 없는 오브젝트만 선택하면 버튼이 비활성화되어야 한다.
        select_only(plain)
        assert not bpy.ops.object.cat_apply_modifiers.poll(), "모디파이어가 없는데 Apply가 활성화되었습니다."

        # 아무것도 선택하지 않아도 비활성화되어야 한다.
        select_only()
        assert not bpy.ops.object.cat_apply_modifiers.poll(), "선택이 없는데 Apply가 활성화되었습니다."

        # 모디파이어가 있는 오브젝트가 섞여 있으면 활성화된다.
        select_only(plain, mirrored, bevel_target)
        assert bpy.ops.object.cat_apply_modifiers.poll(), "모디파이어가 있는데 Apply가 비활성화되었습니다."

        result = bpy.ops.object.cat_apply_modifiers()
        assert result == {"FINISHED"}, f"Apply 실행 실패: {result}"
        assert len(mirrored.modifiers) == 0, "Mirror 모디파이어가 남아 있습니다."
        assert len(bevel_target.modifiers) == 0, "Array 모디파이어가 남아 있습니다."
        assert len(mirrored.data.vertices) == 16, f"Mirror 적용 결과가 다릅니다: {len(mirrored.data.vertices)}"
        assert len(bevel_target.data.vertices) == 24, f"Array 적용 결과가 다릅니다: {len(bevel_target.data.vertices)}"
        assert len(plain.data.vertices) == 8, "모디파이어 없는 오브젝트가 바뀌었습니다."
        assert not bpy.ops.object.cat_apply_modifiers.poll(), "적용 후에도 Apply가 활성화되어 있습니다."

        # Edit 모드에서도 적용한 뒤 Edit 모드로 돌아와야 한다.
        edited = create_cube("CatToolsApplyEdit")
        edited.location.z = 5.0
        solidify = edited.modifiers.new("Solidify", "SOLIDIFY")
        solidify.thickness = 0.1
        select_only(edited)
        bpy.ops.object.mode_set(mode="EDIT")
        assert bpy.ops.object.cat_apply_modifiers.poll(), "Edit 모드에서 Apply가 비활성화되었습니다."
        result = bpy.ops.object.cat_apply_modifiers()
        assert result == {"FINISHED"}, f"Edit 모드 Apply 실행 실패: {result}"
        assert bpy.context.object.mode == "EDIT", "Apply 후 Edit 모드로 돌아오지 않았습니다."
        bpy.ops.object.mode_set(mode="OBJECT")
        assert len(edited.modifiers) == 0, "Solidify 모디파이어가 남아 있습니다."
        assert len(edited.data.vertices) == 16, f"Solidify 적용 결과가 다릅니다: {len(edited.data.vertices)}"

        # 링크 복제된 메쉬도 적용되고, 원본 쪽 데이터는 그대로 남아야 한다.
        source = create_cube("CatToolsApplyLinkedSource")
        linked = source.copy()
        linked.name = "CatToolsApplyLinked"
        bpy.context.collection.objects.link(linked)
        linked.modifiers.new("Array", "ARRAY").count = 2
        select_only(linked)
        result = bpy.ops.object.cat_apply_modifiers()
        assert result == {"FINISHED"}, f"링크 복제 Apply 실행 실패: {result}"
        assert len(linked.modifiers) == 0, "링크 복제 오브젝트에 모디파이어가 남아 있습니다."
        assert linked.data is not source.data, "링크 복제 메쉬가 단독 데이터로 분리되지 않았습니다."
        assert len(linked.data.vertices) == 16, f"링크 복제 적용 결과가 다릅니다: {len(linked.data.vertices)}"
        assert len(source.data.vertices) == 8, "원본 메쉬가 함께 바뀌었습니다."
    finally:
        remove_all_objects()
        if registered_here:
            addon.unregister()

    print("CatTools Modifier Apply Blender 스모크 테스트 통과")


if __name__ == "__main__":
    main()
